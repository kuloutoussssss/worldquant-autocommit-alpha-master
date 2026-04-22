# -*- coding: utf-8 -*-
"""
一键工作流页面
功能：回测 → 筛选 → 提交，通过 API 后端执行
优化版本：使用统一的 API 客户端、session_state、更好的 UI
"""
import streamlit as st
import json
import time
from pathlib import Path

from web.utils.helpers import load_to_test_alphas, get_db
from web.utils.api_client_st import api_get, api_post, check_api_connection
from web.utils.streamlit_helpers import (
    init_session_state,
    connection_status_indicator,
    render_progress_bar,
    render_expander_logs
)


def init_workflow_state():
    """初始化工作流状态"""
    init_session_state({
        'workflow_config': None,
        'workflow_progress': 0,
    })


def load_workflow_config():
    """加载工作流配置"""
    if st.session_state.workflow_config is not None:
        return st.session_state.workflow_config
    
    config_path = Path(__file__).parent.parent.parent / "data" / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            st.session_state.workflow_config = config.get('workflow', {})
            return st.session_state.workflow_config
    
    # 默认配置
    default_config = {
        'num_to_submit': 10,
        'delay': 5,
        'min_sharpe': 1.25,
        'min_fitness': 1.0,
        'max_turnover': 0.70,
        'input_file': 'data/alphas/to_test.txt'
    }
    st.session_state.workflow_config = default_config
    return default_config


def render_workflow_status(current_task):
    """渲染工作流状态"""
    if not current_task:
        return None
    
    st.warning("🔄 有工作流任务正在执行...")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        progress_val = current_task.get("progress", 0)
        st.progress(progress_val, text=f"进度: {progress_val*100:.0f}%")
        st.session_state.workflow_progress = progress_val
    with col2:
        st.write("")  # 占位
        st.write("")  # 占位
        if st.button("⏹️ 停止任务", type="secondary", width='stretch'):
            result = api_post(f"tasks/{current_task['id']}/stop")
            if result.get("success"):
                st.warning("已请求停止任务...")
            else:
                st.error(f"停止失败: {result.get('error')}")
            st.rerun()
    
    # 刷新任务状态
    task_result = api_get(f"tasks/{current_task['id']}", use_cache=False)
    if task_result.get("success"):
        current_task = task_result.get("task", current_task)
    
    # 显示详情
    details = current_task.get("details", [])
    if details:
        render_expander_logs(details[-30:])
    
    # 状态
    status = current_task.get("status", "running")
    
    status_icons = {
        "completed": "✅",
        "failed": "❌",
        "stopped": "⏹️",
        "running": "🔄"
    }
    
    if status == "completed":
        st.success(f"{status_icons.get(status)} 工作流已完成！")
        # 清理进度
        st.session_state.workflow_progress = 1.0
    elif status == "failed":
        st.error(f"{status_icons.get(status)} 工作流失败: {current_task.get('error', '未知错误')}")
    elif status == "stopped":
        st.warning(f"{status_icons.get(status)} 工作流已停止")
    
    # 自动刷新
    if status == "running":
        time.sleep(3)
        st.rerun()
    
    return status


def render_workflow_config(config):
    """渲染工作流配置"""
    st.subheader("⚙️ 工作流配置")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        num_to_submit = st.number_input(
            "提交数量",
            min_value=1,
            max_value=50,
            value=config.get('num_to_submit', 10),
            help="最多提交的 Alpha 数量"
        )
    with col2:
        delay = st.number_input(
            "回测间隔(秒)",
            min_value=1,
            max_value=60,
            value=int(config.get('delay', 5)),
            help="每个 Alpha 回测之间的间隔"
        )
    with col3:
        test_period = st.selectbox(
            "测试周期",
            ["P2Y0M", "P1Y0M", "P3Y0M"],
            index=0
        )
    
    return {
        'num_to_submit': num_to_submit,
        'delay': delay,
        'test_period': test_period,
    }


