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
from typing import Dict as TypeDict  # 避免与 Dict 字典冲突
from pathlib import Path
from requests.auth import HTTPBasicAuth


def authenticate(session: requests.Session, username: str, password: str) -> bool:
    """认证并获取 session token"""
    url = "https://api.worldquantbrain.com/authentication"
    try:
        response = session.post(url, auth=HTTPBasicAuth(username, password), timeout=30)
        if response.status_code == 201:
            data = response.json()
            session.token_expiry = data.get("token", {}).get("expiry", 0)
            print("认证成功")
            return True
        else:
            print(f"认证失败: {response.status_code} - {response.text[:200]}")
            return False
    except Exception as e:
        print(f"认证错误: {e}")
        return False


def get_all_datafields_with_pagination(
    sess: requests.Session,
    username: str,
    password: str,
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
        username: 用户名
        password: 密码
        instrument_type: 工具类型,默认为'EQUITY'(股票)
        region: 地区,默认为'USA'
        universe: 股票池，根据数据集不同（fundamental6=TOP3000, analyst4/pv1=TOP1000）
        dataset_id: 数据集ID,默认为'fundamental6'
        delay: 延迟,默认为1
        use_cache: 是否使用本地缓存,默认为True

    返回:
        全部数据字段名称列表
    """
    # 数据集配置
    DATASET_UNIVERSE = {
        'fundamental6': 'TOP3000',
        'analyst4': 'TOP1000',
        'pv1': 'TOP1000',
    }
    
    universe = DATASET_UNIVERSE.get(dataset_id, 'TOP3000')
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
    
    # 先认证
    if not authenticate(sess, username, password):
        return []
    
    # 从API分页获取
    brain_api_url = "https://api.worldquantbrain.com"
    all_fields = []
    offset = 0
    page_size = 50
    
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
            
            if response.status_code == 429:
                wait_time = 2 ** (offset // page_size + 1)
                print(f"触发速率限制(429),等待{wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            
            if response.status_code == 401:
                print("认证过期,重新认证...")
                if not authenticate(sess, username, password):
                    break
                continue
            
            response.raise_for_status()
            data = response.json()
            
            # 处理不同响应格式
            if isinstance(data, list):
                results = data
            else:
                results = data.get('results', [])
            
            # 获取总数用于判断是否继续（API返回count字段）
            total = data.get('count', len(all_fields)) if isinstance(data, dict) else len(results)
            
            # 收集MATRIX和VECTOR类型的字段ID
            for f in results:
                if isinstance(f, dict):
                    ftype = f.get('type')
                    fid = f.get('id')
                    if fid and ftype in ('MATRIX', 'VECTOR'):
                        all_fields.append(fid)
            print(f"  已获取 {len(all_fields)} 个字段(MATRIX+VECTOR, API total={total}, offset={offset})")
            
            # 如果返回的记录数小于page_size，说明已经是最后一页
            if len(results) < page_size:
                break
            
            # 避免限流
            offset += page_size
            time.sleep(3)
            
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            break
    
    # 去重并保存到本地缓存
    if all_fields:
        unique_fields = list(dict.fromkeys(all_fields))  # 保持顺序去重
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(unique_fields, f, ensure_ascii=False)
        print(f"数据字段已缓存到: {cache_file} ({len(unique_fields)} 个字段)")
        return unique_fields
    
    return all_fields


def sync_all_datasets(
    username: str,
    password: str,
    progress_callback=None
) -> Dict[str, Any]:
    """同步所有数据集的字段到本地缓存
    
    参数:
        username: 用户名
        password: 密码
        progress_callback: 进度回调函数，接收 (dataset_id, current, total, status) 参数
    
    返回:
        包含同步结果的字典
    """
    datasets = [
        ('fundamental6', 'TOP3000'),
        ('analyst4', 'TOP1000'),
        ('pv1', 'TOP1000'),
    ]
    
    results = {}
    total_fields = 0
    
    for i, (dataset_id, universe) in enumerate(datasets):
        if progress_callback:
            progress_callback(dataset_id, i, len(datasets), 'running')
        
        # 强制不使用缓存，重新获取
        session = requests.Session()
        fields = get_all_datafields_with_pagination(
            sess=session,
            username=username,
            password=password,
            dataset_id=dataset_id,
            use_cache=False
        )
        
        results[dataset_id] = {
            'fields': len(fields),
            'status': 'success' if fields else 'failed'
        }
        total_fields += len(fields)
        
        if progress_callback:
            progress_callback(dataset_id, i + 1, len(datasets), 'done')
    
    return {
        'success': True,
        'datasets': results,
        'total_fields': total_fields
    }


def get_datafields(
    sess: requests.Session,
    username: str,
    password: str,
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
        username=username,
        password=password,
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
    dataset_id: str = 'fundamental6',
    multi_dataset_fields: Dict[str, List[str]] = None,
    seed: int = None
) -> List[Dict[str, Any]]:
    """根据数据字段和策略模式构建Alpha因子配置列表

    参数:
        datafields: 数据字段列表
        max_factors: 最大构建因子数量
        strategy_mode: 策略模式 (1=基础策略, 2=多因子组合, 3=跨数据集)
        dataset_id: 数据集ID
        multi_dataset_fields: 其他数据集的字段字典
        seed: 随机种子（用于复现）

    返回:
        Alpha因子配置列表
    """
    # 导入策略生成器
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.alpha_strategy import AlphaStrategy
    
    strategy = AlphaStrategy(seed=seed, random_mode=True)
    
    # 从数据库加载失败模式（失败次数>=2的表达式）
    failed_patterns_count = strategy.load_failure_patterns(min_fail_count=2)
    if failed_patterns_count > 0:
        print(f"[FactorBuilder] 已学习 {failed_patterns_count} 个失败模式，将避免生成类似表达式")
    
    # 生成策略表达式
    expressions = strategy.get_simulation_data(
        datafields, 
        mode=strategy_mode,
        multi_dataset_fields=multi_dataset_fields
    )
    
    print(f"策略模式 {strategy_mode}: 生成了 {len(expressions)} 个表达式")
    
    # 限制数量
    expressions = expressions[:max_factors]
    
    # 转换模式说明
    mode_desc = {1: '基础策略(充分利用所有字段)', 2: '多因子组合策略', 3: '跨数据集组合策略'}
    
    # 转换为因子配置
    alpha_factors = []
    for i, expr in enumerate(expressions, 1):
        print(f"[{i}/{len(expressions)}] {mode_desc.get(strategy_mode, '未知模式')} - 构建因子")
        
        # 根据数据集确定默认universe
        universe = 'TOP3000' if dataset_id == 'fundamental6' else 'TOP1000'
        
        factor_config = {
            'stype': 'REGULAR',
            'settings': {
                'instrumentType': 'EQUITY',
                'region': 'USA',
                'universe': universe,
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
    username: str = None,
    password: str = None,
    dataset_id: str = 'fundamental6',
    max_factors: int = 10,
    strategy_mode: int = 1,
    multi_dataset_ids: list = None,
    seed: int = None
) -> Dict[str, Any]:
    """构建Alpha因子流水线(仅获取字段和构建因子,不执行回测)
    
    参数:
        client: BrainAPIClient 实例 (优先使用)
        username: 用户名
        password: 密码
        dataset_id: 数据集ID,默认为'fundamental6'
        max_factors: 最大构建因子数量,默认为10
        strategy_mode: 策略模式 (1=基础策略, 2=多因子组合, 3=跨数据集)
        multi_dataset_ids: 其他数据集ID列表（用于模式3跨数据集组合）
        seed: 随机种子（用于复现，固定为随机模式）
    
    返回:
        包含数据字段和因子配置的字典
    """
    # 初始化会话
    if client is not None and hasattr(client, 'session'):
        session = client.session
        username = username or client.email
        password = password or client.password
        client.ensure_session()
    elif username:
        session = requests.Session()
    else:
        print("X 缺少认证信息,请提供 client 或 username/password")
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
        username=username,
        password=password,
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

    print(f"OK 获取到 {len(datafields)} 个数据字段 (主数据集: {dataset_id})")
    
    # 模式3: 获取其他数据集字段
    multi_dataset_fields = {}
    if strategy_mode == 3 and multi_dataset_ids:
        print(f"\n获取跨数据集字段...")
        for other_ds in multi_dataset_ids:
            if other_ds != dataset_id:
                other_fields = get_all_datafields_with_pagination(
                    sess=session,
                    username=username,
                    password=password,
                    instrument_type='EQUITY',
                    region='USA',
                    universe='TOP1000' if other_ds != 'fundamental6' else 'TOP3000',
                    dataset_id=other_ds
                )
                if other_fields:
                    multi_dataset_fields[other_ds] = other_fields
                    print(f"  {other_ds}: {len(other_fields)} 个字段")
    
    print("\n" + "=" * 50)
    print("步骤2: 构建Alpha因子表达式")
    print("=" * 50)
    
    # 模式说明
    mode_desc = {1: '基础策略', 2: '多因子组合', 3: '跨数据集组合'}
    print(f"策略模式: {mode_desc.get(strategy_mode, '未知')} (mode={strategy_mode})")
    
    # 根据策略模式构建因子
    alpha_factors = build_advanced_factors(
        datafields=datafields,
        max_factors=max_factors,
        strategy_mode=strategy_mode,
        dataset_id=dataset_id,
        multi_dataset_fields=multi_dataset_fields if multi_dataset_fields else None,
        seed=seed
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
        'multi_dataset_fields': len(sum(m.multi_dataset_fields.values(), [])) if multi_dataset_fields else 0,
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
    # 从 .env 加载认证信息
    from dotenv import load_dotenv
    load_dotenv()
    import os
    
    USERNAME = os.getenv("WQ_USERNAME", "")
    PASSWORD = os.getenv("WQ_PASSWORD", "")
    
    if not USERNAME or not PASSWORD:
        print("错误: 请在 .env 文件中配置 WQ_USERNAME 和 WQ_PASSWORD")
        exit(1)
    
    result = build_factor_pipeline(
        username=USERNAME,
        password=PASSWORD,
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
