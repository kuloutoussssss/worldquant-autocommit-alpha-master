# -*- coding: utf-8 -*-
"""
筛选导出页面
功能：按条件筛选 Alpha 并导出，支持批量中性化回测
"""
import streamlit as st
import pandas as pd
import sqlite3
import requests
import os
from pathlib import Path
from datetime import datetime
from web.utils.helpers import get_db
from web.utils.api_client_st import API_BASE


def load_env_file():
    """从 .env 文件加载环境变量"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())


def get_self_corr_calculator_page():
    """获取或初始化自相关计算器"""
    # 加载 .env 文件
    load_env_file()

    if 'self_corr_calc' not in st.session_state:
        username = os.environ.get("WQ_USERNAME") or os.environ.get("WORLDQUANT_USERNAME")
        password = os.environ.get("WQ_PASSWORD") or os.environ.get("WORLDQUANT_PASSWORD")

        if username and password:
            try:
                from core.self_correlation import get_self_corr_calculator
                st.session_state.self_corr_calc = get_self_corr_calculator(username, password)
                # 加载本地数据
                st.session_state.self_corr_calc.load_data(tag='SelfCorr')
            except Exception as e:
                st.session_state.self_corr_calc = None
                st.warning(f"自相关计算器初始化失败: {e}")
        else:
            st.session_state.self_corr_calc = None

    return st.session_state.self_corr_calc


def page_filter():
    """筛选导出页面"""
    st.header("🎯 筛选与导出")

    # 自相关计算器初始化
    self_corr_calc = get_self_corr_calculator_page()

    # 自相关配置区域
    with st.expander("📊 自相关计算配置", expanded=not self_corr_calc):
        if self_corr_calc:
            st.success("✅ 已连接到 WorldQuant Brain")
            if st.button("🔄 重新加载数据"):
                try:
                    st.session_state.self_corr_calc.load_data(tag='SelfCorr')
                    st.success("数据重新加载成功！")
                    st.rerun()
                except Exception as e:
                    st.error(f"重新加载失败: {e}")
        else:
            # 尝试从 .env 获取账户信息
            username = os.environ.get("WQ_USERNAME", "")
            password = os.environ.get("WQ_PASSWORD", "")

            if username and password:
                st.info("正在自动连接...")
                if st.button("🔗 连接并加载数据"):
                    with st.spinner("正在加载 OS Alpha 数据..."):
                        try:
                            from core.self_correlation import get_self_corr_calculator
                            st.session_state.self_corr_calc = get_self_corr_calculator(username, password)
                            st.session_state.self_corr_calc.load_data(tag='SelfCorr')
                            st.success("数据加载成功！可以开始计算自相关了")
                            st.rerun()
                        except Exception as e:
                            st.error(f"加载失败: {e}")
            else:
                st.warning("⚠️ 未找到 WorldQuant 账户信息，请设置 .env 文件中的 WQ_USERNAME 和 WQ_PASSWORD")
                with st.expander("查看 .env 配置示例"):
                    st.code("""# .env 文件
