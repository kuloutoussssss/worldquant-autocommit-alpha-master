# -*- coding: utf-8 -*-
"""Alpha 提交工具"""
import sys
import time
from pathlib import Path
from typing import List, Optional
from .api_client import BrainAPIClient
from .logger import logger
from .db_manager import get_database

# 429限流不增加失败计数（API限制，Alpha本身没问题）
THROTTLE_ERRORS = ['429', 'THROTTLED', 'throttled']

# 网络/API错误不增加失败计数（可能是临时性问题）
NETWORK_ERRORS = ['Expecting value', 'JSONDecodeError', 'No response', 'Connection', 'timeout', 'timed out']

# 429限流重试配置（指数退避，与batch_tester.py保持一致）
MAX_SUBMIT_RETRIES = 3  # 最大重试次数
SUBMIT_INITIAL_DELAY = 60  # 初始等待60秒
SUBMIT_BACKOFF_FACTOR = 2.0  # 指数退避因子


def submit_alpha_ids(alpha_id_file: str, num_to_submit: Optional[int] = None) -> dict:
    """
    提交 Alpha ID 列表到 WorldQuant Brain
    
    Args:
        alpha_id_file: 包含 Alpha ID 的文件路径
        num_to_submit: 最大提交数量，None 表示全部
    """
    path = Path(alpha_id_file)
    if not path.exists():
        logger.error(f"Alpha ID file not found: {alpha_id_file}")
        return {'success': 0, 'failed': 0, 'total': 0}
    
    with open(path, 'r', encoding='utf-8') as f:
        alpha_ids = [line.strip() for line in f if line.strip()]
    
    if num_to_submit:
        alpha_ids = alpha_ids[:num_to_submit]
    
    if not alpha_ids:
        logger.warning("No alpha IDs to submit")
        return {'success': 0, 'failed': 0, 'total': 0}
    
    client = BrainAPIClient()
    db = get_database()
    successful = []
    failed = []
    skipped_429 = []
    total_retries = 0  # 总重试次数
    
    logger.info(f"Submitting {len(alpha_ids)} alphas...")
    logger.info(f"429 Retry policy: max={MAX_SUBMIT_RETRIES}, delays={SUBMIT_INITIAL_DELAY}s -> {SUBMIT_INITIAL_DELAY*SUBMIT_BACKOFF_FACTOR}s -> {SUBMIT_INITIAL_DELAY*SUBMIT_BACKOFF_FACTOR**2}s")
    
    try:
        for i, alpha_id in enumerate(alpha_ids, 1):
            logger.info(f"[{i}/{len(alpha_ids)}] Submitting: {alpha_id}")
            
            # 使用指数退避重试机制
            result = _retry_submit_with_backoff(client, alpha_id, i)
            total_retries += result['retries']
            
            if result['success']:
                logger.info(f"  ✓ Success!")
                successful.append(alpha_id)
                db.mark_submitted(alpha_id)
            elif result['is_429']:
                # 429错误超过最大重试次数
                logger.error(f"  ✗ 429错误超过最大重试次数({MAX_SUBMIT_RETRIES}): {result['error']}")
                skipped_429.append(alpha_id)
            else:
                # 其他错误
                error = result['error']
                is_network_error = any(t in str(error) for t in NETWORK_ERRORS)
                
                if is_network_error:
                    logger.warning(f"  ⚠ Network/API Error (不计入失败): {error}")
                    skipped_429.append(alpha_id)
                else:
                    logger.error(f"  ✗ Failed: {error}")
                    failed.append(alpha_id)
                    # 失败时增加计数，连续3次失败才移除
                    should_remove = db.mark_submit_failed(alpha_id, error)
                    if not should_remove:
                        logger.warning(f"  {alpha_id} removed from candidate pool (3+ failures)")
            
            # 请求间隔
            if i < len(alpha_ids):
                time.sleep(1)
    finally:
        client.session.close()
    
    logger.info(f"Submission complete: {len(successful)} success, {len(failed)} failed, {len(skipped_429)} 429 (total_retries: {total_retries})")
    
    return {
        'success': len(successful),
        'failed': len(failed),
        'skipped_429': len(skipped_429),
        'total': len(alpha_ids),
        'successful_ids': successful,
        'failed_ids': failed,
        'skipped_429_ids': skipped_429
    }


