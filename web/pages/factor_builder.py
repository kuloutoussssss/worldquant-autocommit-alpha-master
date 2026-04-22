# -*- coding: utf-8 -*-
"""
Alpha 因子构建页面
功能：从数据集构建 Alpha 因子
"""
import streamlit as st
import json
from web.utils.helpers import load_to_test_alphas
from core.api_client import BrainAPIClient
from scripts.factor_builder import build_factor_pipeline, save_factors_for_batch_test


def page_factor_builder():
    """构建 Alpha 因子页面"""
    st.header("🧬 Alpha 因子构建")
    
    client = BrainAPIClient()
    
    if not client.ensure_session():
        st.error("认证失败，请检查账号配置")
        return
    
    st.divider()
    
    st.subheader("参数配置")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        dataset_options = {
            "1: fundamental6 (TOP3000) - 基础财务数据": "fundamental6",
            "2: analyst4 (TOP1000) - 分析师预测数据": "analyst4",
            "3: pv1 (TOP1000) - 股市成交量数据": "pv1",
        }
        dataset_display = st.selectbox(
            "数据集",
            options=list(dataset_options.keys()),
            index=0,
            help="选择要使用的数据集"
        )
        dataset_id = dataset_options[dataset_display]
    with col2:
        strategy_mode = st.selectbox(
            "策略模式",
            options=[1, 2],
            format_func=lambda x: ["基础策略", "多因子组合"][x-1],
            index=0,
            help="基础策略：日内、波动率、成交量等单因子策略\n多因子组合：回归中性化、条件组合等多因子策略"
        )
    with col3:
        max_factors = st.number_input(
            "构建因子数量",
            min_value=1,
            max_value=5000,
            value=10,
            help="最多构建的因子数量"
        )
    
    existing_count = len(load_to_test_alphas())
    st.metric("现有 Alpha", existing_count)
    
    col4, col5 = st.columns(2)
    with col4:
        append_mode = st.checkbox("追加到现有列表", value=False, help="勾选则追加到现有文件，否则覆盖")
    with col5:
        st.info(f"操作后预计总数: {existing_count + max_factors if append_mode else max_factors}")
    
    st.divider()
    
    if st.button("🔨 开始构建因子", type="primary"):
        with st.spinner("正在构建因子..."):
            result = build_factor_pipeline(
                client=client,
                dataset_id=dataset_id,
                max_factors=max_factors,
                strategy_mode=strategy_mode
            )
        
        if result['success']:
            with st.spinner("正在保存因子..."):
                save_factors_for_batch_test(
                    result['factors'],
                    'data/alphas/to_test.txt',
                    append=append_mode
                )
            
            st.success(f"""
            **构建完成！**
            - 获取数据字段: {result['total_fields']} 个
            - 构建因子: {result['total_factors']} 个
            - 保存到: data/alphas/to_test.txt
            """)
            
            st.subheader("构建的因子列表")
            
            factors_data = []
            for i, f in enumerate(result['factors'], 1):
                factors_data.append({
                    "序号": i,
                    "表达式": f.get('regular', f.get('expression', '')),
                    "延迟": f.get('settings', {}).get('delay', 0),
                    "中性化": f.get('settings', {}).get('neutralization', ''),
                })
            
            df_factors = pd.DataFrame(factors_data)
            st.dataframe(df_factors, width='stretch')
            
            st.divider()
            col1, col2 = st.columns(2)
            
            with col1:
                json_data = json.dumps(result['factors'], indent=2, ensure_ascii=False)
                st.download_button(
                    "📥 导出为 JSON",
                    json_data,
                    f"alpha_factors_{dataset_id}.json",
                    "application/json"
                )
            
            with col2:
                txt_content = "\n".join([f.get('regular', '') for f in result['factors']])
                st.download_button(
                    "📥 导出为 TXT",
                    txt_content,
                    f"alpha_factors_{dataset_id}.txt",
                    "text/plain"
                )
        else:
            st.error(f"构建失败: {result.get('error', '未知错误')}")
    
    client.session.close()


# 导入 pandas 用于 DataFrame
import pandas as pd
