# -*- coding: utf-8 -*-
"""
中性化组合测试页面
"""
import streamlit as st
from utils.api_client_st import API_BASE
import requests
import json


def page_neutralization():
    """中性化组合测试页面"""

    st.title("中性化组合测试")
    st.markdown("""
    ### 功能说明
    测试 Alpha 在不同中性化方式 × maxTrade 组合下的表现，自动筛选优质结果并打标签。

    ### 优质Alpha筛选条件
    1. 换手率 <= 0.4, Sharpe >= 1.2, Margin >= 0.0009
    2. 换手率 <= 0.4, Sharpe >= 1.5, Margin >= 0.001
    3. 换手率 <= 0.6, Sharpe >= 2.0, Margin >= 0.0015
    """)

    api_base = API_BASE

    # 获取中性化选项
    try:
        response = requests.get(f"{api_base}/api/neutralization/options", timeout=10)
        if response.status_code == 200:
            options_data = response.json()
            regions = options_data.get('regions', {})
            max_trade_options = options_data.get('max_trade', ['ON', 'OFF'])
        else:
            regions = {
                'USA': ['STATISTICAL', 'REVERSION_AND_MOMENTUM', 'SLOW_AND_FAST', 'FAST', 'SLOW', 'CROWDING', 'MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'],
                'CHN': ['STATISTICAL', 'REVERSION_AND_MOMENTUM', 'SLOW_AND_FAST', 'FAST', 'SLOW', 'CROWDING', 'MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'],
            }
            max_trade_options = ['ON', 'OFF']
    except Exception as e:
        st.error(f"获取选项失败: {e}")
        return

    # 输入表单
    col1, col2 = st.columns(2)

    with col1:
        alpha_id = st.text_input(
            "Alpha ID",
            placeholder="输入Alpha ID，例如: KPwOMNk1",
            help="输入已存在的Alpha ID，系统将自动获取表达式"
        )

        region = st.selectbox(
            "区域",
            options=list(regions.keys()),
            index=0
        )

    with col2:
        st.info("""
        **说明：**
        - 输入 Alpha ID 后，系统将自动获取表达式和设置
        - 将测试所有中性化方式 × maxTrade (ON/OFF) 组合
        - 优质结果将自动打标签
        """)

    # 显示将测试的组合
    if alpha_id:
        neutralizations = regions.get(region, [])
        total_combinations = len(neutralizations) * len(max_trade_options)

        st.markdown(f"""
        ### 测试计划
        - **区域**: {region}
        - **中性化方式**: {len(neutralizations)} 种
        - **maxTrade**: {max_trade_options}
        - **总组合数**: {total_combinations} 个
        """)

        # 测试按钮
        if st.button("开始测试", type="primary", use_container_width=True):
            with st.spinner("测试中，请稍候..."):
                try:
                    response = requests.post(
                        f"{api_base}/api/neutralization/test",
                        json={"alpha_id": alpha_id, "region": region},
                        timeout=300
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if data.get('success'):
                            results = data.get('results', [])
                            summary = data.get('summary', {})

                            # 显示摘要
                            st.success("测试完成！")

                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("总组合数", summary.get('total_combinations', 0))
                            with col2:
                                st.metric("成功完成", summary.get('completed', 0))
                            with col3:
                                st.metric("优质Alpha", summary.get('quality_count', 0))
                            with col4:
                                st.metric("最佳Sharpe", f"{summary.get('best_sharpe', 0):.3f}")

                            # 显示结果表格
                            st.markdown("### 测试结果")

                            if results:
                                # 转换为DataFrame显示
                                import pandas as pd
                                df = pd.DataFrame(results)

                                # 格式化显示
                                df_display = df[['neutralization', 'max_trade', 'sharpe', 'fitness', 'turnover', 'margin', 'is_quality', 'status']].copy()
                                df_display.columns = ['中性化', 'maxTrade', 'Sharpe', 'Fitness', '换手率', 'Margin', '优质', '状态']
                                df_display['Sharpe'] = df_display['Sharpe'].apply(lambda x: f"{x:.3f}")
                                df_display['Fitness'] = df_display['Fitness'].apply(lambda x: f"{x:.3f}")
                                df_display['换手率'] = df_display['换手率'].apply(lambda x: f"{x:.3f}")
                                df_display['Margin'] = df_display['Margin'].apply(lambda x: f"{x:.6f}")
                                df_display['优质'] = df_display['优质'].apply(lambda x: '★' if x else '')

                                st.dataframe(df_display, use_container_width=True)

                            # 显示优质Alpha列表
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
    else:
        st.warning("请输入 Alpha ID")

    # 优质条件检查器
    st.divider()
    st.subheader("优质Alpha条件检查器")

    col1, col2, col3 = st.columns(3)
    with col1:
        sharpe = st.number_input("Sharpe", value=1.5, step=0.1, format="%.2f")
    with col2:
        turnover = st.number_input("换手率", value=0.4, step=0.05, max_value=1.0, format="%.2f")
    with col3:
        margin = st.number_input("Margin", value=0.001, step=0.0001, format="%.4f")

    if st.button("检查是否符合优质条件"):
        try:
            response = requests.post(
                f"{api_base}/api/neutralization/quality-check",
                json={"sharpe": sharpe, "turnover": turnover, "margin": margin},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    if data.get('is_quality'):
                        st.success(f"✓ 符合优质条件！匹配条件 {data.get('matched_condition')}")
                    else:
                        st.error("✗ 不符合优质条件")
        except Exception as e:
            st.error(f"检查失败: {e}")