def _retry_submit_with_backoff(client: BrainAPIClient, alpha_id: str, i: int) -> dict:
    """使用指数退避重试机制处理429错误
    
    Args:
        client: API客户端
        alpha_id: Alpha ID
        i: 当前索引
    
    Returns:
        重试后的结果 {'success': bool, 'error': str, 'is_429': bool, 'retries': int}
    """
    delay = SUBMIT_INITIAL_DELAY
    
    for retry in range(MAX_SUBMIT_RETRIES):
        if retry > 0:
            # 指数退避等待
            wait_time = delay
            logger.warning(f"  ⏳ 429限流! 等待 {wait_time}秒后重试 ({retry}/{MAX_SUBMIT_RETRIES})...")
            time.sleep(wait_time)
            delay *= SUBMIT_BACKOFF_FACTOR
        
        result = client.submit_alpha(alpha_id)
        
        if result and result.get('status') == 'OK':
            return {'success': True, 'error': None, 'is_429': False, 'retries': retry}
        
        error = result.get('error', 'Unknown error') if result else 'No response'
        is_429 = any(t in str(error) for t in THROTTLE_ERRORS)
        
        if not is_429:
            # 非429错误，停止重试
            return {'success': False, 'error': error, 'is_429': False, 'retries': retry}
    
    # 超过最大重试次数
    return {'success': False, 'error': error, 'is_429': True, 'retries': MAX_SUBMIT_RETRIES}


def submit_from_db(target_success: int = 2) -> dict:
    """
    从候选池获取符合条件的 Alpha 并提交，直到成功达到目标数量
    
    Args:
        target_success: 目标成功提交数量，默认2个
    """
    from .db_manager import get_database
    
    db = get_database()
    candidates = db.get_candidates()
    
    if not candidates:
        logger.warning("No submittable alphas found in candidate pool")
        return {'success': 0, 'failed': 0, 'total': 0, 'skipped_429': 0}
    
    successful = []
    failed = []
    skipped_429 = []
    submitted = 0  # 已尝试提交的总数
    total_retries = 0  # 总重试次数
    
    logger.info(f"Target: {target_success} successful submissions")
    logger.info(f"Candidates available: {len(candidates)}")
    logger.info(f"429 Retry policy: max={MAX_SUBMIT_RETRIES}, delays={SUBMIT_INITIAL_DELAY}s -> {SUBMIT_INITIAL_DELAY*SUBMIT_BACKOFF_FACTOR}s -> {SUBMIT_INITIAL_DELAY*SUBMIT_BACKOFF_FACTOR**2}s")
    
    client = BrainAPIClient()
    
    try:
        for i, alpha in enumerate(candidates, 1):
            # 达到目标成功数后停止
            if len(successful) >= target_success:
                logger.info(f"Target reached ({target_success}), stopping...")
                break
            
            alpha_id = alpha['alpha_id']
            logger.info(f"[{i}/{len(candidates)}] Submitting: {alpha_id} (success: {len(successful)}/{target_success})")
            
            # 使用指数退避重试机制
            result = _retry_submit_with_backoff(client, alpha_id, i)
            submitted += 1
            total_retries += result['retries']
            
            if result['success']:
                logger.info(f"  ✓ Success!")
                successful.append(alpha_id)
                db.mark_submitted(alpha_id)
            elif result['is_429']:
                # 429错误超过最大重试次数
                logger.error(f"  ✗ 429错误超过最大重试次数({MAX_SUBMIT_RETRIES}): {result['error']}")
                skipped_429.append(alpha_id)
            else:
                # 其他错误
                logger.error(f"  ✗ Failed: {result['error']}")
                failed.append(alpha_id)
                # 失败时增加计数，连续3次失败才移除
                should_remove = db.mark_submit_failed(alpha_id, result['error'])
                if not should_remove:
                    logger.warning(f"  {alpha_id} removed from candidate pool (3+ failures)")
            
            # 请求间隔（避免触发限流）
            if i < len(candidates) and len(successful) < target_success:
                time.sleep(1)
                
    finally:
        client.session.close()
    
    logger.info(f"Submission complete: {len(successful)} success, {len(failed)} failed, {len(skipped_429)} 429 (tried: {submitted}, total_retries: {total_retries})")
    
    return {
        'success': len(successful),
        'failed': len(failed),
        'skipped_429': len(skipped_429),
        'total': submitted,
        'successful_ids': successful,
        'failed_ids': failed,
        'skipped_429_ids': skipped_429
    }
