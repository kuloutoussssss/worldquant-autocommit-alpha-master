# -*- coding: utf-8 -*-
"""
Alpha 批量回测工具
已统一使用 core/async_backtest_engine.py 作为核心模块（异步队列模式）
"""
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Optional, Set

from .async_backtest_engine import AsyncBacktestEngine, BacktestResult
from .db_manager import get_database
from .logger import logger

# 429限流重试配置
MAX_RETRIES = 5
RETRY_DELAY = 30

# 默认路径
DEFAULT_INPUT = "data/alphas/to_test.txt"
DEFAULT_OUTPUT = "data/results/batch_results.json"
DEFAULT_CONCURRENCY = 3  # 异步并发数


class AlphaBatchTester:
    """Alpha 批量回测器 - 使用异步队列引擎"""

    def __init__(self, input_file: str = DEFAULT_INPUT, output_file: str = DEFAULT_OUTPUT):
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.results = []
        self._engine = None
        self._db = get_database()

    def _on_result(self, result: BacktestResult):
        """结果回调"""
        self.results.append(result)

    def load_alphas(self) -> List[Dict]:
        """从文件加载 Alpha 列表，跳过已测试的"""
        if not self.input_file.exists():
            logger.warning(f"Input file not found: {self.input_file}")
            return []
        
        tested_exprs = self._db.get_tested_expressions()
        
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if content.startswith('['):
                # JSON 格式
                items = json.loads(content)
            else:
                # 文本格式（每行一个表达式）
                items = [line.strip() for line in content.split('\n') if line.strip()]
            
            alphas = []
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    expr = item.get('expression', '')
                else:
                    expr = item.split('|')[0].strip() if '|' in item else item.strip()
                
                if expr and expr not in tested_exprs:
                    if isinstance(item, dict):
                        alphas.append(item)
                    else:
                        alphas.append({'expression': expr, 'index': i + 1})
            
            logger.info(f"Loaded {len(alphas)} alphas (skipped {len(items) - len(alphas)} already tested)")
            return alphas
            
        except Exception as e:
            logger.error(f"Failed to load alphas: {e}")
            return []

    def run(self, delay: float = 5.0, max_count: Optional[int] = None, concurrency: int = DEFAULT_CONCURRENCY):
        """运行批量回测（异步队列模式）
        
        Args:
            delay: 请求间隔（秒），仅用于兼容旧接口
            max_count: 最大测试数量
            concurrency: 并发数
        """
        alphas = self.load_alphas()
        if not alphas:
            logger.error("No alphas to test")
            return

        if max_count:
            alphas = alphas[:max_count]

        logger.info(f"Starting async batch test: {len(alphas)} alphas, concurrency={concurrency}, delay={delay}s")
        
        # 使用异步引擎
        self._engine = AsyncBacktestEngine(
            progress_callback=None,
            result_callback=self._on_result,
            concurrency=concurrency,
            remove_tested=True,
            input_file=str(self.input_file)
        )
        
        # 异步执行
        results = asyncio.run(
            self._engine.run_batch_async(
                alphas=alphas,
                output_file=str(self.output_file),
                input_file=str(self.input_file)
            )
        )
        
        self.results = results
        logger.info(f"Batch complete: {self._engine.completed} success, {self._engine.failed} failed, {self._engine.skipped_429} 429")

    def _save_progress(self, results: List):
        """保存进度"""
        import json
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Progress saved: {len(results)} results")

    def _save_results(self, results: List):
        """保存结果"""
        pass  # AsyncBacktestEngine 内部已保存

    def _print_summary(self, results: List, retry_stats: Dict = None):
        """打印汇总"""
        if self._engine:
            logger.info("=" * 50)
            logger.info(f"总完成: {self._engine.completed}")
            logger.info(f"总失败: {self._engine.failed}")
            logger.info(f"429跳过: {self._engine.skipped_429}")
            logger.info("=" * 50)


def run_async_batch(input_file: str = DEFAULT_INPUT, output_file: str = DEFAULT_OUTPUT,
                    concurrency: int = DEFAULT_CONCURRENCY, max_count: Optional[int] = None):
    """
    异步批量回测（命令行使用）
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        concurrency: 并发数（默认3）
        max_count: 最大测试数量
    """
    tester = AlphaBatchTester(input_file, output_file)
    tester.run(delay=0, max_count=max_count, concurrency=concurrency)
    return tester.results
