# -*- coding: utf-8 -*-
"""
Alpha因子构建脚本

功能：
1. 分页获取所有数据字段（突破API限制）
2. 支持多种策略模式生成因子
"""
import requests
import json
import time
from typing import List, Dict, Any, Optional
from pathlib import Path


def get_all_datafields_with_pagination(
    sess: requests.Session,
    instrument_type: str = 'EQUITY',
    region: str = 'USA',
    universe: str = 'TOP3000',
    dataset_id: str = 'fundamental6',
    delay: int = 1,
    use_cache: bool = True
) -> List[str]:
    """分页获取指定数据集的所有数据字段

    参数:
        sess: requests会话对象
        instrument_type: 工具类型,默认为'EQUITY'(股票)
        region: 地区,默认为'USA'
        universe: 股票池，根据数据集不同（fundamental6=TOP3000, analyst4/pv1=TOP1000）
        dataset_id: 数据集ID,默认为'fundamental6'
        delay: 延迟,默认为1
        use_cache: 是否使用本地缓存,默认为True

    返回:
        全部数据字段名称列表
    """
    # 数据集配置（与参考项目 dataset_config.py 一致）
    DATASET_UNIVERSE = {
        'fundamental6': 'TOP3000',
        'analyst4': 'TOP1000',
        'pv1': 'TOP1000',
    }
    
    # 使用数据集对应的 universe
    universe = DATASET_UNIVERSE.get(dataset_id, 'TOP3000')
    
    # 本地缓存文件路径
    cache_file = Path(f"data/field_names_{dataset_id}_all.json")
    
    # 优先从本地缓存加载
    if use_cache and cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                fields = json.load(f)
            print(f"从本地缓存加载了 {len(fields)} 个数据字段")
            return fields
        except Exception as e:
            print(f"加载本地缓存失败: {e},将尝试从API获取")
    
    # 从API分页获取
    brain_api_url = "https://api.worldquantbrain.com"
    all_fields = []
    offset = 0
    page_size = 50  # 与参考项目一致，每次50条
    
    print(f"开始分页获取 {dataset_id} 数据集的字段...")
    
    while True:
        url = (
            f"{brain_api_url}/data-fields?"
            f"instrumentType={instrument_type}"
            f"&region={region}&delay={delay}&universe={universe}"
            f"&dataset.id={dataset_id}&limit={page_size}&offset={offset}"
        )
        
        try:
            response = sess.get(url)
            
            # 处理429错误(请求过于频繁)
            if response.status_code == 429:
                wait_time = 2 ** (offset // page_size + 1)
                print(f"触发速率限制(429),等待{wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            # 提取字段名称，过滤矩阵类型字段（与参考项目一致）
            fields = [f.get('id') for f in data.get('results', []) if f.get('id') and f.get('type') == 'MATRIX']
            all_fields.extend(fields)
            
            print(f"  已获取 {len(all_fields)} 个字段 (offset={offset})")
            
            # 判断是否还有更多数据
            if len(fields) < page_size:
                break
            
            offset += page_size
            time.sleep(0.5)  # 避免请求过快
            
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            break
    
    # 保存到本地缓存
    if all_fields:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(all_fields, f, ensure_ascii=False)
        print(f"数据字段已缓存到: {cache_file}")
    
    return all_fields


def get_datafields(
    sess: requests.Session,
    instrument_type: str = 'EQUITY',
    region: str = 'USA',
    universe: str = 'TOP3000',
    dataset_id: str = 'fundamental6',
    delay: int = 1,
    use_cache: bool = True
) -> List[str]:
    """获取指定数据集的数据字段列表（向后兼容）"""
    return get_all_datafields_with_pagination(
        sess=sess,
        instrument_type=instrument_type,
        region=region,
        universe=universe,
        dataset_id=dataset_id,
        delay=delay,
        use_cache=use_cache
    )


def build_advanced_factors(
    datafields: List[str],
    max_factors: int = 5000,
    strategy_mode: int = 1,
    dataset_id: str = 'fundamental6'
) -> List[Dict[str, Any]]:
    """根据数据字段和策略模式构建Alpha因子配置列表

    参数:
        datafields: 数据字段列表
        max_factors: 最大构建因子数量
        strategy_mode: 策略模式 (1=基础策略, 2=多因子组合)
        dataset_id: 数据集ID

    返回:
        Alpha因子配置列表
    """
    # 导入策略生成器
    from scripts.alpha_strategy import AlphaStrategy
    
    strategy = AlphaStrategy()
    
    # 生成策略表达式
    expressions = strategy.get_simulation_data(datafields, mode=strategy_mode)
    
    print(f"策略模式 {strategy_mode}: 生成了 {len(expressions)} 个表达式")
    
    # 限制数量
    expressions = expressions[:max_factors]
    
    # 转换为因子配置
    alpha_factors = []
    for i, expr in enumerate(expressions, 1):
        print(f"[{i}/{len(expressions)}] 构建因子")
        
        factor_config = {
            'stype': 'REGULAR',
            'settings': {
                'instrumentType': 'EQUITY',
                'region': 'USA',
                'universe': 'TOP3000',
                'delay': 1,
                'decay': 0,
                'neutralization': 'SUBINDUSTRY',
                'truncation': 0.08,
                'pasteurization': 'ON',
                'unitHandling': 'VERIFY',
                'nanHandling': 'ON',
                'language': 'FASTEXPR',
                'visualization': False,
            },
            "regular": expr
        }
        alpha_factors.append(factor_config)
    
    return alpha_factors


def build_factor_pipeline(
    client=None,
    api_token: str = None,
    dataset_id: str = 'fundamental6',
    max_factors: int = 10,
    strategy_mode: int = 1
) -> Dict[str, Any]:
    """构建Alpha因子流水线(仅获取字段和构建因子,不执行回测)
    
    参数:
        client: BrainAPIClient 实例 (优先使用)
        api_token: WorldQuant Brain API令牌 (格式: username:password) - 旧接口兼容
        dataset_id: 数据集ID,默认为'fundamental6'
        max_factors: 最大构建因子数量,默认为10
        strategy_mode: 策略模式 (1=基础策略, 2=多因子组合)
    
    返回:
        包含数据字段和因子配置的字典
    """
    # 初始化会话
    if client is not None and hasattr(client, 'session'):
        session = client.session
        client.ensure_session()
    elif api_token:
        session = requests.Session()
        
        if ':' in api_token:
            username, password = api_token.split(':', 1)
        else:
            username = api_token
            password = ''
        
        from requests.auth import HTTPBasicAuth
        session.auth = HTTPBasicAuth(username, password)
    else:
        print("X 缺少认证信息,请提供 client 或 api_token")
        return {
            'success': False,
            'datafields': [],
            'factors': [],
            'error': '缺少认证信息'
        }
    
    print("=" * 50)
    print("步骤1: 获取数据字段")
    print("=" * 50)
    
    # 第一步:获取数据字段（分页获取全部）
    datafields = get_all_datafields_with_pagination(
        sess=session,
        instrument_type='EQUITY',
        region='USA',
        universe='TOP3000',
        dataset_id=dataset_id
    )

    if not datafields:
        print("X 未能获取数据字段,请检查API令牌和网络连接")
        return {
            'success': False,
            'datafields': [],
            'factors': [],
            'error': '获取数据字段失败'
        }

    print(f"OK 获取到 {len(datafields)} 个数据字段")
    
    print("\n" + "=" * 50)
    print("步骤2: 构建Alpha因子表达式")
    print("=" * 50)
    
    # 根据策略模式构建因子（与参考项目一致）
    alpha_factors = build_advanced_factors(
        datafields=datafields,
        max_factors=max_factors,
        strategy_mode=strategy_mode,
        dataset_id=dataset_id
    )

    print(f"OK 构建了 {len(alpha_factors)} 个Alpha因子")
    
    print("\n" + "=" * 50)
    print("流程完成!")
    print("=" * 50)
    
    return {
        'success': True,
        'datafields': datafields,
        'factors': alpha_factors,
        'total_fields': len(datafields),
        'total_factors': len(alpha_factors)
    }


def save_factors_to_json(factors: List[Dict[str, Any]], filename: str = 'alpha_factors.json'):
    """将因子配置保存到JSON文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(factors, f, indent=2, ensure_ascii=False)
    print(f"因子配置已保存到 {filename}")


def print_factor_summary(factors: List[Dict[str, Any]]):
    """打印因子摘要信息"""
    print("\n" + "=" * 50)
    print("因子摘要")
    print("=" * 50)
    
    for i, factor in enumerate(factors, 1):
        print(f"\n因子 {i}:")
        print(f"  表达式: {factor['regular']}")
        print(f"  类型: {factor['stype']}")
        print(f"  中性化: {factor['settings']['neutralization']}")
        print(f"  延迟: {factor['settings']['delay']}")


def save_factors_for_batch_test(factors: List[Dict[str, Any]], filename: str = 'data/alphas/to_test.txt', append: bool = False):
    """将因子配置保存为批量回测可用的格式
    
    保存格式: expression|universe|region|neutralization|truncation
    地区根据 universe 自动设定: TOP3000 -> CHN, TOP1000 -> USA
    """
    import os
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    new_lines = []
    
    for factor in factors:
        # 兼容不同格式: expression 或 regular 字段
        expression = factor.get('expression', '') or factor.get('regular', '')
        settings = factor.get('settings', factor)
        universe = settings.get('universe', 'TOP3000')
        neutralization = settings.get('neutralization', 'SUBINDUSTRY')
        truncation = settings.get('truncation', 0.08)
        
        if expression:
            # 格式: expression|universe|region|neutralization|truncation
            # region 使用 0 (使用数据集默认值)
            line = f"{expression}|{universe}|0|{neutralization}|{truncation}"
            new_lines.append(line)
    
    if append and os.path.exists(filename):
        # 追加模式:读取现有内容,去重后保存
        with open(filename, 'r', encoding='utf-8') as f:
            existing_lines = [line.strip() for line in f if line.strip()]
        
        # 合并并去重(保持顺序)
        seen = set(existing_lines)
        unique_new_lines = []
        
        for line in new_lines:
            if line not in seen:
                seen.add(line)
                unique_new_lines.append(line)
        
        # 追加新的唯一行
        with open(filename, 'a', encoding='utf-8') as f:
            for line in unique_new_lines:
                f.write(line + '\n')
        
        skipped = len(new_lines) - len(unique_new_lines)
        print(f"因子配置已追加到 {filename}")
        print(f"  新增: {len(unique_new_lines)} 个")
        if skipped > 0:
            print(f"  跳过重复: {skipped} 个")
    else:
        # 覆盖模式
        with open(filename, 'w', encoding='utf-8') as f:
            for line in new_lines:
                f.write(line + '\n')
        print(f"因子配置已保存到 {filename} (共 {len(new_lines)} 个因子)")


if __name__ == "__main__":
    # 示例用法
    API_TOKEN = "your_api_token_here"
    
    result = build_factor_pipeline(
        api_token=API_TOKEN,
        dataset_id='fundamental6',
        max_factors=100,
        strategy_mode=1
    )
    
    if result['success']:
        save_factors_to_json(result['factors'], 'alpha_factors.json')
        save_factors_for_batch_test(result['factors'], 'data/alphas/to_test.txt')
        print_factor_summary(result['factors'])
        print(f"\n数据字段总数: {len(result['datafields'])}")
    else:
        print(f"构建失败: {result.get('error', '未知错误')}")