WQ_USERNAME=your_email@gmail.com
WQ_PASSWORD=your_password""")

    db = get_db()

    # 获取 alphas 表数据
    with db._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT alpha_id, expression, sharpe, fitness, turnover, returns, drawdown
            FROM alphas
            ORDER BY sharpe DESC
        """)
        rows = [dict(row) for row in cursor.fetchall()]

    if not rows:
        st.info("暂无回测数据")
        return

    df = pd.DataFrame(rows)

    # 获取自相关数据（从 tested_expressions 表）
    with db._get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT alpha_id, expression, self_corr
            FROM tested_expressions
            WHERE self_corr >= 0
        """)
        self_corr_rows = {row['expression']: row['self_corr'] for row in cursor.fetchall()}

    # 将自相关数据合并到 df
    df['self_corr'] = df['expression'].map(self_corr_rows).fillna(-1)
    
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

    # 自相关筛选（只显示有数据的 Alpha）
    has_self_corr = df['self_corr'] >= 0
    if has_self_corr.any():
        col6, col7 = st.columns(2)
        with col6:
            max_self_corr = st.slider(
                "自相关 ≤",
                min_value=0.0,
                max_value=1.0,
                value=1.0,
                step=0.01,
                help="只显示自相关值低于此阈值的 Alpha"
            )
    else:
        max_self_corr = 1.0
        st.caption("💡 暂无自相关数据，需要先下载 OS Alpha 数据")
    
    # 筛选条件：自相关条件只对有数据的 Alpha 生效
    # 没有自相关数据的 Alpha（self_corr=-1）不受自相关筛选影响
    self_corr_condition = (
        (df["self_corr"] < 0) |  # 没有自相关数据的直接通过
        (df["self_corr"] <= max_self_corr)  # 有数据的需要满足阈值
    )

    qualified = df[
        (df["sharpe"] >= min_sharpe) &
        (df["fitness"] >= min_fitness) &
        (df["turnover"] <= max_turnover) &
        (df["returns"] >= min_returns) &
        (df["drawdown"] <= max_drawdown) &
        self_corr_condition
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
        
        # 初始化 session state
        if 'selected_alphas' not in st.session_state:
            st.session_state.selected_alphas = set()
        if 'neutralization_results' not in st.session_state:
            st.session_state.neutralization_results = {}
        
        # 显示表格，带勾选框
        display_df = qualified[["alpha_id", "sharpe", "fitness", "turnover", "returns", "drawdown", "self_corr", "expression"]].copy()
        display_df = display_df.round(4)

        # 格式化自相关列：-1 显示为 "N/A"
        display_df["self_corr"] = display_df["self_corr"].apply(
            lambda x: "N/A" if x < 0 else f"{x:.3f}"
        )

        # 添加选择列（放在第一列）
        display_df.insert(0, "_selected", display_df["alpha_id"].isin(st.session_state.selected_alphas))

        # 使用列配置创建带勾选框的表格
        col_config = {
            "_selected": st.column_config.CheckboxColumn("选择", width="small"),
            "alpha_id": st.column_config.TextColumn("Alpha ID", width="medium"),
            "sharpe": st.column_config.NumberColumn("Sharpe", format="%.3f", width="small"),
            "fitness": st.column_config.NumberColumn("Fitness", format="%.3f", width="small"),
            "turnover": st.column_config.NumberColumn("换手率", format="%.3f", width="small"),
            "returns": st.column_config.NumberColumn("收益", format="%.4f", width="small"),
            "drawdown": st.column_config.NumberColumn("回撤", format="%.3f", width="small"),
            "self_corr": st.column_config.TextColumn("自相关", width="small"),
            "expression": st.column_config.TextColumn("表达式", width="large"),
        }

        # 显示可编辑的表格
        edited_df = st.data_editor(
            display_df,
            column_config=col_config,
            hide_index=True,
            height=400,
            key="alpha_selection",
            disabled=["alpha_id", "sharpe", "fitness", "turnover", "returns", "drawdown", "self_corr", "expression"]
        )

        # 获取当前选中的行并更新 session state
        if "_selected" in edited_df.columns:
            newly_selected = edited_df[edited_df["_selected"] == True]["alpha_id"].tolist()
            st.session_state.selected_alphas = set(newly_selected)

        selected_rows = display_df[display_df['alpha_id'].isin(st.session_state.selected_alphas)]

        # 自相关计算区域
        st.divider()
        st.subheader("📊 自相关计算")

        # 找出还没有自相关数据的 Alpha
        needs_calc = qualified[qualified['self_corr'] < 0]['alpha_id'].tolist()
        has_calc = qualified[qualified['self_corr'] >= 0]['alpha_id'].tolist()

        col_sc1, col_sc2, col_sc3 = st.columns(3)
        with col_sc1:
            st.metric("待计算", len(needs_calc))
        with col_sc2:
            st.metric("已计算", len(has_calc))
        with col_sc3:
            if self_corr_calc:
                st.success("✅ 已连接")
            else:
                st.warning("⚠️ 未连接")

        # 计算按钮
        calc_col1, calc_col2 = st.columns(2)

        with calc_col1:
            if st.button(f"🔍 计算所选 Alpha 的自相关 ({len(st.session_state.selected_alphas)})", 
                        use_container_width=True, disabled=not self_corr_calc):
                if st.session_state.selected_alphas:
                    selected_to_calc = [aid for aid in st.session_state.selected_alphas 
                                       if aid in needs_calc]
                    if selected_to_calc:
                        with st.spinner(f"正在计算 {len(selected_to_calc)} 个 Alpha..."):
                            for i, alpha_id in enumerate(selected_to_calc):
                                try:
                                    # 获取 Alpha PnL
                                    alpha_pnl = self_corr_calc.get_alpha_pnl_by_id(alpha_id, "USA")
                                    if alpha_pnl is not None and len(alpha_pnl) >= 60:
                                        # 计算自相关
                                        self_corr = self_corr_calc.calc_self_corr(
                                            alpha_pnl, 
                                            self_corr_calc._os_alpha_pnls
                                        )
                                        # 保存到数据库
                                        db.update_self_corr(
                                            qualified[qualified['alpha_id'] == alpha_id]['expression'].values[0],
                                            self_corr
                                        )
                                        st.info(f"[{i+1}/{len(selected_to_calc)}] {alpha_id}: {self_corr:.4f}")
                                    else:
                                        st.warning(f"[{i+1}/{len(selected_to_calc)}] {alpha_id}: 无法获取 PnL 数据")
                                except Exception as e:
                                    st.warning(f"[{i+1}/{len(selected_to_calc)}] {alpha_id}: {e}")
                        st.success("计算完成！")
                        st.rerun()
                    else:
                        st.info("所选 Alpha 已有自相关数据")

        with calc_col2:
            if st.button(f"📊 计算全部待计算 Alpha ({len(needs_calc)})", 
                        use_container_width=True, disabled=not self_corr_calc):
                if needs_calc:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    for i, alpha_id in enumerate(needs_calc):
                        status_text.text(f"计算中: {alpha_id} ({i+1}/{len(needs_calc)})")
                        progress_bar.progress((i + 1) / len(needs_calc))
                        try:
                            alpha_pnl = self_corr_calc.get_alpha_pnl_by_id(alpha_id, "USA")
                            if alpha_pnl is not None and len(alpha_pnl) >= 60:
                                self_corr = self_corr_calc.calc_self_corr(
                                    alpha_pnl, 
                                    self_corr_calc._os_alpha_pnls
                                )
                                db.update_self_corr(
                                    qualified[qualified['alpha_id'] == alpha_id]['expression'].values[0],
                                    self_corr
                                )
                            else:
                                db.update_self_corr(
                                    qualified[qualified['alpha_id'] == alpha_id]['expression'].values[0],
                                    -1
                                )
                        except Exception as e:
                            db.update_self_corr(
                                qualified[qualified['alpha_id'] == alpha_id]['expression'].values[0],
                                -1
                            )
                    progress_bar.empty()
                    status_text.empty()
                    st.success(f"批量计算完成！共处理 {len(needs_calc)} 个 Alpha")
                    st.rerun()

        st.divider()

        # 操作按钮区
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("已选中", len(st.session_state.selected_alphas))

        with col2:
            if st.button("🔄 刷新选中", use_container_width=True):
                st.rerun()

        with col3:
            if st.button("🗑️ 清除选中", use_container_width=True):
                st.session_state.selected_alphas = set()
                st.rerun()

        with col4:
            if st.button("✅ 全选", use_container_width=True):
                st.session_state.selected_alphas = set(qualified['alpha_id'].dropna().tolist())
                st.rerun()

        st.divider()

        # 单个 Alpha 中性化测试（从 neutralization.py 整合）
        with st.expander("🔬 单个 Alpha 中性化测试"):
            st.markdown("""
            **功能说明**：测试 Alpha 在不同中性化方式 × maxTrade 组合下的表现

            **优质Alpha筛选条件**：
            1. 换手率 ≤ 0.4, Sharpe ≥ 1.2, Margin ≥ 0.0009
            2. 换手率 ≤ 0.4, Sharpe ≥ 1.5, Margin ≥ 0.001
            3. 换手率 ≤ 0.6, Sharpe ≥ 2.0, Margin ≥ 0.0015
            """)

            single_col1, single_col2 = st.columns(2)
            with single_col1:
                single_alpha_id = st.text_input(
                    "Alpha ID",
                    placeholder="输入 Alpha ID，例如: KPwOMNk1",
                    key="single_neut_alpha_id"
                )

            with single_col2:
                single_region = st.selectbox(
                    "区域",
                    options=["USA", "CHN", "CHN_A", "IND", "EUR"],
                    index=0,
                    key="single_neut_region"
                )

            if single_alpha_id:
                if st.button("开始测试", type="primary", use_container_width=True, key="single_neut_test"):
                    with st.spinner("测试中，请稍候..."):
                        try:
                            response = requests.post(
                                f"{API_BASE}/api/neutralization/test",
                                json={"alpha_id": single_alpha_id, "region": single_region},
                                timeout=300
                            )

                            if response.status_code == 200:
                                data = response.json()
                                if data.get('success'):
                                    results = data.get('results', [])
                                    summary = data.get('summary', {})

                                    st.success("测试完成！")

                                    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                                    with m_col1:
                                        st.metric("总组合数", summary.get('total_combinations', 0))
                                    with m_col2:
                                        st.metric("成功完成", summary.get('completed', 0))
                                    with m_col3:
                                        st.metric("优质Alpha", summary.get('quality_count', 0))
                                    with m_col4:
                                        st.metric("最佳Sharpe", f"{summary.get('best_sharpe', 0):.3f}")

                                    if results:
                                        df = pd.DataFrame(results)
                                        df_display = df[['neutralization', 'max_trade', 'sharpe', 'fitness', 'turnover', 'margin', 'is_quality', 'status']].copy()
                                        df_display.columns = ['中性化', 'maxTrade', 'Sharpe', 'Fitness', '换手率', 'Margin', '优质', '状态']
                                        df_display['Sharpe'] = df_display['Sharpe'].apply(lambda x: f"{x:.3f}")
                                        df_display['Fitness'] = df_display['Fitness'].apply(lambda x: f"{x:.3f}")
                                        df_display['换手率'] = df_display['换手率'].apply(lambda x: f"{x:.3f}")
                                        df_display['Margin'] = df_display['Margin'].apply(lambda x: f"{x:.6f}")
                                        df_display['优质'] = df_display['优质'].apply(lambda x: '★' if x else '')
                                        st.dataframe(df_display, use_container_width=True)

                                    quality_alphas = summary.get('quality_alphas', [])
                                    if quality_alphas:
                                        st.markdown("### 优质Alpha")
                                        for qa in quality_alphas:
                                            st.markdown(f"""
                                            - **Alpha ID**: {qa.get('alpha_id', 'N/A')}
                                            - **中性化**: {qa.get('neutralization')} / {qa.get('max_trade')}
                                            - **Sharpe**: {qa.get('sharpe', 0):.3f}
                                            - **Fitness**: {qa.get('fitness', 0):.3f}
                                            """)
                                else:
                                    st.error(f"测试失败: {data.get('error', '未知错误')}")
                            else:
                                st.error(f"请求失败: {response.status_code}")
                        except Exception as e:
                            st.error(f"测试异常: {e}")

            # 优质条件检查器
            st.divider()
            st.subheader("优质Alpha条件检查器")
            check_col1, check_col2, check_col3 = st.columns(3)
            with check_col1:
                check_sharpe = st.number_input("Sharpe", value=1.5, step=0.1, key="check_sharpe")
            with check_col2:
                check_turnover = st.number_input("换手率", value=0.4, step=0.05, max_value=1.0, key="check_turnover")
            with check_col3:
                check_margin = st.number_input("Margin", value=0.001, step=0.0001, key="check_margin")

            if st.button("检查是否符合优质条件", key="check_quality"):
                try:
                    response = requests.post(
                        f"{API_BASE}/api/neutralization/quality-check",
                        json={"sharpe": check_sharpe, "turnover": check_turnover, "margin": check_margin},
                        timeout=10
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('success'):
                            if data.get('is_quality'):
                                st.success(f"✓ 符合优质条件！匹配条件 {data.get('matched_condition')}")
                            else:
                                st.error("✗ 不符合优质条件")
                        else:
                            st.error("检查失败")
                except Exception as e:
                    st.error(f"检查失败: {e}")

        # 中性化回测区域
        st.subheader("⚡ 批量中性化回测")

        # 中性化配置
        neut_col1, neut_col2, neut_col3 = st.columns(3)
        with neut_col1:
            neutralization_region = st.selectbox(
                "区域",
                options=["USA", "CHN", "CHN_A", "IND", "EUR"],
                index=0,
                help="选择中性化回测的区域"
            )
        with neut_col2:
            max_trade_mode = st.selectbox(
                "maxTrade",
                options=["BOTH", "ON", "OFF"],
                index=0,
                help="BOTH: 测试ON和OFF两种模式"
            )
        with neut_col3:
            concurrency = st.number_input(
                "并发数",
                min_value=1,
                max_value=5,
                value=1,
                help="同时测试的组合数"
            )
        
        # 中性化按钮
        if len(st.session_state.selected_alphas) > 0:
            if st.button(f"🚀 批量中性化回测 ({len(st.session_state.selected_alphas)} 个)", type="primary", use_container_width=True):
                selected_alpha_ids = list(st.session_state.selected_alphas)
                progress_bar = st.progress(0, text="准备开始...")
                status_text = st.empty()
                
                all_results = []
                total = len(selected_alpha_ids)
                
                for idx, alpha_id in enumerate(selected_alpha_ids):
                    status_text.text(f"正在中性化回测 [{idx+1}/{total}]: {alpha_id}")
                    progress_bar.progress((idx + 1) / total)
                    
                    try:
                        # 获取 Alpha 信息
                        alpha_response = requests.get(f"{API_BASE}/database/alphas/{alpha_id}", timeout=30)
                        if alpha_response.status_code == 200:
                            alpha_data = alpha_response.json()
                            # 从返回的 alpha 对象中获取 expression
                            alpha_obj = alpha_data.get('alpha', {})
                            expression = alpha_obj.get('expression', '')
                            
                            if expression:
                                # 调用中性化测试
                                neut_response = requests.post(
                                    f"{API_BASE}/api/neutralization/test",
                                    json={
                                        "alpha_id": alpha_id,
                                        "expression": expression,
                                        "region": neutralization_region,
                                        "concurrency": concurrency
                                    },
                                    timeout=600
                                )
                                
                                if neut_response.status_code == 200:
                                    result = neut_response.json()
                                    all_results.append({
                                        'alpha_id': alpha_id,
                                        'status': 'success',
                                        'results': result.get('results', []),
                                        'summary': result.get('summary', {})
                                    })
                                else:
                                    all_results.append({
                                        'alpha_id': alpha_id,
                                        'status': 'error',
                                        'error': f"HTTP {neut_response.status_code}"
                                    })
                            else:
                                all_results.append({
                                    'alpha_id': alpha_id,
                                    'status': 'error',
                                    'error': '表达式为空'
                                })
                        else:
                            all_results.append({
                                'alpha_id': alpha_id,
                                'status': 'error',
                                'error': f'获取Alpha失败: {alpha_response.status_code}'
                            })
                    except Exception as e:
                        all_results.append({
                            'alpha_id': alpha_id,
                            'status': 'error',
                            'error': str(e)
                        })
                
                # 保存结果
                st.session_state.neutralization_results = all_results
                progress_bar.empty()
                status_text.empty()
                
                # 显示结果
                st.success(f"中性化回测完成！处理了 {len(all_results)} 个 Alpha")
        
        # 显示中性化结果
        if st.session_state.neutralization_results:
            st.divider()
            st.subheader("📊 中性化回测结果")
            
            # 汇总统计
            success_count = sum(1 for r in st.session_state.neutralization_results if r.get('status') == 'success')
            total_results = sum(len(r.get('results', [])) for r in st.session_state.neutralization_results if r.get('status') == 'success')
            quality_count = sum(r.get('summary', {}).get('quality_count', 0) for r in st.session_state.neutralization_results)
            
            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
            with stat_col1:
                st.metric("成功", success_count)
            with stat_col2:
                st.metric("失败", len(st.session_state.neutralization_results) - success_count)
            with stat_col3:
                st.metric("总组合数", total_results)
            with stat_col4:
                st.metric("优质Alpha", quality_count)
            
            # 详细结果表格
            all_combos = []
            for r in st.session_state.neutralization_results:
                if r.get('status') == 'success':
                    for combo in r.get('results', []):
                        all_combos.append({
                            '原Alpha': r['alpha_id'],
                            '中性化': combo.get('neutralization', ''),
                            'maxTrade': combo.get('max_trade', ''),
                            'Sharpe': combo.get('sharpe', 0),
                            'Fitness': combo.get('fitness', 0),
                            '换手率': combo.get('turnover', 0),
                            'Margin': combo.get('margin', 0),
                            '优质': '★' if combo.get('is_quality') else ''
                        })
            
            if all_combos:
                result_df = pd.DataFrame(all_combos)
                result_df = result_df.sort_values('Sharpe', ascending=False)
                result_df['Sharpe'] = result_df['Sharpe'].round(3)
                result_df['Fitness'] = result_df['Fitness'].round(3)
                result_df['换手率'] = result_df['换手率'].round(3)
                result_df['Margin'] = result_df['Margin'].round(6)
                
                st.dataframe(result_df, use_container_width=True, height=400)
                
                # 导出中性化结果
                csv_data = result_df.to_csv(index=False)
                st.download_button(
                    "📥 导出中性化结果",
                    csv_data,
                    f"neutralization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv",
                    type="primary"
                )
            
            # 显示失败的 Alpha
            failed = [r for r in st.session_state.neutralization_results if r.get('status') != 'success']
            if failed:
                st.warning(f"以下 Alpha 中性化失败：")
                for f in failed:
                    st.write(f"- **{f['alpha_id']}**: {f.get('error', '未知错误')}")
        
        st.divider()
        
        # 导出区域
        export_col1, export_col2, export_col3 = st.columns(3)
        with export_col1:
            csv_data = qualified.to_csv(index=False)
            st.download_button(
                "📥 导出为 CSV",
                csv_data,
                f"qualified_alphas_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
                type="primary"
            )
        
        with export_col2:
            txt_content = "\n".join(qualified["expression"].tolist())
            st.download_button(
                "📥 导出为 TXT",
                txt_content,
                f"qualified_alphas_{datetime.now().strftime('%Y%m%d')}.txt",
                "text/plain"
            )
        
        with export_col3:
            alpha_ids = qualified["alpha_id"].dropna().tolist()
            if alpha_ids:
                ids_content = "\n".join(alpha_ids)
                st.download_button(
                    "📥 导出 Alpha ID",
                    ids_content,
                    f"alpha_ids_{datetime.now().strftime('%Y%m%d')}.txt",
                    "text/plain"
                )
    else:
        st.warning("没有符合条件的 Alpha")