def render_filter_config(config):
    """渲染筛选条件"""
    st.subheader("🎯 筛选条件")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        min_sharpe = st.number_input(
            "最小 Sharpe",
            min_value=0.0,
            max_value=10.0,
            value=float(config.get('min_sharpe', 1.25)),
            step=0.05,
            format="%.2f",
            help="Sharpe 比率最低要求"
        )
    with col2:
        min_fitness = st.number_input(
            "最小 Fitness",
            min_value=0.0,
            max_value=5.0,
            value=float(config.get('min_fitness', 1.0)),
            step=0.05,
            format="%.2f",
            help="Fitness 最低要求"
        )
    with col3:
        max_turnover = st.number_input(
            "最大 Turnover",
            min_value=0.0,
            max_value=2.0,
            value=float(config.get('max_turnover', 0.70)),
            step=0.05,
            format="%.2f",
            help="Turnover 最高限制"
        )
    
    return {
        'min_sharpe': min_sharpe,
        'min_fitness': min_fitness,
        'max_turnover': max_turnover,
    }


def render_start_workflow(workflow_config, filter_config):
    """渲染启动工作流按钮"""
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.info("""
        **一键工作流说明：**
        1. 🔬 批量回测 to_test.txt 中的 Alpha
        2. 🎯 根据筛选条件过滤结果
        3. 🚀 自动提交符合条件的 Alpha
        4. ⏭️ 支持 429 限流自动重试（60s → 120s → 240s）
        
        工作流在后台执行，可随时查看进度和停止
        """)
    
    with col2:
        st.write("")  # 占位
        st.write("")  # 占位
        
        # 统计待回测数量
        to_test_count = len(load_to_test_alphas())
        st.metric("待回测", to_test_count)
        
        if st.button("⚡ 启动工作流", type="primary", width='stretch'):
            if to_test_count == 0:
                st.error("没有待回测的 Alpha，请先添加 Alpha")
            else:
                # 合并配置
                full_config = {**workflow_config, **filter_config}
                
                with st.spinner("正在启动工作流..."):
                    result = api_post("tasks/workflow/start", full_config)
                
                if result.get("success"):
                    st.success("✅ 工作流已启动！")
                    st.rerun()
                else:
                    st.error(f"❌ 启动失败: {result.get('error', '未知错误')}")


def render_workflow_history():
    """渲染工作流历史"""
    st.divider()
    st.subheader("📜 历史任务")
    
    # 获取历史任务
    result = api_get("tasks/", use_cache=False)
    
    if result.get("success"):
        tasks = result.get("tasks", [])
        workflow_tasks = [t for t in tasks if t.get("type") == "workflow"]
        
        if workflow_tasks:
            for task in workflow_tasks[:5]:
                status = task.get("status", "unknown")
                created = task.get("created_at", "")
                
                status_colors = {
                    "completed": "🟢",
                    "failed": "🔴",
                    "stopped": "🟡",
                    "running": "🔵"
                }
                
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"{status_colors.get(status, '⚪')} {task.get('id', '')[:20]}...")
                    with col2:
                        st.write(f"进度: {task.get('progress', 0)*100:.0f}%")
                    with col3:
                        if st.button("详情", key=f"view_{task.get('id')}"):
                            st.session_state.selected_task = task.get('id')
                            st.rerun()
        else:
            st.info("暂无工作流历史")
    else:
        st.warning("无法加载历史任务")


def page_one_click_workflow():
    """一键工作流页面"""
    # 初始化状态
    init_workflow_state()
    
    # 检查 API 连接
    is_connected, error_msg = check_api_connection()
    if not is_connected:
        connection_status_indicator(False, error_msg)
        return
    
    connection_status_indicator(True)
    st.divider()
    
    # 检查是否有运行中的工作流任务
    running_result = api_get("tasks/running", use_cache=False)
    running_tasks = running_result.get("tasks", []) if running_result.get("success") else []
    
    current_task = None
    for task in running_tasks:
        if task.get("type") == "workflow":
            current_task = task
            break
    
    # 如果有运行中的工作流，显示状态
    if current_task:
        status = render_workflow_status(current_task)
        
        # 如果工作流未完成，不显示配置区域
        if status in ["running"]:
            st.divider()
            st.subheader("📊 当前阶段")
            # 显示当前阶段信息
            details = current_task.get("details", [])
            if details:
                last_detail = details[-1]
                st.write(f"**{last_detail.get('message', '')}**")
            
            render_workflow_history()
            return
    
    # 加载配置
    config = load_workflow_config()
    
    # 渲染配置区域
    workflow_config = render_workflow_config(config)
    filter_config = render_filter_config(config)
    
    # 启动按钮
    render_start_workflow(workflow_config, filter_config)
    
    # 历史记录
    render_workflow_history()
