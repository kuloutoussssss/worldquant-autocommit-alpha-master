# -*- coding: utf-8 -*-
"""
中性化组合测试 API
"""
from flask import Blueprint, request, jsonify
from core.neutralization_tester import (
    NeutralizationTester,
    test_neutralization_combinations,
    get_neutralization_options,
    is_quality_alpha,
    get_quality_conditions_description,
    NEUTRALIZATION_OPTIONS
)

neutralization_bp = Blueprint('neutralization', __name__, url_prefix='/api/neutralization')


@neutralization_bp.route('/options', methods=['GET'])
def get_options():
    """
    获取中性化选项

    Returns:
        {
            "regions": {
                "USA": ["STATISTICAL", "REVERSION_AND_MOMENTUM", ...],
                "CHN": [...],
                ...
            },
            "max_trade": ["ON", "OFF"],
            "quality_conditions": "..."
        }
    """
    return jsonify({
        'regions': NEUTRALIZATION_OPTIONS,
        'max_trade': ['ON', 'OFF'],
        'quality_conditions': get_quality_conditions_description()
    })


@neutralization_bp.route('/test', methods=['POST'])
def test_combinations():
    """
    测试中性化组合

    Request Body:
        {
            "alpha_id": "KPwOMNk1",  # Alpha ID
            "expression": "...",      # 可选，如果提供则直接使用
            "region": "USA",          # 可选，默认从 alpha_id 获取
            "universe": "TOP3000",    # 可选
            "decay": 30,              # 可选
            "truncation": 0.08,       # 可选
            "concurrency": 1          # 可选，默认1（同步）
        }

    Returns:
        {
            "status": "ok",
            "results": [...],
            "summary": {
                "total_combinations": 20,
                "completed": 20,
                "quality_count": 3,
                "best_sharpe": 2.15,
                "best_combination": {...},
                "quality_alphas": [...]
            }
        }
    """
    data = request.get_json()

    if not data:
        return jsonify({'status': 'error', 'message': '请求体不能为空'}), 400

    alpha_id = data.get('alpha_id')
    expression = data.get('expression')

    if not alpha_id and not expression:
        return jsonify({'status': 'error', 'message': '必须提供 alpha_id 或 expression'}), 400

    from core.api_client import BrainAPIClient
    client = BrainAPIClient()

    # 如果提供了 alpha_id，获取表达式和设置
    if alpha_id and not expression:
        try:
            alpha_info = client.get_alpha(alpha_id)
            if not alpha_info:
                return jsonify({'status': 'error', 'message': f'无法获取Alpha {alpha_id}'}), 404

            expression = alpha_info.get('regular', {}).get('code', '')
            if not expression:
                return jsonify({'status': 'error', 'message': 'Alpha表达式为空'}), 400

            region = data.get('region', alpha_info.get('settings', {}).get('region', 'USA'))
            universe = data.get('universe', alpha_info.get('settings', {}).get('universe', 'TOP3000'))
            decay = data.get('decay', int(alpha_info.get('settings', {}).get('decay', 30)))
            truncation = data.get('truncation', float(alpha_info.get('settings', {}).get('truncation', 0.08)))
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'获取Alpha信息失败: {str(e)}'}), 500
    else:
        region = data.get('region', 'USA')
        universe = data.get('universe', 'TOP3000')
        decay = data.get('decay', 30)
        truncation = data.get('truncation', 0.08)

    concurrency = data.get('concurrency', 1)

    # 创建测试器
    tester = NeutralizationTester(
        expression=expression,
        region=region,
        universe=universe,
        decay=decay,
        truncation=truncation,
        base_alpha_id=alpha_id,
        progress_callback=None
    )

    try:
        # 执行测试
        results = tester.test_all_combinations(concurrency=concurrency)

        # 返回结果
        return jsonify({
            'status': 'ok',
            'results': [r.to_dict() for r in results],
            'summary': tester.get_summary()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@neutralization_bp.route('/quality-check', methods=['POST'])
def check_quality():
    """
    检查单个Alpha是否符合优质条件

    Request Body:
        {
            "sharpe": 1.5,
            "turnover": 0.35,
            "margin": 0.001
        }

    Returns:
        {
            "is_quality": true,
            "matched_condition": 1  # 匹配的条件编号，0表示未匹配
        }
    """
    data = request.get_json()

    if not data:
        return jsonify({'status': 'error', 'message': '请求体不能为空'}), 400

    result = {
        'sharpe': float(data.get('sharpe', 0)),
        'turnover': float(data.get('turnover', 1)),
        'margin': float(data.get('margin', 0))
    }

    quality = is_quality_alpha(result)

    # 确定匹配的条件
    matched = 0
    if quality:
        if result['turnover'] <= 0.4 and abs(result['sharpe']) >= 1.5 and abs(result['margin']) >= 0.001:
            matched = 2
        elif result['turnover'] <= 0.4 and abs(result['sharpe']) >= 1.2 and abs(result['margin']) >= 0.0009:
            matched = 1
        elif result['turnover'] <= 0.6 and abs(result['sharpe']) >= 2.0 and abs(result['margin']) >= 0.0015:
            matched = 3

    return jsonify({
        'is_quality': quality,
        'matched_condition': matched
    })


@neutralization_bp.route('/batch-test', methods=['POST'])
def batch_test():
    """
    批量中性化测试

    Request Body:
        {
            "alphas": [
                {"alpha_id": "xxx", "expression": "..."},
                {"alpha_id": "yyy", "expression": "..."}
            ],
            "region": "USA",
            "concurrency": 1
        }

    Returns:
        {
            "status": "ok",
            "total": 2,
            "completed": 2,
            "results": [
                {
                    "alpha_id": "xxx",
                    "status": "success",
                    "results": [...],
                    "summary": {...}
                },
                ...
            ]
        }
    """
    data = request.get_json()

    if not data:
        return jsonify({'status': 'error', 'message': '请求体不能为空'}), 400

    alphas = data.get('alphas', [])
    region = data.get('region', 'USA')
    concurrency = data.get('concurrency', 1)

    if not alphas:
        return jsonify({'status': 'error', 'message': 'alphas 列表不能为空'}), 400

    results = []
    completed = 0

    for alpha_item in alphas:
        alpha_id = alpha_item.get('alpha_id')
        expression = alpha_item.get('expression')

        if not alpha_id and not expression:
            results.append({
                'alpha_id': alpha_id or 'unknown',
                'status': 'error',
                'error': 'alpha_id 和 expression 都为空'
            })
            continue

        try:
            # 创建测试器
            tester = NeutralizationTester(
                expression=expression,
                region=region,
                base_alpha_id=alpha_id,
                progress_callback=None
            )

            # 执行测试
            test_results = tester.test_all_combinations(concurrency=concurrency)

            results.append({
                'alpha_id': alpha_id,
                'status': 'success',
                'results': [r.to_dict() for r in test_results],
                'summary': tester.get_summary()
            })
            completed += 1

        except Exception as e:
            results.append({
                'alpha_id': alpha_id,
                'status': 'error',
                'error': str(e)
            })

    return jsonify({
        'status': 'ok',
        'total': len(alphas),
        'completed': completed,
        'failed': len(alphas) - completed,
        'results': results
    })
