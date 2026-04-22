# -*- coding: utf-8 -*-
"""
批量回测页面
功能：批量回测 Alpha 表达式，通过 API 后端执行
优化：移除阻塞性 sleep，使用异步刷新
"""
import streamlit as st
import requests
from pathlib import Path

from web.utils.helpers import load_to_test_alphas, get_db
from web.utils.streamlit_helpers import auto_refresh

# API 基础地址
API_BASE = "http://localhost:5000/api"


def api_get(endpoint, timeout=5):
    """GET 请求（带缓存）"""
    try:
        resp = requests.get(f"{API_BASE}/{endpoint}", timeout=timeout)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def api_post(endpoint, data=None, timeout=10):
    """POST 请求"""
    try:
        resp = requests.post(f"{API_BASE}/{endpoint}", json=data or {}, timeout=timeout)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@st.cache_data(ttl=5, show_spinner=False)
def get_running_tasks():
    """获取运行中的任务（5秒缓存）"""
    return api_get("tasks/running")


def page_backtest():
    """回测执行页面"""
    st.header("🔬 批量回测")
    
    # 检查 API 连接（带缓存）
    with st.spinner("检查 API 连接..."):
        health = api_get("health", timeout=3)
    
    if not health.get("success"):
        st.error("⚠️ 无法连接 API 服务器")
        st.info("提示：运行 `python web/run.py` 启动 API 服务器")
        
        if st.button("🔄 重试"):
            st.rerun()
        return
    
    # 获取运行中的回测任务
    tasks_result = get_running_tasks()
    running_tasks = tasks_result.get("tasks", []) if tasks_result.get("success") else []
    current_task = None
    for task in running_tasks:
        if task["type"] == "backtest":
            current_task = task
            break
    
    # 如果有运行中的任务，显示进度
    if current_task:
        st.info("🔄 有回测任务正在执行...")
        
        # 刷新任务详情
        task_result = api_get(f"tasks/{current_task['id']}")
        if task_result.get("success"):
            current_task = task_result.get("task", current_task)
        
        # 进度显示
        progress = current_task.get("progress", 0)
        completed = current_task.get("completed", 0)
        total = current_task.get("total", 1)
        failed = current_task.get("failed", 0)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("完成", completed)
        with col2:
            st.metric("失败", failed)
        with col3:
            st.metric("总计", total)
        with col4:
            st.metric("进度", f"{progress*100:.1f}%")
        
        st.progress(progress, text=f"进度: {completed}/{total}")
        
        # 停止按钮
        col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 2])
        with col_btn2:
            if st.button("⏹️ 停止任务", type="secondary"):
                result = api_post(f"tasks/{current_task['id']}/stop")
                if result.get("success"):
                    st.warning("已请求停止任务...")
                    get_running_tasks.clear()
                else:
                    st.error(f"停止失败: {result.get('error')}")
                st.rerun()
        
        # 任务详情
        if current_task.get("details"):
            with st.expander("📋 任务详情", expanded=False):
                for detail in current_task["details"][-10:]:
                    st.text(f"[{detail.get('time', '')}] {detail.get('message', '')}")
        
        # 使用 auto_refresh 而不是 sleep
        st.empty()
        st.markdown("*页面将在 30 秒后自动刷新...*")
        # 刷新任务列表
        get_running_tasks.clear()
        # 触发自动刷新
        auto_refresh(lambda: True, interval=30)
        return
    
    # 检查是否有可恢复的停止任务
    stopped_tasks = [t for t in running_tasks if t["type"] == "backtest" and t["status"] == "stopped"]
    if stopped_tasks:
        st.warning("⚠️ 发现已停止的回测任务，可以继续执行")
        
        # 显示可恢复任务
        for task in stopped_tasks:
            with st.expander(f"📋 {task['id']} (完成: {task.get('completed', 0)}, 失败: {task.get('failed', 0)})"):
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button(f"▶️ 恢复任务", key=f"resume_{task['id']}"):
                        result = api_post("backtest/resume", {"task_id": task["id"]})
                        if result.get("success"):
                            st.success("任务已恢复")
                            get_running_tasks.clear()
                        else:
                            st.error(f"恢复失败: {result.get('error')}")
                        st.rerun()
                with col2:
                    if st.button(f"🗑️ 删除任务", key=f"del_{task['id']}"):
                        # 删除进度文件
                        from web.utils.task_progress import get_progress_manager
                        pm = get_progress_manager()
                        pm.delete_progress(task["id"])
                        st.info("进度文件已删除，请重新开始任务")
                        get_running_tasks.clear()
                        st.rerun()
        
        st.divider()
    
    # ===== 获取待回测统计 =====
    try:
        alphas = load_to_test_alphas()
        db = get_db()
        tested_exprs = db.get_tested_expressions()
        
        untested = [a for a in alphas if a.split("|")[0].strip() not in tested_exprs]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("待回测", len(untested))
        with col2:
            st.metric("已回测", len(alphas) - len(untested))
        with col3:
            st.metric("预计耗时", f"{len(untested) * 12 / 60:.1f} 分钟")
    except Exception as e:
        st.error(f"加载数据失败: {e}")
        untested = []
    
    if not untested:
        st.success("✅ 所有 Alpha 已完成回测！")
        return
    
    st.divider()
    
    # 范围选择
    col_start, col_end = st.columns(2)
    with col_start:
        start_idx = st.number_input("从第几个开始", min_value=1, max_value=len(untested), value=1, key="bt_start")
    with col_end:
        end_idx = st.number_input("到第几个结束", min_value=start_idx, max_value=len(untested), value=len(untested), key="bt_end")
    
    total_to_test = end_idx - start_idx + 1
    
    st.divider()
    
    # 启动按钮
    col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 2])
    with col_btn1:
        st.info(f"将回测 {total_to_test} 个 Alpha")
    with col_btn2:
        start_clicked = st.button("🚀 开始回测", type="primary", disabled=len(untested) == 0, key="bt_start_btn")
    with col_btn3:
        if st.button("🔄 刷新列表", key="bt_refresh"):
            get_running_tasks.clear()
            st.rerun()
    
    if start_clicked:
        # 准备待回测数据
        untested_data = untested[start_idx - 1:end_idx]
        
        # 调用 API 启动任务（只传数据，参数由 Alpha 自带）
        with st.spinner("正在启动回测任务..."):
            result = api_post("backtest/start", {
                "data": untested_data  # 待回测的 Alpha 列表
            })
        
        if result.get("success"):
            st.success(f"✅ 任务已启动: {result.get('task_id')}")
            get_running_tasks.clear()
            st.rerun()
        else:
            st.error(f"❌ 启动失败: {result.get('error')}")


# 扩展 Streamlit 添加 _rerun_trigger 支持
if not hasattr(st, '_rerun_trigger'):
    # 在每个页面渲染后检查是否需要自动刷新
    original_rerun = st.rerun
    def patched_rerun():
        if st.session_state.get('_rerun_trigger'):
            st.session_state._rerun_trigger = False
            import time
            time.sleep(3)
        return original_rerun()
    st.rerun = patched_rerun
