# -*- coding: utf-8 -*-
"""
Alpha 提交页面
功能：同步数据、查看候选池、指定提交、批量提交 Alpha
优化版本：使用统一的 API 客户端、session_state、更好的 UI
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from web.utils.helpers import get_db
from web.utils.api_client_st import api_get, api_post, check_api_connection
from web.utils.streamlit_helpers import (
    init_session_state,
    render_metric_card,
    connection_status_indicator
)
from core.api_client import BrainAPIClient


def init_submit_state():
    """初始化提交页面状态"""
    init_session_state({
        'candidates_cache': None,
        'candidates_timestamp': None,
        'last_sync_time': None,
    })


def render_sync_section():
    """渲染同步区域"""
    st.subheader("📥 数据同步")
    st.caption("提交前请先同步数据，确保获取最新的 8 项 Checks 验证结果")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📥 增量同步", help="同步自上次同步以来的数据", width='stretch'):
            with st.spinner("同步中..."):
                result = api_post("sync/incremental", timeout=120)
            
            if result.get("success"):
                st.success(f"✅ {result.get('message')}")
                st.write(f"新增 **{result.get('new_count', 0)}** 个, 更新 **{result.get('update_count', 0)}** 个")
                st.session_state.last_sync_time = datetime.now()
                # 清除候选池缓存
                st.session_state.candidates_cache = None
            else:
                st.error(f"❌ 同步失败: {result.get('error', '未知错误')}")
            st.rerun()
    
    with col2:
        # 初始化确认状态
        if 'confirm_full_sync' not in st.session_state:
            st.session_state.confirm_full_sync = False
        
        if st.button("📤 全量同步", help="同步所有 Alpha 数据", width='stretch'):
            st.session_state.confirm_full_sync = True
        
        if st.session_state.confirm_full_sync:
            st.warning("⚠️ 确定要全量同步吗？这可能需要较长时间")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ 确认", type="primary", width='stretch'):
                    st.session_state.confirm_full_sync = False
                    with st.spinner("正在获取所有 Alpha..."):
                        result = api_post("sync/full", timeout=300)
                    
                    if result.get("success"):
                        st.success(f"✅ {result.get('message')}")
                        st.write(f"新增 **{result.get('new_count', 0)}** 个, 更新 **{result.get('update_count', 0)}** 个, 共 **{result.get('total', 0)}** 个")
                        st.session_state.last_sync_time = datetime.now()
                        st.session_state.candidates_cache = None
                    else:
                        st.error(f"❌ 同步失败: {result.get('error', '未知错误')}")
                    st.rerun()
            with col_no:
                if st.button("❌ 取消", width='stretch'):
                    st.session_state.confirm_full_sync = False
                    st.rerun()
    
    with col3:
        # 显示上次同步时间
        if st.session_state.last_sync_time:
            st.info(f"上次同步: {st.session_state.last_sync_time.strftime('%H:%M:%S')}")


def render_candidate_pool():
    """渲染候选池"""
    st.subheader("📋 候选池")
    st.caption("通过 8 项 Checks 验证的 Alpha 列表")
    
    # 获取候选池（使用缓存）
    cache_key = 'candidates_cache'
    cache_valid = (
        st.session_state.get('candidates_cache') is not None and
        st.session_state.get('candidates_timestamp') is not None
    )
    
    if cache_valid:
        import time
        if time.time() - st.session_state.candidates_timestamp < 60:  # 60秒缓存
            candidates = st.session_state.candidates_cache
        else:
            candidates = None
    else:
        candidates = None
    
    if candidates is None:
        db = get_db()
        db.update_candidate_pool()
        # get_candidates 返回元组 (candidates, total)，需要解包
        candidates, _ = db.get_candidates()
        # 更新缓存
        import time
        st.session_state.candidates_cache = candidates
        st.session_state.candidates_timestamp = time.time()
    
    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("候选数量", len(candidates))
    with col2:
        submitted_today = len([c for c in candidates if c.get('submitted_today')])
        st.metric("今日已提交", submitted_today)
    with col3:
        available = len(candidates) - submitted_today
        st.metric("可提交", max(0, available))
    with col4:
        avg_sharpe = sum([c.get('sharpe', 0) for c in candidates]) / max(1, len(candidates))
        st.metric("平均 Sharpe", f"{avg_sharpe:.2f}")
    
    if candidates:
        # 显示表格
        df_candidates = pd.DataFrame(candidates)
        display_cols = ['alpha_id', 'sharpe', 'fitness', 'turnover', 'returns', 'drawdown']
        available_cols = [c for c in display_cols if c in df_candidates.columns]
        
        # 分页
        page_size = st.session_state.get('page_size', 50)
        total_pages = max(1, (len(df_candidates) + page_size - 1) // page_size)
        
        col_page, col_info = st.columns([1, 3])
        with col_page:
            page = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="candidates_page")
        with col_info:
            st.write(f"共 {total_pages} 页, {len(df_candidates)} 条")
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        st.dataframe(
            df_candidates[available_cols].iloc[start_idx:end_idx],
            width='stretch',
            height=min(350, (end_idx - start_idx) * 35 + 40)
        )
        
        # 刷新按钮
        if st.button("🔄 刷新候选池"):
            st.session_state.candidates_cache = None
            st.rerun()
    else:
        st.info("候选池为空，请先同步数据")


def render_pool_submit(candidates):
    """渲染候选池提交"""
    st.subheader("🚀 提交 Alpha")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        num_to_submit = st.number_input(
            "目标成功数量",
            min_value=1,
            max_value=min(50, max(1, len(candidates))),
            value=min(2, max(1, len(candidates))),
            help="直到成功达到目标数量才停止提交"
        )
        
        # 429 重试说明
        st.info("""
        **提交说明：**
        - 仅提交通过 8 项 Checks 验证的 Alpha
        - 429 限流时自动重试（60s → 120s → 240s）
        - 连续 3 次失败的 Alpha 将移出候选池
        """)
    
    with col2:
        st.write("")  # 占位
        if st.button("🚀 开始提交", type="primary", disabled=len(candidates) == 0, width='stretch'):
            if len(candidates) == 0:
                st.warning("没有可提交的 Alpha")
            else:
                with st.spinner(f"正在提交 {num_to_submit} 个 Alpha..."):
                    result = api_post("submit", {"num_to_submit": num_to_submit}, timeout=600)
                
                if result.get("success"):
                    success_count = result.get('success_count', 0)
                    failed_count = result.get('failed_count', 0)
                    skipped_429 = result.get('skipped_429', 0)
                    
                    # 统计结果
                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        st.metric("成功", success_count, delta=None)
                    with col_s2:
                        st.metric("失败", failed_count, delta=None)
                    with col_s3:
                        st.metric("限流跳过", skipped_429, delta=None)
                    
                    successful_ids = result.get('successful_ids', [])
                    if successful_ids:
                        st.success(f"✅ 成功提交 {len(successful_ids)} 个 Alpha")
                        with st.expander("查看成功的 Alpha ID"):
                            st.code("\n".join(successful_ids))
                else:
                    st.error(f"❌ 提交失败: {result.get('error', '未知错误')}")
                
                # 清除缓存
                st.session_state.candidates_cache = None


def render_custom_submit():
    """渲染指定 Alpha ID 提交"""
    st.subheader("🎯 指定 Alpha ID 提交")
    st.caption("输入要提交的特定 Alpha ID，可一次提交多个（每行一个）")
    
    alpha_ids_input = st.text_area(
        "Alpha ID 列表",
        placeholder="例如:\n1167\n1168\n1169",
        height=150,
        help="输入 Alpha ID，每行一个",
        key="custom_alpha_ids"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        num_custom = st.number_input(
            "提交数量限制",
            min_value=1,
            max_value=100,
            value=10,
            help="最多提交多少个 Alpha"
        )
    
    st.divider()
    
    # 验证区域
    st.subheader("🔍 验证 Alpha")
    
    client = BrainAPIClient()
    if not client.ensure_session():
        st.error("认证失败，请检查账号配置")
        return
    
    # 解析输入的 Alpha ID
    alpha_ids = [aid.strip() for aid in alpha_ids_input.strip().split('\n') if aid.strip()]
    valid_ids = []
    alpha_info_list = []
    
    if alpha_ids:
        with st.spinner("正在验证 Alpha ID..."):
            for i, aid in enumerate(alpha_ids):
                alpha = client.get_alpha(aid)
                if alpha:
                    valid_ids.append(aid)
                    alpha_info_list.append(alpha)
    
    if alpha_info_list:
        df_valid = pd.DataFrame(alpha_info_list)
        display_cols = ['alpha_id', 'sharpe', 'fitness', 'turnover', 'returns', 'drawdown']
        available_cols = [c for c in display_cols if c in df_valid.columns]
        
        col_v1, col_v2 = st.columns([3, 1])
        with col_v1:
            st.write(f"**有效的 Alpha ({len(valid_ids)} 个)：**")
        with col_v2:
            st.metric("有效", len(valid_ids))
        
        st.dataframe(
            df_valid[available_cols],
            width='stretch',
            height=min(300, len(df_valid) * 35 + 40)
        )
    
    # 显示未找到的
    invalid_ids = [aid for aid in alpha_ids if aid not in valid_ids]
    if invalid_ids:
        with st.expander(f"⚠️ 未找到的 Alpha ID ({len(invalid_ids)} 个)"):
            st.code("\n".join(invalid_ids[:50]))
    
    st.divider()
    
    # 提交说明
    col1, col2 = st.columns([2, 1])
    with col1:
        st.info("""
        **说明：**
        - 直接提交指定的 Alpha ID
        - 不受 8 项 Checks 限制
        - 可用于提交未在候选池中的 Alpha
        - 429 限流自动重试
        """)
    
    with col2:
        st.write("")  # 占位
        if st.button("🚀 提交指定 Alpha", type="primary", disabled=len(valid_ids) == 0, width='stretch'):
            if not valid_ids:
                st.error("没有有效的 Alpha ID 可提交")
            else:
                # 创建临时文件保存 Alpha ID
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                    for aid in valid_ids[:num_custom]:
                        f.write(aid + '\n')
                    temp_path = f.name
                
                try:
                    from core.submit import submit_alpha_ids
                    with st.spinner(f"正在提交 {min(num_custom, len(valid_ids))} 个 Alpha..."):
                        result = submit_alpha_ids(temp_path, num_to_submit=num_custom)
                    
                    # 显示结果
                    col_r1, col_r2, col_r3 = st.columns(3)
                    with col_r1:
                        st.metric("成功", result['success'])
                    with col_r2:
                        st.metric("失败", result['failed'])
                    with col_r3:
                        st.metric("限流跳过", result['skipped_429'])
                    
                    if result['successful_ids']:
                        st.success(f"✅ 成功提交 {len(result['successful_ids'])} 个 Alpha")
                        with st.expander("查看成功的 Alpha ID"):
                            st.code("\n".join(result['successful_ids'][:20]))
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
    
    client.session.close()


def page_submit():
    """提交 Alpha 页面"""
    # 初始化状态
    init_submit_state()
    
    # 检查 API 连接
    is_connected, error_msg = check_api_connection()
    if not is_connected:
        connection_status_indicator(False, error_msg)
        return
    
    connection_status_indicator(True)
    st.divider()
    
    # 选项卡
    tab1, tab2 = st.tabs(["📋 候选池提交", "🎯 指定 Alpha ID 提交"])
    
    with tab1:
        render_sync_section()
        st.divider()
        render_candidate_pool()
        st.divider()
        render_pool_submit(st.session_state.get('candidates_cache') or [])
    
    with tab2:
        render_custom_submit()
