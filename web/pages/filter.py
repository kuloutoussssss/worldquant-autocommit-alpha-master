# -*- coding: utf-8 -*-
"""
筛选导出页面
功能：按条件筛选 Alpha 并导出，支持批量中性化回测
"""
import streamlit as st
import pandas as pd
import sqlite3
import requests
from datetime import datetime
from web.utils.helpers import get_db
from web.utils.api_client_st import API_BASE


def page_filter():
    """筛选导出页面"""
    st.header("🎯 筛选与导出")
    
    db = get_db()
    
    with db._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT * FROM tested_expressions WHERE status = 'OK'
            ORDER BY sharpe DESC
        """)
        rows = [dict(row) for row in cursor.fetchall()]
    
    if not rows:
        st.info("暂无回测数据")
        return
    
    df = pd.DataFrame(rows)
    
    st.subheader("筛选条件")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        min_sharpe = st.slider("Sharpe ≥", min_value=-5.0, max_value=20.0, value=1.25, step=0.05)
    with col2:
        min_fitness = st.slider("Fitness ≥", min_value=-5.0, max_value=50.0, value=1.0, step=0.1)
    with col3:
        max_turnover = st.slider("Turnover ≤", min_value=0.0, max_value=1.0, value=0.7, step=0.01)
    
    col4, col5 = st.columns(2)
    with col4:
        min_returns = st.slider("Returns ≥", min_value=-1.0, max_value=1.0, value=-1.0, step=0.01)
    with col5:
        max_drawdown = st.slider("Drawdown ≤", min_value=0.0, max_value=1.0, value=1.0, step=0.01)
    
    qualified = df[
        (df["sharpe"] >= min_sharpe) &
        (df["fitness"] >= min_fitness) &
        (df["turnover"] <= max_turnover) &
        (df["returns"] >= min_returns) &
        (df["drawdown"] <= max_drawdown)
    ]
    
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("筛选结果", len(qualified))
    with col2:
        st.metric("占比", f"{len(qualified)/len(df)*100:.1f}%")
    with col3:
        avg_sharpe = qualified["sharpe"].mean() if len(qualified) > 0 else 0
        st.metric("平均 Sharpe", f"{avg_sharpe:.2f}")
    
    st.divider()
    
    if len(qualified) > 0:
        st.subheader("达标 Alpha 列表")
        
        # 初始化 session state
        if 'selected_alphas' not in st.session_state:
            st.session_state.selected_alphas = set()
        if 'neutralization_results' not in st.session_state:
            st.session_state.neutralization_results = {}
        
        # 显示表格，带勾选框
        display_df = qualified[["alpha_id", "sharpe", "fitness", "turnover", "returns", "drawdown", "expression"]].copy()
        display_df = display_df.round(4)
        
        # 使用列配置创建带勾选框的表格
        col_config = {
            "alpha_id": st.column_config.TextColumn("Alpha ID", width="medium"),
            "sharpe": st.column_config.NumberColumn("Sharpe", format="%.3f", width="small"),
            "fitness": st.column_config.NumberColumn("Fitness", format="%.3f", width="small"),
            "turnover": st.column_config.NumberColumn("换手率", format="%.3f", width="small"),
            "returns": st.column_config.NumberColumn("收益", format="%.4f", width="small"),
            "drawdown": st.column_config.NumberColumn("回撤", format="%.3f", width="small"),
            "expression": st.column_config.TextColumn("表达式", width="large"),
        }
        
        # 添加勾选列
        display_df['_selected'] = display_df['alpha_id'].isin(st.session_state.selected_alphas)
        
        edited_df = st.data_editor(
            display_df,
            column_config=col_config,
            hide_index=True,
            width='stretch',
            height=400,
            row_selection="multi",
            key="alpha_selection"
        )
        
        # 同步勾选状态到 session_state
        if edited_df is not None and '_selected' in edited_df.columns:
            selected_ids = edited_df[edited_df['_selected']]['alpha_id'].tolist()
            st.session_state.selected_alphas = set(selected_ids)
        
        # 获取当前选中的行
        selected_rows = display_df[display_df['alpha_id'].isin(st.session_state.selected_alphas)]
        
        st.divider()
        
        # 操作按钮区
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("已选中", len(st.session_state.selected_alphas))
        
        with col2:
            if st.button("🔄 刷新选中", use_container_width=True):
                st.rerun()
        
        with col3:
            if st.button("🗑️ 清除选中", use_container_width=True):
                st.session_state.selected_alphas = set()
                st.rerun()
        
        with col4:
            if st.button("✅ 全选", use_container_width=True):
                st.session_state.selected_alphas = set(qualified['alpha_id'].dropna().tolist())
                st.rerun()
        
        st.divider()
        
        # 中性化回测区域
        st.subheader("⚡ 批量中性化回测")
        
        # 中性化配置
        neut_col1, neut_col2, neut_col3 = st.columns(3)
        with neut_col1:
            neutralization_region = st.selectbox(
                "区域",
                options=["USA", "CHN", "CHN_A", "IND", "EUR"],
                index=0,
                help="选择中性化回测的区域"
            )
        with neut_col2:
            max_trade_mode = st.selectbox(
                "maxTrade",
                options=["BOTH", "ON", "OFF"],
                index=0,
                help="BOTH: 测试ON和OFF两种模式"
            )
        with neut_col3:
            concurrency = st.number_input(
                "并发数",
                min_value=1,
                max_value=5,
                value=1,
                help="同时测试的组合数"
            )
        
        # 中性化按钮
        if len(st.session_state.selected_alphas) > 0:
            if st.button(f"🚀 批量中性化回测 ({len(st.session_state.selected_alphas)} 个)", type="primary", use_container_width=True):
                selected_alpha_ids = list(st.session_state.selected_alphas)
                progress_bar = st.progress(0, text="准备开始...")
                status_text = st.empty()
                
                all_results = []
                total = len(selected_alpha_ids)
                
                for idx, alpha_id in enumerate(selected_alpha_ids):
                    status_text.text(f"正在中性化回测 [{idx+1}/{total}]: {alpha_id}")
                    progress_bar.progress((idx + 1) / total)
                    
                    try:
                        # 获取 Alpha 信息
                        alpha_response = requests.get(f"{API_BASE}/database/alphas/{alpha_id}", timeout=30)
                        if alpha_response.status_code == 200:
                            alpha_data = alpha_response.json()
                            # 从返回的 alpha 对象中获取 expression
                            alpha_obj = alpha_data.get('alpha', {})
                            expression = alpha_obj.get('expression', '')
                            
                            if expression:
                                # 调用中性化测试
                                neut_response = requests.post(
                                    f"{API_BASE}/api/neutralization/test",
                                    json={
                                        "alpha_id": alpha_id,
                                        "expression": expression,
                                        "region": neutralization_region,
                                        "concurrency": concurrency
                                    },
                                    timeout=600
                                )
                                
                                if neut_response.status_code == 200:
                                    result = neut_response.json()
                                    all_results.append({
                                        'alpha_id': alpha_id,
                                        'status': 'success',
                                        'results': result.get('results', []),
                                        'summary': result.get('summary', {})
                                    })
                                else:
                                    all_results.append({
                                        'alpha_id': alpha_id,
                                        'status': 'error',
                                        'error': f"HTTP {neut_response.status_code}"
                                    })
                            else:
                                all_results.append({
                                    'alpha_id': alpha_id,
                                    'status': 'error',
                                    'error': '表达式为空'
                                })
                        else:
                            all_results.append({
                                'alpha_id': alpha_id,
                                'status': 'error',
                                'error': f'获取Alpha失败: {alpha_response.status_code}'
                            })
                    except Exception as e:
                        all_results.append({
                            'alpha_id': alpha_id,
                            'status': 'error',
                            'error': str(e)
                        })
                
                # 保存结果
                st.session_state.neutralization_results = all_results
                progress_bar.empty()
                status_text.empty()
                
                # 显示结果
                st.success(f"中性化回测完成！处理了 {len(all_results)} 个 Alpha")
        
        # 显示中性化结果
        if st.session_state.neutralization_results:
            st.divider()
            st.subheader("📊 中性化回测结果")
            
            # 汇总统计
            success_count = sum(1 for r in st.session_state.neutralization_results if r.get('status') == 'success')
            total_results = sum(len(r.get('results', [])) for r in st.session_state.neutralization_results if r.get('status') == 'success')
            quality_count = sum(r.get('summary', {}).get('quality_count', 0) for r in st.session_state.neutralization_results)
            
            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
            with stat_col1:
                st.metric("成功", success_count)
            with stat_col2:
                st.metric("失败", len(st.session_state.neutralization_results) - success_count)
            with stat_col3:
                st.metric("总组合数", total_results)
            with stat_col4:
                st.metric("优质Alpha", quality_count)
            
            # 详细结果表格
            all_combos = []
            for r in st.session_state.neutralization_results:
                if r.get('status') == 'success':
                    for combo in r.get('results', []):
                        all_combos.append({
                            '原Alpha': r['alpha_id'],
                            '中性化': combo.get('neutralization', ''),
                            'maxTrade': combo.get('max_trade', ''),
                            'Sharpe': combo.get('sharpe', 0),
                            'Fitness': combo.get('fitness', 0),
                            '换手率': combo.get('turnover', 0),
                            'Margin': combo.get('margin', 0),
                            '优质': '★' if combo.get('is_quality') else ''
                        })
            
            if all_combos:
                result_df = pd.DataFrame(all_combos)
                result_df = result_df.sort_values('Sharpe', ascending=False)
                result_df['Sharpe'] = result_df['Sharpe'].round(3)
                result_df['Fitness'] = result_df['Fitness'].round(3)
                result_df['换手率'] = result_df['换手率'].round(3)
                result_df['Margin'] = result_df['Margin'].round(6)
                
                st.dataframe(result_df, use_container_width=True, height=400)
                
                # 导出中性化结果
                csv_data = result_df.to_csv(index=False)
                st.download_button(
                    "📥 导出中性化结果",
                    csv_data,
                    f"neutralization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv",
                    type="primary"
                )
            
            # 显示失败的 Alpha
            failed = [r for r in st.session_state.neutralization_results if r.get('status') != 'success']
            if failed:
                st.warning(f"以下 Alpha 中性化失败：")
                for f in failed:
                    st.write(f"- **{f['alpha_id']}**: {f.get('error', '未知错误')}")
        
        st.divider()
        
        # 导出区域
        export_col1, export_col2, export_col3 = st.columns(3)
        with export_col1:
            csv_data = qualified.to_csv(index=False)
            st.download_button(
                "📥 导出为 CSV",
                csv_data,
                f"qualified_alphas_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
                type="primary"
            )
        
        with export_col2:
            txt_content = "\n".join(qualified["expression"].tolist())
            st.download_button(
                "📥 导出为 TXT",
                txt_content,
                f"qualified_alphas_{datetime.now().strftime('%Y%m%d')}.txt",
                "text/plain"
            )
        
        with export_col3:
            alpha_ids = qualified["alpha_id"].dropna().tolist()
            if alpha_ids:
                ids_content = "\n".join(alpha_ids)
                st.download_button(
                    "📥 导出 Alpha ID",
                    ids_content,
                    f"alpha_ids_{datetime.now().strftime('%Y%m%d')}.txt",
                    "text/plain"
                )
    else:
        st.warning("没有符合条件的 Alpha")
