# -*- coding: utf-8 -*-
"""
任务列表页面
功能：查看和管理所有后台任务，通过 API 轮询
优化：移除阻塞性 sleep，添加缓存
"""
import requests
import streamlit as st
from datetime import datetime

# API 基础地址
API_BASE = "http://localhost:5000/api"


def api_get(endpoint, timeout=5):
    """GET 请求"""
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


def api_delete(endpoint, timeout=5):
    """DELETE 请求"""
    try:
        resp = requests.delete(f"{API_BASE}/{endpoint}", timeout=timeout)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@st.cache_data(ttl=3, show_spinner=False)
def get_all_tasks(limit=100):
    """获取所有任务（3秒缓存）"""
    return api_get(f"tasks/?limit={limit}")


def page_tasks():
    """任务列表页面"""
    st.header("📋 任务列表")
    
    # 检查 API 连接
    health = api_get("health", timeout=3)
    if not health.get("success"):
        st.error("⚠️ 无法连接 API 服务器")
        st.info("提示：运行 `python web/run.py` 启动 API 服务器")
        
        if st.button("🔄 重试"):
            st.rerun()
        return
    
    # 获取所有任务
    result = get_all_tasks(100)
    if not result.get("success"):
        st.error("获取任务列表失败")
        if st.button("🔄 重试"):
            get_all_tasks.clear()
            st.rerun()
        return
    
    all_tasks = result.get("tasks", [])
    running_tasks = [t for t in all_tasks if t["status"] == "running"]
    
    # 统计信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("运行中", len(running_tasks))
    with col2:
        st.metric("已完成", len([t for t in all_tasks if t["status"] == "completed"]))
    with col3:
        st.metric("已停止", len([t for t in all_tasks if t["status"] == "stopped"]))
    with col4:
        st.metric("失败", len([t for t in all_tasks if t["status"] == "failed"]))
    
    st.divider()
    
    # 操作按钮行
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        if st.button("⏹️ 停止所有", type="secondary", disabled=len(running_tasks) == 0):
            result = api_post("tasks/stop-all")
            if result.get("success"):
                st.success("已停止所有任务")
                get_all_tasks.clear()
            else:
                st.error(f"失败: {result.get('error')}")
            st.rerun()
    
    with col2:
        if st.button("🗑️ 清理完成", type="secondary"):
            result = api_post("tasks/clear")
            if result.get("success"):
                st.success("已清理任务")
                get_all_tasks.clear()
            else:
                st.error(f"失败: {result.get('error')}")
            st.rerun()
    
    with col3:
        if st.button("🔄 刷新", type="secondary"):
            get_all_tasks.clear()
            st.rerun()
    
    with col4:
        if running_tasks:
            st.info(f"🔄 {len(running_tasks)} 个任务运行中，页面将在 30 秒后自动刷新...")
        else:
            st.success("✅ 无运行中任务")
    
    st.divider()
    
    # 任务列表
    if not all_tasks:
        st.info("暂无任务记录")
        return
    
    # 分类显示
    tab1, tab2, tab3, tab4 = st.tabs(["🔄 运行中", "✅ 已完成", "⏹️ 已停止", "❌ 失败"])
    
    with tab1:
        show_task_list([t for t in all_tasks if t["status"] == "running"], refreshable=True)
    
    with tab2:
        show_task_list([t for t in all_tasks if t["status"] == "completed"], show_details=True)
    
    with tab3:
        show_task_list([t for t in all_tasks if t["status"] == "stopped"], show_details=True)
    
    with tab4:
        show_task_list([t for t in all_tasks if t["status"] == "failed"], show_details=True)


def show_task_list(tasks, show_details=False, refreshable=False):
    """显示任务列表"""
    if not tasks:
        st.text("无")
        return
    
    for task in tasks:
        with st.container():
            col1, col2, col3 = st.columns([1, 3, 1])
            
            with col1:
                status_map = {
                    "running": "🔄",
                    "completed": "✅",
                    "stopped": "⏹️",
                    "failed": "❌"
                }
                st.markdown(f"### {status_map.get(task['status'], '❓')}")
            
            with col2:
                st.markdown(f"**{task.get('description', '任务')}**")
                st.text(f"ID: {task['id']}")
                st.text(f"开始: {format_time(task.get('started_at', ''))}")
                
                if task.get("finished_at"):
                    st.text(f"结束: {format_time(task.get('finished_at', ''))}")
                
                if task.get("error"):
                    st.error(f"错误: {task['error']}")
            
            with col3:
                if task["status"] == "running":
                    progress = task.get("progress", 0)
                    st.progress(progress)
                    st.text(f"{task.get('completed', 0)}/{task.get('total', 0)}")
                    
                    if st.button("⏹️ 停止", key=f"stop_{task['id']}"):
                        result = api_post(f"tasks/{task['id']}/stop")
                        if result.get("success"):
                            st.success("已停止")
                            get_all_tasks.clear()
                        else:
                            st.error(f"失败: {result.get('error')}")
                        st.rerun()
                
                if st.button("🗑️ 删除", key=f"del_{task['id']}"):
                    result = api_delete(f"tasks/{task['id']}")
                    if result.get("success"):
                        st.success("已删除")
                        get_all_tasks.clear()
                    else:
                        st.error(f"删除失败: {result.get('error')}")
                    st.rerun()
            
            if show_details and task.get("details"):
                with st.expander("📋 详情", expanded=False):
                    for detail in task["details"][-20:]:
                        st.text(f"[{detail.get('time', '')}] {detail.get('message', '')}")
            
            st.divider()


def format_time(iso_str):
    """格式化时间"""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%m-%d %H:%M:%S")
    except:
        return iso_str
