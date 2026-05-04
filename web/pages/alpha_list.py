# -*- coding: utf-8 -*-
"""
Alpha 列表管理页面
功能：查看、添加、导入 Alpha 表达式
优化：添加数据缓存，减少重复查询
"""
import streamlit as st
import pandas as pd
import json


@st.cache_data(ttl=10, show_spinner=False)
def get_alpha_stats():
    """获取 Alpha 统计（10秒缓存）"""
    from web.utils.helpers import load_to_test_alphas, get_db
    
    try:
        alphas = load_to_test_alphas()
        db = get_db()
        tested = db.get_tested_count()
        return {
            "alphas": alphas,
            "tested": tested,
            "remaining": len(alphas) - min(tested, len(alphas))
        }
    except Exception as e:
        return {"alphas": [], "tested": 0, "remaining": 0, "error": str(e)}


def page_alpha_list():
    """Alpha 列表管理页面"""
    st.header("📝 Alpha 列表管理")
    
    # 加载数据（带缓存）
    stats = get_alpha_stats()
    alphas = stats["alphas"]
    
    if "error" in stats:
        st.error(f"加载失败: {stats['error']}")
        if st.button("🔄 重试"):
            get_alpha_stats.clear()
            st.rerun()
        return
    
    tab1, tab2, tab3 = st.tabs(["📄 to_test.txt", "➕ 添加 Alpha", "📤 批量导入"])
    
    with tab1:
        st.subheader("待回测 Alpha 列表 (to_test.txt)")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("文件总数量", len(alphas))
        with col2:
            st.metric("已回测(数据库)", stats["tested"])
        with col3:
            st.metric("待回测(估算)", stats["remaining"])
        
        col_refresh, col_export = st.columns([1, 4])
        with col_refresh:
            if st.button("🔄 刷新", key="refresh_alpha_list"):
                get_alpha_stats.clear()
                st.rerun()
        
        st.divider()
        
        if alphas:
            df = pd.DataFrame({
                "序号": range(1, len(alphas) + 1),
                "表达式": alphas
            })
            
            # 分页
            page_size = 50
            total_pages = max(1, (len(df) + page_size - 1) // page_size)
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                page = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="page_alpha_list")
            
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            
            st.dataframe(
                df.iloc[start_idx:end_idx],
                width='stretch',
                height=400
            )
            
            st.divider()
            
            # 删除操作
            col1, col2, col3 = st.columns(3)
            with col1:
                selected_idx = st.number_input("选择序号删除", min_value=1, max_value=max(1, len(alphas)), value=1, key="delete_idx")
            with col2:
                if st.button("🗑️ 删除选中", type="primary", key="delete_alpha_btn"):
                    if 0 < selected_idx <= len(alphas):
                        deleted = alphas.pop(selected_idx - 1)
                        from web.utils.helpers import save_to_test_alphas
                        save_to_test_alphas(alphas)
                        st.success(f"已删除: {deleted[:50]}...")
                        get_alpha_stats.clear()
                        st.rerun()
            with col3:
                if st.button("🗑️ 清空全部", type="secondary", key="clear_alpha_btn"):
                    from web.utils.helpers import save_to_test_alphas
                    save_to_test_alphas([])
                    st.success("已清空全部 Alpha")
                    get_alpha_stats.clear()
                    st.rerun()
            
            st.divider()
            
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 导出 CSV",
                csv,
                "alphas_to_test.csv",
                "text/csv",
                key="download_alpha_csv"
            )
    
    with tab2:
        st.subheader("添加新的 Alpha")
        
        new_alpha = st.text_area(
            "输入 Alpha 表达式",
            placeholder="例如: rank(-returns)",
            height=100,
            key="new_alpha_input"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            universe = st.selectbox("Universe", ["TOP3000", "TOP1000", "TOP500", "TOP200"], index=0)
        with col2:
            decay = st.number_input("Decay", min_value=0, max_value=60, value=30)
        
        col3, col4 = st.columns(2)
        with col3:
            neutralization = st.selectbox("Neutralization", ["SUBINDUSTRY", "MARKET", "SECTOR", "INDUSTRY"], index=0)
        with col4:
            truncation = st.number_input("Truncation", min_value=0.01, max_value=0.08, value=0.08, step=0.01)
        
        if st.button("➕ 添加到列表", type="primary", key="add_alpha_btn"):
            if new_alpha.strip():
                from web.utils.helpers import load_to_test_alphas, save_to_test_alphas
                
                full_alpha = f"{new_alpha.strip()} | {universe} | {decay} | {neutralization} | {truncation}"
                existing = load_to_test_alphas()
                
                expr = new_alpha.strip()
                if expr not in [a.split("|")[0].strip() for a in existing]:
                    existing.append(full_alpha)
                    save_to_test_alphas(existing)
                    st.success(f"已添加: {full_alpha[:80]}...")
                    get_alpha_stats.clear()
                    st.rerun()
                else:
                    st.warning("该表达式已存在")
            else:
                st.error("请输入 Alpha 表达式")
    
    with tab3:
        st.subheader("批量导入")
        
        uploaded_file = st.file_uploader(
            "上传文件",
            type=["txt", "csv", "json"],
            help="支持 .txt、.csv、.json 格式"
        )
        
        if uploaded_file:
            content = uploaded_file.getvalue().decode("utf-8")
            new_alphas = []
            
            if uploaded_file.name.endswith(".json"):
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        new_alphas = data
                    elif isinstance(data, dict) and "alphas" in data:
                        new_alphas = data["alphas"]
                except:
                    st.error("JSON 格式错误")
            else:
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        new_alphas.append(line)
            
            if new_alphas:
                st.info(f"发现 {len(new_alphas)} 个 Alpha")
                
                if st.button("✅ 合并到列表", type="primary", key="merge_alphas_btn"):
                    from web.utils.helpers import load_to_test_alphas, save_to_test_alphas
                    
                    existing = load_to_test_alphas()
                    existing_set = set(existing)
                    added_count = 0
                    
                    for alpha in new_alphas:
                        if alpha not in existing_set:
                            existing.append(alpha)
                            existing_set.add(alpha)
                            added_count += 1
                    
                    save_to_test_alphas(existing)
                    st.success(f"已添加 {added_count} 个新 Alpha（{len(new_alphas) - added_count} 个重复跳过）")
                    get_alpha_stats.clear()
                    st.rerun()
