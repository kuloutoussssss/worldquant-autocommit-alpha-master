# -*- coding: utf-8 -*-
"""
Alpha 批量回测工具
已统一使用 core/backtest_engine.py 作为核心模块
保留此类用于向后兼容，新代码建议直接使用 BacktestEngine
"""
import time
from pathlib import Path
from typing import List, Dict, Optional, Set

from .backtest_engine import BacktestEngine, BacktestResult
from .db_manager import get_database
from .logger import logger

# 429限流重试配置（指数退避）- 已废弃，使用 backtest_engine 中的配置
MAX_RETRIES = 5
INITIAL_DELAY = 60
MAX_DELAY = 1800
BACKOFF_FACTOR = 2.0

# 默认路径
DEFAULT_INPUT = "data/alphas/to_test.txt"
DEFAULT_OUTPUT = "data/results/batch_results.json"


class AlphaBatchTester:
    """Alpha 批量回测器 - 使用统一回测引擎"""

    def __init__(self, input_file: str = DEFAULT_INPUT, output_file: str = DEFAULT_OUTPUT):
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        # 使用统一的回测引擎
        self.engine = BacktestEngine(
            result_callback=self._on_result,
            stop_check_callback=self._default_stop_check
        )

        self.results = []

    def _on_result(self, result: BacktestResult):
        """结果回调"""
        self.results.append(result)

    def _default_stop_check(self) -> bool:
        """默认停止检查（始终返回 False，不停止）"""
        return False

    def _load_completed_expressions(self) -> Set[str]:
        """从数据库加载已测试的表达式"""
        return self.engine.db.get_tested_expressions()

    def is_tested(self, expression: str) -> bool:
        """检查表达式是否已测试"""
        return self.engine.is_tested(expression)

    def _remove_from_file(self, expression: str):
        """从输入文件删除已回测的表达式"""
        self.engine.remove_from_file(expression, str(self.input_file))

    def add_tested(self, expression: str, result: Dict):
        """添加已测试的表达式到数据库"""
        self.engine.save_to_database(BacktestResult(
            expression=expression,
            alpha_id=result.get('alpha_id', ''),
            sharpe=result.get('sharpe', 0),
            fitness=result.get('fitness', 0),
            turnover=result.get('turnover', 1),
            returns=result.get('returns', 0),
            drawdown=result.get('drawdown', 0),
            status=result.get('status', 'OK')
        ))

    def load_alphas(self) -> List[Dict]:
        """从文件加载 Alpha 列表，支持文本格式和JSON格式，跳过已测试的"""
        return self.engine.load_alphas(str(self.input_file))

    def test_single(self, alpha: Dict) -> Optional[Dict]:
        """测试单个 Alpha（兼容旧接口）"""
        result = self.engine.test_single_with_retry(
            expression=alpha['expression'],
            universe=alpha.get('universe', 'TOP3000'),
            decay=int(alpha.get('decay', 30)),
            neutralization=alpha.get('neutralization', 'SECTOR'),
            truncation=float(alpha.get('truncation', 0.08))
        )

        if result.status == "OK":
            return {
                'alpha_id': result.alpha_id,
                'expression': result.expression,
                'sharpe': result.sharpe,
                'fitness': result.fitness,
                'turnover': result.turnover,
                'returns': result.returns,
                'drawdown': result.drawdown,
                'status': 'OK'
            }
        else:
            return {
                'expression': result.expression,
                'status': 'ERROR',
                'error': result.error,
                'is_429': result.is_429
            }

    def _retry_with_backoff(self, alpha: Dict, i: int, total: int) -> Dict:
        """使用指数退避重试机制处理429错误（已废弃，使用 engine）"""
        result = self.engine.test_single_with_retry(
            expression=alpha['expression'],
            universe=alpha.get('universe', 'TOP3000'),
            decay=int(alpha.get('decay', 30)),
            neutralization=alpha.get('neutralization', 'SECTOR'),
            truncation=float(alpha.get('truncation', 0.08)),
            auto_retry_429=True
        )

        if result.status == "OK":
            return {
                'alpha_id': result.alpha_id,
                'expression': result.expression,
                'sharpe': result.sharpe,
                'fitness': result.fitness,
                'turnover': result.turnover,
                'returns': result.returns,
                'drawdown': result.drawdown,
                'status': 'OK'
            }
        elif result.status == "SKIPPED_429":
            return {
                'expression': result.expression,
                'status': 'SKIPPED_429',
                'error': result.error,
                'is_429': True
            }
        else:
            return {
                'expression': result.expression,
                'status': 'ERROR',
                'error': result.error,
                'is_429': result.is_429
            }

    def run(self, delay: float = 5.0, max_count: Optional[int] = None, auto_retry: bool = True):
        """运行批量回测（使用统一引擎）"""
        alphas = self.load_alphas()
        if not alphas:
            logger.error("No alphas to test")
            return

        if max_count:
            alphas = alphas[:max_count]

        # 使用统一引擎运行
        self.engine.run_batch(
            alphas=alphas,
            delay=delay,
            auto_retry_429=auto_retry,
            save_results=True,
            output_file=str(self.output_file),
            remove_tested=True,
            input_file=str(self.input_file)
        )

        # 收集结果用于汇总
        self.results = self.engine.results

    def _save_progress(self, results: List):
        """保存进度（兼容旧接口）"""
        import json
        from datetime import datetime
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Progress saved: {len(results)} results")

    def _save_results(self, results: List):
        """保存结果（兼容旧接口）"""
        self.engine._save_results(results, str(self.output_file))

    def _print_summary(self, results: List, retry_stats: Dict = None):
        """打印汇总（兼容旧接口）"""
        self.engine._print_summary(results)


def run_async_batch(input_file: str = DEFAULT_INPUT, output_file: str = DEFAULT_OUTPUT,
                    concurrency: int = 5, max_count: Optional[int] = None):
    """
    异步批量回测（命令行使用）
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        concurrency: 并发数
        max_count: 最大测试数量
    """
    import asyncio
    from .async_backtest_engine import AsyncBacktestEngine
    
    tester = AlphaBatchTester(input_file, output_file)
    alphas = tester.load_alphas()
    
    if not alphas:
        logger.error("No alphas to test")
        return
    
    if max_count:
        alphas = alphas[:max_count]
    
    logger.info(f"Starting async batch test: {len(alphas)} alphas, concurrency={concurrency}")
    
    # 创建异步引擎，自动删除已回测的表达式
    engine = AsyncBacktestEngine(
        concurrency=concurrency,
        remove_tested=True,
        input_file=str(input_file)
    )
    results = asyncio.run(engine.run_batch_async(alphas, output_file, input_file=str(input_file)))
    
    logger.info(f"Async batch complete: {engine.completed} success, {engine.failed} failed, {engine.skipped_429} 429")
    
    return results
