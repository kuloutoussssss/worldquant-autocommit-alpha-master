# -*- coding: utf-8 -*-
"""
数据库管理页面
功能：查看统计、清理数据、导入历史
优化：添加缓存
"""
import streamlit as st
from pathlib import Path


@st.cache_data(ttl=30, show_spinner=False)
def get_db_stats():
    """获取数据库统计（30秒缓存）"""
    from web.utils.helpers import get_db
    
    db = get_db()
    try:
        with db._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM alphas").fetchone()[0]
            tested = conn.execute("SELECT COUNT(*) FROM tested_expressions").fetchone()[0]
            qualified = conn.execute("SELECT COUNT(*) FROM tested_expressions WHERE sharpe >= 1.25 AND fitness >= 1.0 AND turnover <= 0.7").fetchone()[0]
            submitted = conn.execute("SELECT COUNT(*) FROM alphas WHERE submitted_at IS NOT NULL").fetchone()[0]
        
        return {
            "total": total,
            "tested": tested,
            "qualified": qualified,
            "submitted": submitted
        }
    except Exception as e:
        return {"error": str(e)}


def page_database():
    """数据库管理页面"""
    st.header("🗄️ 数据库管理")
    
    stats = get_db_stats()
    
    if "error" in stats:
        st.error(f"加载失败: {stats['error']}")
        if st.button("🔄 重试"):
            get_db_stats.clear()
            st.rerun()
        return
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Alpha 总数", stats["total"])
    with col2:
        st.metric("已回测", stats["tested"])
    with col3:
        st.metric("达标", stats["qualified"])
    with col4:
        st.metric("已提交", stats["submitted"])
    
    col_refresh, col_space = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 刷新统计"):
            get_db_stats.clear()
            st.rerun()
    
    st.divider()
    
    st.subheader("📂 数据库操作")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧹 清理重复数据", type="secondary"):
            from web.utils.helpers import get_db
            db = get_db()
            try:
                deleted = db.cleanup_duplicate_tested_expressions()
                st.success(f"已删除 {deleted} 条重复记录")
                get_db_stats.clear()
            except Exception as e:
                st.error(f"清理失败: {e}")
    
    with col2:
        if st.button("🗑️ 清空回测历史", type="secondary"):
            if st.confirm("确定要清空所有回测历史吗？此操作不可恢复"):
                from web.utils.helpers import get_db
                db = get_db()
                try:
                    with db._get_connection() as conn:
                        conn.execute("DELETE FROM tested_expressions")
                        conn.commit()
                    st.success("已清空回测历史")
                    get_db_stats.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"清空失败: {e}")
    
    st.divider()
    
    st.subheader("📂 导入历史数据")
    st.caption("从本地 JSON 文件导入回测结果")
    
    results_dir = Path(__file__).parent.parent.parent / "data" / "results"
    
    if results_dir.exists():
        json_files = list(results_dir.glob("*.json"))
        
        if json_files:
            selected_file = st.selectbox(
                "选择要导入的文件",
                [str(f.relative_to(results_dir.parent.parent.parent)) for f in json_files],
                key="import_file_select"
            )
            
            if st.button("📥 导入选中的文件", type="primary"):
                full_path = results_dir.parent.parent.parent / selected_file
                from web.utils.helpers import get_db
                db = get_db()
                try:
                    count = db.import_batch_results(str(full_path))
                    st.success(f"成功导入 {count} 条记录")
                    get_db_stats.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"导入失败: {e}")
        else:
            st.info("results 目录中没有 JSON 文件")
    else:
        st.info("results 目录不存在")
