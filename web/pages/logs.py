# -*- coding: utf-8 -*-
"""
日志查看页面
功能：查看、搜索、过滤日志文件
"""
import streamlit as st
from pathlib import Path
from datetime import datetime
from web.utils.helpers import get_db


def page_logs():
    """日志查看页面"""
    st.header("📋 日志查看")
    
    if 'log_selected_file' not in st.session_state:
        st.session_state.log_selected_file = None
    if 'log_search_text' not in st.session_state:
        st.session_state.log_search_text = ""
    if 'log_level' not in st.session_state:
        st.session_state.log_level = "全部"
    if 'log_page' not in st.session_state:
        st.session_state.log_page = 1
    
    logs_dir = Path(__file__).parent.parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    log_files = sorted(logs_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not log_files:
        st.info("暂无日志文件")
        return
    
    if st.session_state.log_selected_file is None or st.session_state.log_selected_file not in [f.name for f in log_files]:
        st.session_state.log_selected_file = log_files[0].name
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        file_options = [f.name for f in log_files]
        selected_idx = file_options.index(st.session_state.log_selected_file) if st.session_state.log_selected_file in file_options else 0
        selected_file = st.selectbox(
            "选择日志文件",
            file_options,
            index=selected_idx,
            key="log_file_select"
        )
        if selected_file != st.session_state.log_selected_file:
            st.session_state.log_selected_file = selected_file
            st.session_state.log_page = 1
            st.rerun()
    
    log_path = logs_dir / st.session_state.log_selected_file
    file_size = log_path.stat().st_size
    file_mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
    
    with col2:
        st.metric("文件大小", f"{file_size / 1024 / 1024:.2f} MB" if file_size > 1024*1024 else f"{file_size / 1024:.2f} KB")
    
    with col3:
        st.metric("修改时间", file_mtime.strftime("%Y-%m-%d %H:%M"))
    
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        search_text = st.text_input(
            "🔍 搜索日志内容", 
            value=st.session_state.log_search_text,
            placeholder="输入关键词搜索...",
            key="log_search_input"
        )
        if search_text != st.session_state.log_search_text:
            st.session_state.log_search_text = search_text
            st.session_state.log_page = 1
    with col2:
        level_options = ["全部", "ERROR", "WARNING", "INFO", "DEBUG"]
        level_idx = level_options.index(st.session_state.log_level) if st.session_state.log_level in level_options else 0
        log_level = st.selectbox(
            "日志级别",
            level_options,
            index=level_idx,
            key="log_level_select"
        )
        if log_level != st.session_state.log_level:
            st.session_state.log_level = log_level
            st.session_state.log_page = 1
    
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        st.error(f"读取日志文件失败: {e}")
        return
    
    filtered_lines = []
    for line in lines:
        if st.session_state.log_search_text and st.session_state.log_search_text.lower() not in line.lower():
            continue
        if st.session_state.log_level != "全部":
            level_pattern = f"[{st.session_state.log_level}]"
            if level_pattern not in line and f"_{st.session_state.log_level}_" not in line:
                continue
        filtered_lines.append(line.rstrip())
    
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总行数", len(lines))
    with col2:
        st.metric("过滤后", len(filtered_lines))
    with col3:
        error_count = sum(1 for l in lines if "[ERROR]" in l or "_ERROR_" in l)
        st.metric("错误数", error_count)
    
    st.divider()
    
    page_size = 100
    total_pages = max(1, (len(filtered_lines) + page_size - 1) // page_size)
    
    if st.session_state.log_page > total_pages:
        st.session_state.log_page = total_pages
    
    col1, col2 = st.columns([1, 3])
    with col1:
        page = st.number_input(
            "页码", 
            min_value=1, 
            max_value=total_pages, 
            value=st.session_state.log_page,
            key="log_page_input"
        )
        if page != st.session_state.log_page:
            st.session_state.log_page = page
    with col2:
        st.write(f"共 {total_pages} 页，每页 {page_size} 行")
    
    start_idx = (st.session_state.log_page - 1) * page_size
    end_idx = min(start_idx + page_size, len(filtered_lines))
    page_lines = filtered_lines[start_idx:end_idx]
    
    if page_lines:
        log_display = []
        for line in page_lines:
            if "[ERROR]" in line or "_ERROR_" in line:
                log_display.append(f"🔴 {line}")
            elif "[WARNING]" in line or "_WARNING_" in line:
                log_display.append(f"🟡 {line}")
            elif "[INFO]" in line or "_INFO_" in line:
                log_display.append(f"🔵 {line}")
            elif "[DEBUG]" in line or "_DEBUG_" in line:
                log_display.append(f"⚪ {line}")
            else:
                log_display.append(line)
        
        st.code("\n".join(log_display), language=None)
    else:
        st.info("没有匹配的日志内容")
    
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        if page_lines:
            content = "\n".join(page_lines)
            st.download_button(
                "📥 导出当前页",
                content,
                f"{st.session_state.log_selected_file.replace('.log', '')}_page{st.session_state.log_page}.txt",
                "text/plain"
            )
    
    with col2:
        if filtered_lines:
            content = "\n".join(filtered_lines)
            st.download_button(
                "📥 导出过滤结果",
                content,
                f"{st.session_state.log_selected_file.replace('.log', '')}_filtered.txt",
                "text/plain"
            )
    
    st.divider()
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 刷新日志", key="refresh_log_btn"):
            st.session_state.log_search_text = ""
            st.session_state.log_page = 1
            log_files_new = sorted(logs_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
            if log_files_new:
                st.session_state.log_selected_file = log_files_new[0].name
            st.rerun()
