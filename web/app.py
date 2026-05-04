# -*- coding: utf-8 -*-
"""
WorldQuant Alpha Manager - Streamlit Web 主入口
优化版本：使用原生多页面导航 + 数据缓存
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from pathlib import Path

# 页面配置
st.set_page_config(
    page_title="WorldQuant Alpha Manager",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义样式
st.markdown("""
<style>
    /* 隐藏顶部导航菜单 */
    [data-testid="stMainMenu"] { display: none !important; }
    
    /* 隐藏原生多页面导航 */
    [data-testid="stSidebarNav"] { display: none !important; }
    
    /* 侧边栏样式 */
    section[data-testid="stSidebar"] { background-color: #f0f2f6; }
    
    /* 页面标题 */
    .main-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #1f77b4;
        padding: 0.5rem 0;
        border-bottom: 2px solid #e9ecef;
        margin-bottom: 1rem;
    }
    
    /* 指标卡片 */
    .metric-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .metric-label { color: #6c757d; font-size: 0.85rem; }
    .metric-value { font-size: 1.5rem; font-weight: bold; color: #212529; }
    
    /* 状态颜色 */
    .success-text { color: #28a745; font-weight: bold; }
    .warning-text { color: #ffc107; font-weight: bold; }
    .danger-text { color: #dc3545; font-weight: bold; }
    
    /* Tab 样式优化 */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { 
        padding: 8px 16px; 
        border-radius: 6px 6px 0 0;
        font-size: 0.9rem;
    }
    
    /* 按钮样式 */
    .stButton > button { border-radius: 6px; }
    .stButton > button:hover { border: 1px solid #1f77b4; }
    
    /* 进度条 */
    .stProgress > div > div > div { background-color: #1f77b4; border-radius: 10px; }
    
    /* 表格行悬停 */
    .dataframe tbody tr:hover { background-color: #f0f2f6 !important; }
    
    /* 隐藏空白区域 */
    .stApp { padding: 0 1rem; }
</style>
""", unsafe_allow_html=True)


# ============ 数据缓存装饰器 ============
@st.cache_data(ttl=30, show_spinner=False)
def get_sidebar_stats():
    """获取侧边栏统计（30秒缓存）"""
    try:
        from web.utils.helpers import load_to_test_alphas, get_db
        db = get_db()
        with db._get_connection() as conn:
            total_tested = conn.execute("SELECT COUNT(*) FROM tested_expressions").fetchone()[0]
        to_test = load_to_test_alphas()
        return {
            "total_tested": total_tested,
            "to_test": len(to_test),
            "to_test_remaining": len(to_test) - min(total_tested, len(to_test))
        }
    except Exception:
        return {"total_tested": 0, "to_test": 0, "to_test_remaining": 0}


@st.cache_data(ttl=10, show_spinner=False)
def check_api_health():
    """检查 API 健康状态（10秒缓存）"""
    try:
        import requests
        resp = requests.get("http://localhost:5000/api/health", timeout=3)
        data = resp.json()
        return data.get("success", False)
    except Exception:
        return False


# ============ 侧边栏组件 ============
def render_sidebar():
    """渲染侧边栏（轻量级）"""
    with st.sidebar:
        st.markdown('<p class="main-header">📊 WorldQuant Alpha</p>', unsafe_allow_html=True)
        
        # 页面导航（使用原生 selectbox）
        pages = [
            "📝 Alpha 列表",
            "🔬 批量回测",
            "📊 回测结果",
            "📋 任务列表",
            "🎯 筛选导出",
            "🚀 Alpha 提交",
            "🧬 因子构建",
            "⚡ 一键工作流",
            "🔬 中性化组合测试",
            "📋 日志查看",
            "🗄️ 数据库管理"
        ]
        
        # 初始化当前页面
        if "current_page" not in st.session_state:
            st.session_state.current_page = pages[0]
        
        # 页面选择
        selected_page = st.selectbox(
            "选择页面",
            pages,
            index=pages.index(st.session_state.current_page) if st.session_state.current_page in pages else 0,
            key="page_selectbox"
        )
        
        # 检测页面变化
        if selected_page != st.session_state.current_page:
            st.session_state.current_page = selected_page
            st.rerun()
        
        st.divider()
        
        # 快速统计（带缓存）
        st.subheader("📈 快速统计")
        
        stats = get_sidebar_stats()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("待回测", stats["to_test"])
        with col2:
            st.metric("已回测", stats["total_tested"])
        
        # 进度条
        total = stats["to_test"] + stats["total_tested"]
        if total > 0:
            progress = stats["total_tested"] / total
            st.progress(progress, text=f"完成: {progress*100:.1f}%")
        
        st.divider()
        
        # API 状态（带缓存）
        st.subheader("🔌 API 状态")
        is_connected = check_api_health()
        
        if is_connected:
            st.success("✅ 已连接")
        else:
            st.error("❌ 未连接")
            st.caption("运行 `python web/run.py` 启动")
        
        # 刷新按钮
        if st.button("🔄 刷新状态", use_container_width=True):
            get_sidebar_stats.clear()
            check_api_health.clear()
            st.rerun()
        
        st.divider()
        
        # 配置状态
        st.subheader("⚙️ 配置")
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            with open(env_path, "r") as f:
                content = f.read()
            has_email = "BRAIN_EMAIL" in content or "WQ_USERNAME" in content
            has_password = "BRAIN_PASSWORD" in content or "WQ_PASSWORD" in content
            
            if has_email and has_password:
                st.success("✅ 账号已配置")
            elif has_email:
                st.warning("⚠️ 缺少密码")
            else:
                st.error("❌ 未配置账号")
        else:
            st.error("❌ .env 不存在")
        
        # 用户设置
        st.divider()
        st.caption("v2.0 | Alpha Manager")


# ============ 页面路由 ============
def route_page(page: str):
    """路由到指定页面"""
    # 延迟导入避免循环依赖
    from web.pages.alpha_list import page_alpha_list
    from web.pages.backtest import page_backtest
    from web.pages.results import page_results
    from web.pages.tasks import page_tasks
    from web.pages.filter import page_filter
    from web.pages.submit import page_submit
    from web.pages.factor_builder import page_factor_builder
    from web.pages.workflow import page_one_click_workflow
    from web.pages.logs import page_logs
    from web.pages.database import page_database
    
    page_handlers = {
        "📝 Alpha 列表": page_alpha_list,
        "🔬 批量回测": page_backtest,
        "📊 回测结果": page_results,
        "📋 任务列表": page_tasks,
        "🎯 筛选导出": page_filter,
        "🚀 Alpha 提交": page_submit,
        "🧬 因子构建": page_factor_builder,
        "⚡ 一键工作流": page_one_click_workflow,
        "📋 日志查看": page_logs,
        "🗄️ 数据库管理": page_database,
    }
    
    handler = page_handlers.get(page)
    if handler:
        handler()


# ============ 主函数 ============
def main():
    """主函数"""
    # 渲染侧边栏
    render_sidebar()
    
    # 获取当前页面
    current_page = st.session_state.get('current_page', '📝 Alpha 列表')
    
    # 页面标题
    st.markdown(f"""
    <div style="padding: 1rem 0; border-bottom: 2px solid #e9ecef; margin-bottom: 1rem;">
        <h1 style="color: #1f77b4; margin: 0; font-size: 1.8rem;">{current_page}</h1>
    </div>
    """, unsafe_allow_html=True)
    
    # 路由到页面
    route_page(current_page)


if __name__ == "__main__":
    main()
