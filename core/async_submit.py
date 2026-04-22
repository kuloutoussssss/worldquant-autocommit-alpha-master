# -*- coding: utf-8 -*-
"""
异步 Alpha 提交引擎
功能：并发执行提交请求，提高效率
"""
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable
from collections import deque

from .api_client import BrainAPIClient
from .db_manager import get_database
from .logger import logger

# 并发配置 - 安全设置
DEFAULT_CONCURRENCY = 1  # 提交并发数（安全值：1）
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 30  # 429 重试延迟（秒）
REQUEST_DELAY = 3.0  # 请求间隔（秒），确保API不超限

# 错误类型
THROTTLE_ERRORS = ['429', 'THROTTLED', 'throttled']
NETWORK_ERRORS = ['Expecting value', 'JSONDecodeError', 'No response', 'Connection', 'timeout', 'timed out']


async def _retry_submit_async(client: BrainAPIClient, alpha_id: str) -> Dict:
    """异步提交单个 Alpha，带重试"""
    for retry in range(MAX_RETRIES):
        try:
            # 在新线程中执行同步的 API 调用
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: client.submit_alpha(alpha_id))
            
            if result and result.get('status') == 'OK':
                return {'success': True, 'error': None, 'is_429': False, 'retries': retry}
            
            error = result.get('error', 'Unknown error') if result else 'No response'
            is_429 = any(t in str(error) for t in THROTTLE_ERRORS)
            
            if is_429 and retry < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (retry + 1)
                logger.warning(f"429限流! 等待 {wait_time}秒后重试 ({retry+1}/{MAX_RETRIES})...")
                await asyncio.sleep(wait_time)
                continue
            
            if is_429:
                return {'success': False, 'error': error, 'is_429': True, 'retries': MAX_RETRIES}
            
            # 非 429 错误，停止重试
            return {'success': False, 'error': error, 'is_429': False, 'retries': retry}
            
        except Exception as e:
            error = str(e)
            is_network = any(t in error for t in NETWORK_ERRORS)
            if is_network and retry < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            return {'success': False, 'error': error, 'is_429': False, 'retries': retry, 'is_network': is_network}
    
    return {'success': False, 'error': 'Max retries exceeded', 'is_429': False, 'retries': MAX_RETRIES}


async def _submit_worker(
    worker_id: int,
    queue: deque,
    results: Dict,
    lock: asyncio.Lock,
    db: Optional[get_database] = None
):
    """提交工作协程"""
    client = BrainAPIClient()
    
    try:
        while True:
            async with lock:
                if not queue:
                    break
                alpha_id = queue.popleft()
            
            logger.info(f"[Worker-{worker_id}] Submitting: {alpha_id}")
            
            result = await _retry_submit_async(client, alpha_id)
            
            async with lock:
                if result['success']:
                    results['success'].append(alpha_id)
                    if db:
                        db.mark_submitted(alpha_id)
                    logger.info(f"[Worker-{worker_id}] ✓ Success!")
                elif result['is_429']:
                    results['skipped_429'].append(alpha_id)
                    logger.error(f"[Worker-{worker_id}] ✗ 429错误超过最大重试次数")
                else:
                    results['failed'].append(alpha_id)
                    if db:
                        should_remove = db.mark_submit_failed(alpha_id, result['error'])
                        if not should_remove:
                            logger.warning(f"[Worker-{worker_id}] {alpha_id} removed from candidate pool (3+ failures)")
                    logger.error(f"[Worker-{worker_id}] ✗ Failed: {result['error']}")
            
            # 请求间隔
            await asyncio.sleep(REQUEST_DELAY)
    finally:
        client.session.close()


async def submit_alpha_ids_async(
    alpha_ids: List[str],
    concurrency: int = DEFAULT_CONCURRENCY,
    db=None
) -> Dict:
    """
    异步提交 Alpha ID 列表
    
    Args:
        alpha_ids: Alpha ID 列表
        concurrency: 并发数
        db: 数据库实例
        
    Returns:
        提交结果
    """
    if not alpha_ids:
        return {'success': 0, 'failed': 0, 'skipped_429': 0, 'total': 0}
    
    logger.info(f"Starting async submit: {len(alpha_ids)} alphas, concurrency={concurrency}")
    
    queue = deque(alpha_ids)
    results = {'success': [], 'failed': [], 'skipped_429': []}
    lock = asyncio.Lock()
    
    # 创建工作协程
    workers = [
        asyncio.create_task(_submit_worker(i, queue, results, lock, db))
        for i in range(concurrency)
    ]
    
    # 等待所有工作协程完成
    await asyncio.gather(*workers)
    
    logger.info(f"Async submit complete: {len(results['success'])} success, {len(results['failed'])} failed, {len(results['skipped_429'])} 429")
    
    return {
        'success': len(results['success']),
        'failed': len(results['failed']),
        'skipped_429': len(results['skipped_429']),
        'total': len(alpha_ids),
        'successful_ids': results['success'],
        'failed_ids': results['failed'],
        'skipped_429_ids': results['skipped_429']
    }


# 同步包装函数
def submit_alpha_ids_sync(alpha_id_file: str, num_to_submit: Optional[int] = None, concurrency: int = DEFAULT_CONCURRENCY) -> Dict:
    """
    同步提交 Alpha ID 列表（内部使用异步）
    
    Args:
        alpha_id_file: Alpha ID 文件路径
        num_to_submit: 最大提交数量
        concurrency: 并发数
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
        return {'success': 0, 'failed': 0, 'total': 0}
    
    db = get_database()
    return asyncio.run(submit_alpha_ids_async(alpha_ids, concurrency, db))
