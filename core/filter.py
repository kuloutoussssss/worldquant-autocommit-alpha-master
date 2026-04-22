# -*- coding: utf-8 -*-
"""
筛选模块 - 统一的 Alpha 合格判断逻辑
检查 6 项指标是否全部 PASS
"""

# 6项必须全部 PASS 的指标
QUALIFIED_CHECKS = {
    'LOW_SHARPE',
    'LOW_FITNESS',
    'LOW_TURNOVER',
    'HIGH_TURNOVER',
    'CONCENTRATED_WEIGHT',
    'LOW_SUB_UNIVERSE_SHARPE'
}


def is_qualified_result(result: dict) -> bool:
    """
    统一的合格判断函数
    检查 6 项指标是否全部 PASS

    Args:
        result: 回测结果字典,包含 checks 列表

    Returns:
        True 如果全部 PASS,否则 False
    """
    checks = result.get('checks', [])
    check_results = {item.get('name'): item.get('result') for item in checks}
    return all(check_results.get(m) == 'PASS' for m in QUALIFIED_CHECKS)


def filter_qualified_alpha_ids(data: dict, key: str = 'results') -> list:
    """
    从结果列表中筛选合格的 Alpha ID

    Args:
        data: 包含 results 或 alphas 的字典
        key: 列表的键名 ('results' 或 'alphas')

    Returns:
        合格的 Alpha ID 列表
    """
    qualified_ids = []

    for item in data.get(key, []):
        # 直接有 alpha_id 且通过筛选
        if 'alpha_id' in item and is_qualified_result(item):
            alpha_id = item.get('alpha_id')
            if alpha_id:
                qualified_ids.append(alpha_id)

    return qualified_ids


def get_qualified_stats(result: dict) -> dict:
    """
    获取各项指标的合格状态

    Args:
        result: 回测结果字典

    Returns:
        dict: 每个指标的 PASS/FAIL 状态
    """
    checks = result.get('checks', [])
    check_results = {item.get('name'): item.get('result') for item in checks}

    return {
        'LOW_SHARPE': check_results.get('LOW_SHARPE', 'N/A'),
        'LOW_FITNESS': check_results.get('LOW_FITNESS', 'N/A'),
        'LOW_TURNOVER': check_results.get('LOW_TURNOVER', 'N/A'),
        'HIGH_TURNOVER': check_results.get('HIGH_TURNOVER', 'N/A'),
        'CONCENTRATED_WEIGHT': check_results.get('CONCENTRATED_WEIGHT', 'N/A'),
        'LOW_SUB_UNIVERSE_SHARPE': check_results.get('LOW_SUB_UNIVERSE_SHARPE', 'N/A'),
    }
