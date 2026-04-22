# -*- coding: utf-8 -*-
"""
Streamlit UI 组件库
提供统一的 UI 组件和样式
"""
import streamlit as st
from typing import Callable, Any, Optional, Dict, List
from datetime import datetime


def init_session_state(defaults: Dict[str, Any]) -> None:
    """初始化 session_state 默认值"""
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_header(title: str, icon: str = "📊", subtitle: str = "") -> None:
    """渲染页面标题"""
    st.markdown(f"""
    <div class="page-header">
        <h1>{icon} {title}</h1>
        {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
    </div>
    """, unsafe_allow_html=True)


def render_metric_card(label: str, value: Any, delta: Optional[Any] = None, 
                       color: str = "#1f77b4") -> None:
    """渲染指标卡片"""
    delta_html = ""
    if delta is not None:
        delta_class = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
        delta_html = f'<span class="metric-delta {delta_class}">{delta:+.2f}</span>'
    
    st.markdown(f"""
    <div class="metric-card" style="border-left: 4px solid {color};">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def render_status_badge(status: str) -> str:
    """渲染状态徽章"""
    status_colors = {
        "success": "#28a745",
        "running": "#17a2b8", 
        "pending": "#ffc107",
        "failed": "#dc3545",
        "stopped": "#6c757d"
    }
    color = status_colors.get(status.lower(), "#6c757d")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:12px">{status.upper()}</span>'


def render_info_box(message: str, box_type: str = "info") -> None:
    """渲染信息框"""
    icons = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌"
    }
    st.info(f"{icons.get(box_type, 'ℹ️')} {message}")


def render_expander_logs(logs: List[Dict], max_display: int = 20) -> None:
    """渲染日志展开框"""
    if not logs:
        st.info("暂无日志")
        return
    
    with st.expander("📋 日志详情", expanded=True):
        for log in logs[-max_display:]:
            timestamp = log.get("time", "")
            level = log.get("level", "INFO")
            message = log.get("message", "")
            
            level_color = {
                "INFO": "#17a2b8",
                "WARNING": "#ffc107", 
                "ERROR": "#dc3545",
                "SUCCESS": "#28a745"
            }.get(level, "#6c757d")
            
            st.markdown(f"""
            <div style="font-family: monospace; font-size: 12px; padding: 4px 0;">
                <span style="color: #6c757d;">[{timestamp}]</span>
                <span style="color: {level_color}; font-weight: bold;">[{level}]</span>
                <span>{message}</span>
            </div>
            """, unsafe_allow_html=True)


def render_progress_bar(progress: float, label: str = "进度") -> None:
    """渲染进度条"""
    st.progress(progress, text=f"{label}: {progress*100:.0f}%")


def render_alpha_table(alphas: List[Dict], page_size: int = 50) -> None:
    """渲染 Alpha 表格（带分页）"""
    import pandas as pd
    
    if not alphas:
        st.info("暂无数据")
        return
    
    df = pd.DataFrame(alphas)
    
    # 分页控件
    total_pages = max(1, (len(df) + page_size - 1) // page_size)
    
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        page = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="page_input")
    with col2:
        st.write(f"共 {total_pages} 页")
    with col3:
        st.write(f"共 {len(df)} 条")
    
    # 分页显示
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    st.dataframe(
        df.iloc[start_idx:end_idx],
        use_container_width=True,
        height=min(400, len(df.iloc[start_idx:end_idx]) * 35 + 40)
    )


def render_crud_table(data: List[Dict], 
                      on_delete: Optional[Callable] = None,
                      on_edit: Optional[Callable] = None) -> None:
    """渲染带操作的表格"""
    import pandas as pd
    
    if not data:
        st.info("暂无数据")
        return
    
    df = pd.DataFrame(data)
    
    # 显示表格
    st.dataframe(df, use_container_width=True)
    
    # 操作按钮行
    if on_delete or on_edit:
        col1, col2 = st.columns(2)
        with col1:
            if on_delete:
                delete_id = st.text_input("输入要删除的 ID", key="delete_id_input")
                if st.button("🗑️ 删除", type="secondary"):
                    if delete_id and on_delete(delete_id):
                        st.success(f"已删除: {delete_id}")
                        st.rerun()
        
        with col2:
            if on_edit:
                edit_id = st.text_input("输入要编辑的 ID", key="edit_id_input")
                if st.button("✏️ 编辑", type="secondary"):
                    if edit_id and on_edit(edit_id):
                        st.rerun()


def auto_refresh(condition: Callable[[], bool], interval: int = 30) -> bool:
    """自动刷新（条件为真时）"""
    if condition():
        import time
        time.sleep(interval)
        st.rerun()
    return condition()


def render_sidebar_stats(stats: Dict[str, Any]) -> None:
    """渲染侧边栏统计信息"""
    st.subheader("📈 快速统计")
    
    for key, value in stats.items():
        st.write(f"**{key}:** {value}")
    
    st.divider()


# Streamlit 样式
STREAMLIT_STYLE = """
<style>
    /* 页面标题 */
    .page-header h1 {
        color: #1f77b4;
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    .page-header .subtitle {
        color: #6c757d;
        font-size: 1rem;
    }
    
    /* 指标卡片 */
    .metric-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
    }
    .metric-label {
        color: #6c757d;
        font-size: 0.85rem;
        text-transform: uppercase;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #212529;
    }
    .metric-delta.positive { color: #28a745; }
    .metric-delta.negative { color: #dc3545; }
    .metric-delta.neutral { color: #6c757d; }
    
    /* 表格样式 */
    .dataframe {
        font-size: 0.85rem !important;
    }
    
    /* 按钮样式优化 */
    .stButton > button {
        border-radius: 6px;
    }
    
    /* Tab 样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        border-radius: 6px 6px 0 0;
    }
    
    /* 进度条 */
    .stProgress > div > div > div {
        background-color: #1f77b4;
    }
    
    /* 侧边栏 */
    .css-1d391kg {
        background-color: #f8f9fa;
    }
</style>
"""


def apply_custom_style() -> None:
    """应用自定义样式"""
    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)


def connection_status_indicator(is_connected: bool, message: str = "") -> None:
    """渲染连接状态指示器"""
    if is_connected:
        st.success(f"✅ API 已连接 {message}")
    else:
        st.error(f"❌ API 未连接: {message}")
        st.info("💡 提示：在终端运行 `python web/run.py` 启动 FastAPI 服务器")
