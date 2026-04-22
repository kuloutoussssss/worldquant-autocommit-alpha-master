# -*- coding: utf-8 -*-
"""
回测结果页面
功能：查看、回测结果可视化
优化：添加数据缓存
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime


@st.cache_data(ttl=30, show_spinner="加载数据...")
def get_backtest_results():
    """获取回测结果（30秒缓存）"""
    from web.utils.helpers import get_db
    
    db = get_db()
    with db._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT * FROM tested_expressions 
            ORDER BY test_time DESC
        """)
        rows = [dict(row) for row in cursor.fetchall()]
    
    return rows


def page_results():
    """结果可视化页面"""
    st.header("📊 回测结果")
    
    # 获取数据（带缓存）
    rows = get_backtest_results()
    
    if not rows:
        st.info("暂无回测数据，请先执行回测")
        
        if st.button("🔄 刷新"):
            get_backtest_results.clear()
            st.rerun()
        return
    
    df = pd.DataFrame(rows)
    
    # 统计信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总回测数", len(df))
    
    success_df = df[df["status"] == "OK"]
    with col2:
        st.metric("成功", len(success_df))
    
    avg_sharpe = success_df["sharpe"].mean() if len(success_df) > 0 else 0
    with col3:
        st.metric("平均 Sharpe", f"{avg_sharpe:.2f}")
    
    qualified = len(success_df[
        (success_df["sharpe"] >= 1.25) & 
        (success_df["fitness"] >= 1.0) &
        (success_df["turnover"] <= 0.7)
    ])
    with col4:
        st.metric("达标", qualified)
    
    # 刷新按钮
    col_refresh, col_export = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 刷新数据"):
            get_backtest_results.clear()
            st.rerun()
    
    st.divider()
    
    # 筛选条件
    st.subheader("🔍 筛选条件")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        min_sharpe = st.number_input("最小 Sharpe", min_value=-10.0, max_value=100.0, value=-10.0, step=0.1, key="min_sharpe")
    with col2:
        min_fitness = st.number_input("最小 Fitness", min_value=-10.0, max_value=100.0, value=-10.0, step=0.1, key="min_fitness")
    with col3:
        max_turnover = st.number_input("最大 Turnover", min_value=0.0, max_value=10.0, value=10.0, step=0.1, key="max_turnover")
    
    filtered = df[
        (df["sharpe"] >= min_sharpe) &
        (df["fitness"] >= min_fitness) &
        (df["turnover"] <= max_turnover) &
        (df["status"] == "OK")
    ]
    
    st.divider()
    
    tab1, tab2, tab3 = st.tabs(["📈 统计图表", "📋 数据表格", "🏆 Top Alpha"])
    
    with tab1:
        st.subheader("Sharpe 分布")
        
        if len(filtered) > 0:
            fig = px.histogram(
                filtered, 
                x="sharpe",
                nbins=50,
                title="Sharpe 分布",
                labels={"sharpe": "Sharpe", "count": "数量"}
            )
            fig.add_vline(x=1.25, line_dash="dash", annotation_text="达标线 1.25", line_color="red")
            st.plotly_chart(fig, width='stretch')
            
            fig2 = px.scatter(
                filtered.head(500),
                x="sharpe",
                y="fitness",
                size="turnover",
                color="returns",
                title="Sharpe vs Fitness",
                labels={"sharpe": "Sharpe", "fitness": "Fitness"}
            )
            st.plotly_chart(fig2, width='stretch')
        else:
            st.info("没有符合条件的数据")
    
    with tab2:
        st.subheader(f"数据表格 (共 {len(filtered)} 条)")
        
        display_df = filtered[["id", "expression", "sharpe", "fitness", "turnover", "returns", "drawdown", "test_time"]].copy()
        display_df["expression"] = display_df["expression"].apply(lambda x: x[:80] + "..." if len(str(x)) > 80 else x)
        
        st.dataframe(
            display_df,
            width='stretch',
            height=400
        )
        
        csv = display_df.to_csv(index=False)
        st.download_button(
            "📥 导出 CSV",
            csv,
            f"backtest_results_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv"
        )
    
    with tab3:
        st.subheader("Top 20 Alpha")
        
        top = filtered.nlargest(20, "sharpe")[["alpha_id", "sharpe", "fitness", "turnover", "returns", "drawdown", "expression"]]
        
        for i, row in top.iterrows():
            with st.expander(f"#{list(top.index).index(i)+1} Sharpe: {row['sharpe']:.3f}"):
                st.code(row["expression"], language=None)
