# -*- coding: utf-8 -*-
"""
Alpha 因子构建页面
功能：从数据集构建 Alpha 因子
"""
import streamlit as st
import json
from pathlib import Path
from web.utils.helpers import load_to_test_alphas
from core.api_client import BrainAPIClient
from scripts.factor_builder import build_factor_pipeline, save_factors_for_batch_test, sync_all_datasets


def page_factor_builder():
    """构建 Alpha 因子页面"""
    st.header("🧬 Alpha 因子构建")
    
    # 数据集缓存状态
    st.subheader("📦 数据集缓存状态")
    col0_1, col0_2, col0_3, col0_4 = st.columns(4)
    
    datasets = [
        ('fundamental6', 'data/field_names_fundamental6_all.json'),
        ('analyst4', 'data/field_names_analyst4_all.json'),
        ('pv1', 'data/field_names_pv1_all.json'),
    ]
    
    cols = [col0_1, col0_2, col0_3]
    for i, (ds_id, cache_path) in enumerate(datasets):
        cache_file = Path(cache_path)
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                fields = json.load(f)
            cols[i].metric(ds_id, f"{len(fields)} 字段", "已缓存")
        else:
            cols[i].metric(ds_id, "0 字段", "未缓存")
    
    # 同步按钮
    if col0_4.button("🔄 同步全部", help="从API同步所有数据集字段"):
        with st.spinner("正在同步数据集..."):
            # 获取认证信息
            from dotenv import load_dotenv
            import os
            load_dotenv()
            username = os.getenv('WQ_USERNAME', '')
            password = os.getenv('WQ_PASSWORD', '')
            
            if username and password:
                # 进度条
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(dataset_id, current, total, status):
                    progress = int(current / total * 100)
                    progress_bar.progress(progress)
                    if status == 'running':
                        status_text.text(f"正在同步 {dataset_id}...")
                    else:
                        status_text.text(f"{dataset_id} 同步完成")
                
                result = sync_all_datasets(username, password, progress_callback=update_progress)
                progress_bar.empty()
                status_text.empty()
                
                if result['success']:
                    st.success(f"""
                    **同步完成！**
                    - fundamental6: {result['datasets']['fundamental6']['fields']} 字段
                    - analyst4: {result['datasets']['analyst4']['fields']} 字段
                    - pv1: {result['datasets']['pv1']['fields']} 字段
                    - 总计: {result['total_fields']} 字段
                    """)
                    st.rerun()
                else:
                    st.error("同步失败")
            else:
                st.error("请在 .env 中配置 WQ_USERNAME 和 WQ_PASSWORD")
    
    st.divider()
    
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
            options=[1, 2, 3],
            format_func=lambda x: {1: "基础策略(充分利用所有字段)", 2: "多因子组合", 3: "跨数据集组合"}[x],
            index=0,
            help="基础策略：日内、波动率、成交量等单因子策略，充分利用所有数据字段\n多因子组合：回归中性化、条件组合等多因子策略\n跨数据集组合：fundamental6 × analyst4/pv1 跨数据集组合"
        )
    
    # 跨数据集选项（仅模式3显示）
    multi_dataset_ids = []
    if strategy_mode == 3:
        st.subheader("跨数据集配置")
        col_cross_1, col_cross_2 = st.columns(2)
        with col_cross_1:
            use_analyst4 = st.checkbox("包含 analyst4 (分析师预测数据)", value=True)
        with col_cross_2:
            use_pv1 = st.checkbox("包含 pv1 (成交量数据)", value=False)
        
        if use_analyst4:
            multi_dataset_ids.append('analyst4')
        if use_pv1:
            multi_dataset_ids.append('pv1')
        
        if multi_dataset_ids:
            st.info(f"将生成 {dataset_id} × {', '.join(multi_dataset_ids)} 的跨数据集组合策略")
    with col3:
        max_factors = st.number_input(
            "构建因子数量",
            min_value=1,
            max_value=10000,
            value=100,
            help="最多构建的因子数量"
        )
    
    # 随机种子配置
    st.subheader("🔀 随机配置")
    col_seed_1, col_seed_2 = st.columns(2)
    with col_seed_1:
        use_seed = st.checkbox("使用固定种子（可复现结果）", value=False)
    with col_seed_2:
        seed_value = None
        if use_seed:
            seed_value = st.number_input("种子值", value=42, help="相同种子产生相同的因子列表，方便分享和复现")
    
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
                strategy_mode=strategy_mode,
                multi_dataset_ids=multi_dataset_ids if strategy_mode == 3 else None,
                seed=seed_value if use_seed else None
            )
        
        if result['success']:
            with st.spinner("正在保存因子..."):
                save_factors_for_batch_test(
                    result['factors'],
                    'data/alphas/to_test.txt',
                    append=append_mode
                )
            
            # 构建成功信息
            success_msg = f"""
            **构建完成！**
            - 主数据集字段: {result['total_fields']} 个 ({dataset_id})
            """
            if result.get('multi_dataset_fields', 0) > 0:
                success_msg += f"- 跨数据集字段: {result['multi_dataset_fields']} 个\n"
            success_msg += f"- 构建因子: {result['total_factors']} 个\n"
            success_msg += f"- 保存到: data/alphas/to_test.txt"
            
            st.success(success_msg)
            
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
