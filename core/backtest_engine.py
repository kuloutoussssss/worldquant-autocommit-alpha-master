# -*- coding: utf-8 -*-
"""
Alpha 回测引擎 - 统一核心模块
功能：封装回测逻辑，支持断点续传和进度管理
统一命令行和前端的回测逻辑
"""
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Callable, Set
from dataclasses import dataclass, field, asdict

from .api_client import BrainAPIClient
from .db_manager import get_database
from .logger import logger

# 429限流重试配置（指数退避）
MAX_RETRIES = 5
INITIAL_DELAY = 60
MAX_DELAY = 1800
BACKOFF_FACTOR = 2.0


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
class BacktestProgress:
    """回测进度状态"""
    task_id: str = ""
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped_429: int = 0
    processed_ids: List[str] = field(default_factory=list)
    start_time: str = ""
    last_update: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class BacktestEngine:
    """
    Alpha 回测引擎 - 统一核心模块

    功能：
    1. 统一回测逻辑
    2. 支持断点续传
    3. 统一的 429 处理
    4. 进度回调机制

    使用方式：
    1. 命令行模式：使用 run_batch() 方法
    2. 前端模式：使用 run_with_progress() 方法
    """

    def __init__(
        self,
        progress_callback: Optional[Callable[[BacktestProgress], None]] = None,
        result_callback: Optional[Callable[[BacktestResult], None]] = None,
        stop_check_callback: Optional[Callable[[], bool]] = None
    ):
        """
        初始化回测引擎

        Args:
            progress_callback: 进度回调函数
            result_callback: 结果回调函数（每个 Alpha 测试完成后调用）
            stop_check_callback: 停止检查回调函数
        """
        self.progress_callback = progress_callback
        self.result_callback = result_callback
        self.stop_check_callback = stop_check_callback
        self.client = BrainAPIClient()
        self.db = get_database()

        # 统计信息
        self.completed = 0
        self.failed = 0
        self.skipped_429 = 0
        self.processed_ids: Set[str] = set()

    def is_tested(self, expression: str) -> bool:
        """检查表达式是否已测试"""
        return self.db.is_expression_tested(expression)

    def load_alphas(
        self,
        input_file: str = "data/alphas/to_test.txt"
    ) -> List[Dict]:
        """从文件加载 Alpha 列表，跳过已测试的"""
        input_path = Path(input_file)
        if not input_path.exists():
            logger.error(f"Input file not exists: {input_path}")
            return []

        tested_expressions = self.db.get_tested_expressions()
        logger.info(f"Loaded {len(tested_expressions)} tested expressions from database")

        alphas = []
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 尝试 JSON 格式
        if content.strip().startswith('[') or content.strip().startswith('{'):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    alphas = data
                elif isinstance(data, dict) and 'alphas' in data:
                    alphas = data['alphas']
            except json.JSONDecodeError:
                pass

        # 文本格式: expression|universe|decay|neutralization|truncation
        if not alphas:
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                alpha = {
                    'expression': parts[0].strip(),
                    'universe': parts[1].strip() if len(parts) > 1 else 'TOP3000',
                    'decay': parts[2].strip() if len(parts) > 2 else '30',
                    'neutralization': parts[3].strip().upper() if len(parts) > 3 else 'SECTOR',
                    'truncation': parts[4].strip() if len(parts) > 4 else '0.08'
                }
                alphas.append(alpha)

        # 过滤掉已测试的Alpha
        original_count = len(alphas)
        alphas = [a for a in alphas if not self.is_tested(a['expression'])]
        skipped = original_count - len(alphas)

        logger.info(f"Loaded {len(alphas)} alphas (skipped {skipped} already tested)")
        return alphas

    def test_single(
        self,
        expression: str,
        universe: str = "TOP3000",
        decay: int = 30,
        neutralization: str = "SECTOR",
        truncation: float = 0.08,
        region: str = "USA",
        test_period: str = "P2Y0M"
    ) -> BacktestResult:
        """测试单个 Alpha，使用 API Client 的 429 处理"""
        result = BacktestResult(expression=expression)

        try:
            api_result = self.client.test_alpha(
                expression=expression,
                universe=universe,
                decay=decay,
                neutralization=neutralization,
                truncation=truncation,
                region=region,
                test_period=test_period
            )

            if api_result.get("status") == "OK":
                location = api_result.get("location", "")

                # 获取回测结果
                sim_result = self.client.get_simulation_result(location)

                if sim_result.get("status") == "OK":
                    data = sim_result.get("data", {})
                    is_data = data.get("is", {})

                    result.alpha_id = location.split("/")[-1] if "/" in location else ""
                    result.sharpe = is_data.get("sharpe", 0) or 0
                    result.fitness = is_data.get("fitness", 0) or 0
                    result.turnover = is_data.get("turnover", 1) or 1
                    result.returns = is_data.get("returns", 0) or 0
                    result.drawdown = is_data.get("drawdown", 0) or 0
                    result.status = "OK"
                    return result
                else:
                    result.status = "ERROR"
                    result.error = sim_result.get("error", "Simulation failed")
            else:
                error_msg = api_result.get("error", "Unknown error")
                result.status = "ERROR"
                result.error = error_msg
                result.is_429 = "429" in str(error_msg) or "LIMIT_EXCEEDED" in str(error_msg)

        except Exception as e:
            result.status = "ERROR"
            result.error = str(e)
            result.is_429 = "429" in str(e) or "LIMIT_EXCEEDED" in str(e)
            logger.error(f"Test error: {e}")

        return result

    def test_single_with_retry(
        self,
        expression: str,
        universe: str = "TOP3000",
        decay: int = 30,
        neutralization: str = "SECTOR",
        truncation: float = 0.08,
        region: str = "USA",
        test_period: str = "P2Y0M",
        auto_retry_429: bool = True
    ) -> BacktestResult:
        """测试单个 Alpha，支持 429 自动重试"""
        result = self.test_single(
            expression, universe, decay, neutralization, truncation, region, test_period
        )

        # 处理 429 错误
        if result.is_429 and auto_retry_429:
            retry_count = 0
            delay = INITIAL_DELAY

            while retry_count < MAX_RETRIES:
                if retry_count > 0:
                    wait_time = min(delay, MAX_DELAY)
                    logger.warning(f"429限流! 等待 {wait_time}秒后重试 ({retry_count}/{MAX_RETRIES})...")
                    time.sleep(wait_time)
                    delay *= BACKOFF_FACTOR

                result = self.test_single(
                    expression, universe, decay, neutralization, truncation, region, test_period
                )

                if not result.is_429:
                    break

                retry_count += 1

            if result.is_429:
                result.status = "SKIPPED_429"
                result.error = f"429 after {MAX_RETRIES} retries"
                self.skipped_429 += 1

        return result

    def remove_from_file(self, expression: str, input_file: str):
        """从输入文件删除已回测的表达式"""
        input_path = Path(input_file)
        if not input_path.exists():
            return

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
            for line in remaining:
                f.write(line + '\n')

    def save_to_database(self, result: BacktestResult):
        """保存结果到数据库"""
        self.db.add_tested_expression(
            expression=result.expression,
            alpha_id=result.alpha_id,
            sharpe=result.sharpe,
            fitness=result.fitness,
            turnover=result.turnover,
            returns=result.returns,
            drawdown=result.drawdown,
            status=result.status
        )

    def _check_stop(self) -> bool:
        """检查是否应该停止"""
        if self.stop_check_callback:
            return self.stop_check_callback()
        return False

    def _update_progress(self, total: int):
        """更新进度"""
        if self.progress_callback:
            progress = BacktestProgress(
                total=total,
                completed=self.completed,
                failed=self.failed,
                skipped_429=self.skipped_429,
                processed_ids=list(self.processed_ids),
                last_update=datetime.now().isoformat()
            )
            self.progress_callback(progress)

    def run_batch(
        self,
        alphas: List[Dict],
        delay: float = 5.0,
        auto_retry_429: bool = True,
        save_results: bool = True,
        output_file: str = "data/results/batch_results.json",
        remove_tested: bool = True,
        input_file: str = "data/alphas/to_test.txt"
    ) -> List[BacktestResult]:
        """
        批量回测（命令行模式）

        Args:
            alphas: Alpha 列表
            delay: 请求间隔（秒）
            auto_retry_429: 是否自动重试429错误
            save_results: 是否保存结果到文件
            output_file: 结果输出文件
            remove_tested: 是否从输入文件删除已回测的表达式
            input_file: 输入文件路径

        Returns:
            回测结果列表
        """
        total = len(alphas)
        all_results = []

        logger.info(f"Starting batch test: {total} alphas, delay={delay}s, auto_retry_429={auto_retry_429}")

        for i, alpha in enumerate(alphas, 1):
            # 检查停止信号
            if self._check_stop():
                logger.info("Received stop signal")
                break

            expr_preview = alpha['expression'][:50] + ('...' if len(alpha['expression']) > 50 else '')
            logger.info(f"[{i}/{total}] Testing: {expr_preview}")

            # 测试 Alpha
            result = self.test_single_with_retry(
                expression=alpha['expression'],
                universe=alpha.get('universe', 'TOP3000'),
                decay=int(alpha.get('decay', 30)),
                neutralization=alpha.get('neutralization', 'SECTOR'),
                truncation=float(alpha.get('truncation', 0.08)),
                auto_retry_429=auto_retry_429
            )
            result.index = i
            result.test_time = datetime.now().isoformat()

            all_results.append(result)

            # 更新统计
            if result.status == "OK":
                self.completed += 1
                self.processed_ids.add(result.expression)
                self.save_to_database(result)

                if remove_tested:
                    self.remove_from_file(result.expression, input_file)

                logger.info(f"  Sharpe={(result.sharpe or 0):.2f} Fitness={(result.fitness or 0):.2f} "
                           f"Turnover={(result.turnover or 0)*100:.1f}%")
            elif result.status == "SKIPPED_429":
                logger.warning(f"  429错误跳过: {result.error}")
            else:
                self.failed += 1
                logger.error(f"  Error: {result.error}")

            # 回调
            if self.result_callback:
                self.result_callback(result)

            # 更新进度
            self._update_progress(total)

            # 延迟
            if i < total:
                time.sleep(delay)

            # 保存进度
            if i % 50 == 0 and save_results:
                self._save_results(all_results, output_file)

        # 保存最终结果
        if save_results:
            self._save_results(all_results, output_file)

        self._print_summary(all_results)
        return all_results

    def run_with_progress(
        self,
        task_id: str,
        untested_data: List,
        params: Dict,
        resume: bool = False,
        input_file: str = None
    ) -> Dict:
        """
        带进度管理的回测（前端模式）

        Args:
            task_id: 任务ID
            untested_data: 待回测数据 [(expression, params), ...]
            params: 回测参数
            resume: 是否从断点恢复
            input_file: 待回测文件路径，成功时从该文件删除

        Returns:
            任务结果
        """
        from web.utils.task_progress import get_progress_manager, TaskProgress

        progress_mgr = get_progress_manager()
        total = len(untested_data)

        logger.info(f"[{task_id}] BacktestEngine 任务启动")
        logger.info(f"[{task_id}] 待回测数量: {total}")

        # 加载或创建进度
        if resume:
            saved_progress = progress_mgr.load_progress(task_id)
            if saved_progress:
                logger.info(f"[{task_id}] 找到断点进度，恢复执行")
                self.completed = saved_progress.completed
                self.failed = saved_progress.failed
                self.processed_ids = set(saved_progress.processed_ids)
                # 过滤掉已处理的表达式
                untested_data = [
                    expr for expr in untested_data
                    if expr.split("|")[0].strip() not in self.processed_ids
                ]
                logger.info(f"[{task_id}] 剩余待处理: {len(untested_data)}")
            else:
                logger.info(f"[{task_id}] 未找到断点进度，从头开始")
                resume = False

        if not resume:
            self.completed = 0
            self.failed = 0
            self.skipped_429 = 0
            self.processed_ids = set()

            # 初始化进度
            progress = TaskProgress(task_id, "backtest", total)
            progress_mgr.save_progress(progress)

        # 开始回测
        for i, expression in enumerate(untested_data):
            # 检查停止信号
            if self._check_stop():
                logger.info(f"[{task_id}] 收到停止信号")
                return {"status": "stopped", "completed": self.completed, "failed": self.failed}

            # 解析表达式参数
            parts = expression.split("|")
            expr = parts[0].strip()
            p_universe = parts[1].strip() if len(parts) > 1 else params.get("universe", "TOP3000")
            p_decay = int(parts[2].strip()) if len(parts) > 2 else params.get("decay", 30)
            p_neutralization = parts[3].strip() if len(parts) > 3 else params.get("neutralization", "SUBINDUSTRY")
            p_truncation = float(parts[4].strip()) if len(parts) > 4 else params.get("truncation", 0.08)

            logger.info(f"[{task_id}] 回测 [{i+1}/{len(untested_data)}]: {expr[:50]}...")

            # 测试 Alpha（使用 API Client 的 429 处理）
            result = self.test_single(
                expression=expr,
                universe=p_universe,
                decay=p_decay,
                neutralization=p_neutralization,
                truncation=p_truncation,
                region=params.get("region", "USA"),
                test_period=params.get("test_period", "P2Y0M")
            )

            if result.status == "OK":
                self.completed += 1
                self.processed_ids.add(expr)
                self.save_to_database(result)

                # 成功时从待回测文件删除
                if input_file:
                    self.remove_from_file(expr, input_file)

                # 回调
                if self.result_callback:
                    result.test_time = datetime.now().isoformat()
                    self.result_callback(result)

                # 保存进度
                progress_mgr.mark_processed(task_id, expr, True)
                logger.info(f"[{task_id}] 成功: {expr[:30]}...")
            else:
                self.failed += 1
                self.processed_ids.add(expr)
                progress_mgr.mark_processed(task_id, expr, False)
                logger.warning(f"[{task_id}] ❌ 失败: {result.error}")
                
                # 失败时也调用回调
                if self.result_callback:
                    result.test_time = datetime.now().isoformat()
                    self.result_callback(result)

            # 更新进度
            self._update_progress(total)

        # 清理进度
        progress_mgr.clear_completed(task_id)

        return {
            "status": "completed",
            "completed": self.completed,
            "failed": self.failed,
            "skipped_429": self.skipped_429
        }

    def _save_results(self, results: List[BacktestResult], output_file: str):
        """保存结果到文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total': len(results),
                'results': [r.to_dict() for r in results]
            }, f, ensure_ascii=False, indent=2)

        logger.info(f"Results saved to {output_path}")

    def _print_summary(self, results: List[BacktestResult]):
        """打印汇总"""
        successful = [r for r in results if r.status == "OK"]
        skipped_429 = [r for r in results if r.status == "SKIPPED_429"]
        failed = [r for r in results if r.status == "ERROR"]

        print(f"\n{'='*60}")
        print(f"Batch Test Summary")
        print(f"{'='*60}")
        print(f"  Total: {len(results)}")
        print(f"  Successful: {len(successful)}")
        print(f"  Failed: {len(failed)}")
        print(f"  429 Skipped: {len(skipped_429)}")
        print(f"  Already tested: {self.db.get_tested_count()}")

        if successful:
            # 按 fitness 排序
            successful.sort(key=lambda x: x.fitness, reverse=True)

            qualified = [r for r in successful
                        if r.sharpe >= 1.25
                        and r.fitness >= 1.0
                        and r.turnover <= 0.70]

            print(f"\n  Qualified (Sharpe>=1.25, Fitness>=1.0, Turnover<=70%): {len(qualified)}")

            if qualified:
                print(f"\n  Top 5 by Fitness:")
                for i, r in enumerate(qualified[:5], 1):
                    print(f"    {i}. {r.alpha_id}: "
                          f"Sharpe={r.sharpe:.2f} "
                          f"Fitness={r.fitness:.2f} "
                          f"Turnover={r.turnover*100:.1f}%")

        print(f"{'='*60}")


# 便捷函数
def create_engine(
    progress_callback: Optional[Callable] = None,
    result_callback: Optional[Callable] = None,
    stop_check_callback: Optional[Callable] = None
) -> BacktestEngine:
    """创建回测引擎实例"""
    return BacktestEngine(
        progress_callback=progress_callback,
        result_callback=result_callback,
        stop_check_callback=stop_check_callback
    )


def run_cli_batch(
    input_file: str = "data/alphas/to_test.txt",
    delay: float = 5.0,
    max_count: Optional[int] = None,
    auto_retry_429: bool = True
) -> List[BacktestResult]:
    """命令行批量回测快捷函数"""
    engine = BacktestEngine()
    alphas = engine.load_alphas(input_file)

    if max_count:
        alphas = alphas[:max_count]

    return engine.run_batch(
        alphas=alphas,
        delay=delay,
        auto_retry_429=auto_retry_429
    )
