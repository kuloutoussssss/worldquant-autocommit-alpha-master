# -*- coding: utf-8 -*-
"""
筛选导出页面
功能：按条件筛选 Alpha 并导出
"""
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from web.utils.helpers import get_db


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
        
        display_df = qualified[["alpha_id", "sharpe", "fitness", "turnover", "returns", "drawdown", "expression"]].copy()
        display_df = display_df.round(4)
        
        st.dataframe(
            display_df,
            width='stretch',
            height=400
        )
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            csv_data = qualified.to_csv(index=False)
            st.download_button(
                "📥 导出为 CSV",
                csv_data,
                f"qualified_alphas_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
                type="primary"
            )
        
        with col2:
            txt_content = "\n".join(qualified["expression"].tolist())
            st.download_button(
                "📥 导出为 TXT",
                txt_content,
                f"qualified_alphas_{datetime.now().strftime('%Y%m%d')}.txt",
                "text/plain"
            )
        
        alpha_ids = qualified["alpha_id"].dropna().tolist()
        if alpha_ids:
            ids_content = "\n".join(alpha_ids)
            st.download_button(
                "📥 导出 Alpha ID 列表",
                ids_content,
                f"alpha_ids_{datetime.now().strftime('%Y%m%d')}.txt",
                "text/plain"
            )
    else:
        st.warning("没有符合条件的 Alpha")
