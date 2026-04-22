# -*- coding: utf-8 -*-
"""
异步 Alpha 回测引擎
功能：并发执行回测请求，提高效率
"""
import asyncio
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Callable, Set
from dataclasses import dataclass, field, asdict
from collections import deque

from .api_client import BrainAPIClient
from .db_manager import get_database
from .logger import logger

# 并发配置 - 安全设置
DEFAULT_CONCURRENCY = 1  # 默认并发数（安全值：1）
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 30  # 429 重试延迟（秒）
REQUEST_DELAY = 3.0  # 请求间隔（秒），确保API不超限


@dataclass
class BacktestResult:
    """单个回测结果"""
    alpha_id: str = ""
    expression: str = ""
    sharpe: float = 0.0
    fitness: float = 0.0
    turnover: float = 1.0
    returns: float = 0.0
    drawdown: float = 0.0
    status: str = "PENDING"  # PENDING, OK, ERROR, SKIPPED_429
    error: str = ""
    is_429: bool = False
    index: int = 0
    test_time: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AsyncBacktestEngine:
    """
    异步 Alpha 回测引擎
    
    使用 asyncio 并发执行回测请求，大幅提升效率
    """
    
    progress_callback: Optional[Callable] = None
    result_callback: Optional[Callable] = None
    concurrency: int = DEFAULT_CONCURRENCY
    remove_tested: bool = True  # 是否从输入文件删除已回测的表达式
    input_file: str = ""  # 输入文件路径
    
    def __post_init__(self):
        self.completed = 0
        self.failed = 0
        self.skipped_429 = 0
        self.processed_ids: Set[str] = set()
        self.db = get_database()
        self.client = BrainAPIClient()  # 共享客户端
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._results: List[BacktestResult] = []
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'client'):
            self.client.session.close()
    
    def is_tested(self, expression: str) -> bool:
        """检查表达式是否已测试"""
        return self.db.is_expression_tested(expression)
    
    def remove_from_file(self, expression: str, input_file: str):
        """从输入文件删除已回测的表达式"""
        input_path = Path(input_file)
        if not input_path.exists():
            return
        
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            expr_to_remove = expression.strip()
            remaining = []
            for line in lines:
                line = line.strip()
                if line:
                    parts = line.split('|')
                    if parts[0].strip() != expr_to_remove:
                        remaining.append(line)
            
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(remaining) + '\n')
        except Exception as e:
            logger.error(f"Failed to remove from file: {e}")
    
    async def test_single(self, alpha: Dict) -> BacktestResult:
        """异步测试单个 Alpha"""
        expression = alpha.get('expression', '')
        universe = alpha.get('universe', 'TOP3000')
        decay = alpha.get('decay', 30)
        neutralization = alpha.get('neutralization', 'SECTOR')
        truncation = alpha.get('truncation', 0.08)
        region = alpha.get('region', 'USA')
        test_period = alpha.get('test_period', 'P2Y0M')
        index = alpha.get('index', 0)
        
        result = BacktestResult(
            expression=expression,
            index=index,
            test_time=datetime.now().isoformat()
        )
        
        try:
            # 在线程池中执行同步 API 调用
            loop = asyncio.get_event_loop()
            
            # 1. 提交 simulation
            api_result = await loop.run_in_executor(
                None,
                lambda: self.client.test_alpha(
                    expression=expression,
                    universe=universe,
                    decay=int(decay) if decay else 30,
                    neutralization=neutralization.upper() if neutralization else 'SECTOR',
                    truncation=float(truncation) if truncation else 0.08,
                    region=region,
                    test_period=test_period
                )
            )
            
            if not api_result or api_result.get('status') != 'OK':
                error = api_result.get('error', 'Unknown error') if api_result else 'No response'
                result.status = "ERROR"
                result.error = error
                result.is_429 = "429" in str(error) or "LIMIT_EXCEEDED" in str(error)
                return result
            
            location = api_result.get('location', '')
            
            # 2. 轮询获取结果（使用线程池避免阻塞事件循环）
            api_result = await loop.run_in_executor(
                None,
                lambda: self.client.get_simulation_result(location)
            )
            
            if api_result and api_result.get('status') == 'OK':
                data = api_result.get('data', {})
                result.alpha_id = data.get('alphaId', '')
                result.sharpe = float(data.get('sharpe', 0))
                result.fitness = float(data.get('fitness', 0))
                result.turnover = float(data.get('turnover', 0))
                result.returns = float(data.get('returns', 0))
                result.drawdown = float(data.get('drawdown', 0))
                result.status = "OK"
            elif api_result and api_result.get('status') == 'ERROR':
                error = api_result.get('error', 'Unknown error')
                result.status = "ERROR"
                result.error = error
                result.is_429 = "429" in str(error) or "LIMIT_EXCEEDED" in str(error)
            else:
                result.status = "ERROR"
                result.error = "No response"
                
        except Exception as e:
            result.status = "ERROR"
            result.error = str(e)
            result.is_429 = "429" in str(e) or "LIMIT_EXCEEDED" in str(e)
            logger.error(f"Test error: {e}")
        
        return result
    
    async def _process_alpha(
        self, 
        alpha: Dict, 
        queue: deque,
        completed_ids: Set[str],
        results: List[BacktestResult]
    ):
        """处理单个 Alpha，包含 429 重试逻辑"""
        expression = alpha.get('expression', '')
        
        for retry in range(MAX_RETRIES):
            result = await self.test_single(alpha)
            
            if result.status == "OK":
                async with self._lock:
                    results.append(result)
                    completed_ids.add(expression)
                self.completed += 1
                
                # 从输入文件删除已回测的表达式
                if self.remove_tested and self.input_file:
                    self.remove_from_file(expression, self.input_file)
                
                self._update_progress()
                if self.result_callback:
                    self.result_callback(result)
                return
            
            if result.is_429 and retry < MAX_RETRIES - 1:
                # 429 错误，等待后重试
                wait_time = RETRY_DELAY * (retry + 1)
                logger.warning(f"429限流! 等待 {wait_time}秒后重试 ({retry+1}/{MAX_RETRIES})...")
                await asyncio.sleep(wait_time)
                continue
            
            # 其他错误或超过重试次数
            async with self._lock:
                results.append(result)
                completed_ids.add(expression)
            
            if result.is_429:
                result.status = "SKIPPED_429"
                result.error = f"429 after {MAX_RETRIES} retries"
                self.skipped_429 += 1
                logger.warning(f"  429错误跳过: {result.error}")
            else:
                self.failed += 1
                logger.error(f"  Error: {result.error}")
            
            self._update_progress()
            if self.result_callback:
                self.result_callback(result)
            return
        
        # 理论上不会到这里
        self.skipped_429 += 1
        self._update_progress()
    
    async def _worker(
        self, 
        worker_id: int,
        alphas_queue: deque,
        completed_ids: Set[str],
        results: List[BacktestResult]
    ):
        """工作协程，从队列取任务执行"""
        while not self._stop_event.is_set():
            async with self._lock:
                if not alphas_queue:
                    break
                alpha = alphas_queue.popleft()
            
            expression = alpha.get('expression', '')
            expr_preview = expression[:50] + ('...' if len(expression) > 50 else '')
            
            logger.info(f"[Worker-{worker_id}] Processing: {expr_preview}")
            
            try:
                await self._process_alpha(alpha, alphas_queue, completed_ids, results)
            except Exception as e:
                logger.error(f"[Worker-{worker_id}] Error: {e}")
                self.failed += 1
                self._update_progress()
            
            # 请求间隔
            await asyncio.sleep(REQUEST_DELAY)
    
    def _update_progress(self):
        """更新进度"""
        if self.progress_callback:
            total = len(self._results) + self.completed + self.failed + self.skipped_429
            self.progress_callback({
                'total': total,
                'completed': self.completed,
                'failed': self.failed,
                'skipped_429': self.skipped_429
            })
    
    async def run_batch_async(
        self,
        alphas: List[Dict],
        output_file: str = "data/results/batch_results.json",
        input_file: str = "data/alphas/to_test.txt",
        remove_tested: bool = True
    ) -> List[BacktestResult]:
        """
        异步批量回测
        
        Args:
            alphas: Alpha 列表
            output_file: 结果输出文件
            input_file: 输入文件路径，成功时从该文件删除
            remove_tested: 是否从输入文件删除已回测的表达式
            
        Returns:
            回测结果列表
        """
        # 保存输入文件参数
        self.input_file = input_file
        self.remove_tested = remove_tested
        
        total = len(alphas)
        logger.info(f"Starting async batch test: {total} alphas, concurrency={self.concurrency}, input={input_file}")
        
        # 创建任务队列
        alphas_queue = deque(alphas)
        completed_ids: Set[str] = set()
        results: List[BacktestResult] = []
        
        # 创建工作协程
        workers = [
            asyncio.create_task(
                self._worker(i, alphas_queue, completed_ids, results)
            )
            for i in range(self.concurrency)
        ]
        
        # 等待所有工作协程完成
        await asyncio.gather(*workers)
        
        # 保存结果
        self._results = results
        self._save_results(output_file)
        
        logger.info(f"Async batch complete: {self.completed} success, {self.failed} failed, {self.skipped_429} 429")
        
        return results
    
    def _save_results(self, output_file: str):
        """保存结果到文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取已有结果
        existing = []
        if output_path.exists():
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                existing = []
        
        # 合并新结果
        existing_ids = {r.get('expression', '') for r in existing}
        for result in self._results:
            if result.expression not in existing_ids:
                existing.append(result.to_dict())
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    
    def stop(self):
        """停止回测"""
        self._stop_event.set()


# 兼容原有接口
class AsyncBacktestWrapper:
    """包装异步引擎，提供同步接口"""
    
    def __init__(self, *args, **kwargs):
        self._engine = AsyncBacktestEngine(*args, **kwargs)
    
    def run_batch(self, alphas: List[Dict], **kwargs) -> List[BacktestResult]:
        """同步执行批量回测"""
        return asyncio.run(self._engine.run_batch_async(alphas, **kwargs))
