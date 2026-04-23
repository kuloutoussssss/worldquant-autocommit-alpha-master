# -*- coding: utf-8 -*-
"""
中性化组合测试模块
功能：
1. 遍历所有中性化方式 × maxTrade 组合
2. 优质Alpha筛选条件
3. 自动打标签
"""
import time
import copy
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, asdict

from .api_client import BrainAPIClient
from .logger import logger


# 中性化方式列表
NEUTRALIZATION_OPTIONS = {
    'IND': ['REVERSION_AND_MOMENTUM', 'SLOW_AND_FAST', 'FAST', 'SLOW', 'CROWDING', 'MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'],
    'CHN': ['STATISTICAL', 'REVERSION_AND_MOMENTUM', 'SLOW_AND_FAST', 'FAST', 'SLOW', 'CROWDING', 'MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'],
    'CHN_A': ['STATISTICAL', 'REVERSION_AND_MOMENTUM', 'SLOW_AND_FAST', 'FAST', 'SLOW', 'CROWDING', 'MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'],
    'USA': ['STATISTICAL', 'REVERSION_AND_MOMENTUM', 'SLOW_AND_FAST', 'FAST', 'SLOW', 'CROWDING', 'MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'],
    'EUR': ['STATISTICAL', 'REVERSION_AND_MOMENTUM', 'SLOW_AND_FAST', 'FAST', 'SLOW', 'CROWDING', 'MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'],
}

# maxTrade 选项
MAX_TRADE_OPTIONS = ['ON', 'OFF']

# 优质Alpha筛选条件
QUALITY_ALPHA_CONDITIONS = [
    # 条件1: 换手率 <= 0.4, Sharpe >= 1.2, Margin >= 0.0009
    lambda r: r.get('turnover', 1) <= 0.4 and abs(r.get('sharpe', 0)) >= 1.2 and abs(r.get('margin', 0)) >= 0.0009,
    # 条件2: 换手率 <= 0.4, Sharpe >= 1.5, Margin >= 0.001
    lambda r: r.get('turnover', 1) <= 0.4 and abs(r.get('sharpe', 0)) >= 1.5 and abs(r.get('margin', 0)) >= 0.001,
    # 条件3: 换手率 <= 0.6, Sharpe >= 2.0, Margin >= 0.0015
    lambda r: r.get('turnover', 1) <= 0.6 and abs(r.get('sharpe', 0)) >= 2.0 and abs(r.get('margin', 0)) >= 0.0015,
]


@dataclass
class NeutralizationResult:
    """中性化组合测试结果"""
    alpha_id: str = ""
    expression: str = ""
    neutralization: str = ""
    max_trade: str = ""
    sharpe: float = 0.0
    fitness: float = 0.0
    turnover: float = 1.0
    margin: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    is_quality: bool = False
    status: str = "PENDING"

    def to_dict(self) -> Dict:
        return asdict(self)


def get_neutralization_options(region: str) -> List[str]:
    """获取指定区域的中性化选项"""
    region_upper = region.upper()
    if region_upper in NEUTRALIZATION_OPTIONS:
        return NEUTRALIZATION_OPTIONS[region_upper]
    # 默认返回除IND外的完整列表
    return NEUTRALIZATION_OPTIONS['CHN']


def is_quality_alpha(result: Dict) -> bool:
    """
    判断是否为优质Alpha

    判断条件（满足任一即可）：
    1. 换手率 <= 0.4, Sharpe >= 1.2, Margin >= 0.0009
    2. 换手率 <= 0.4, Sharpe >= 1.5, Margin >= 0.001
    3. 换手率 <= 0.6, Sharpe >= 2.0, Margin >= 0.0015
    """
    for condition in QUALITY_ALPHA_CONDITIONS:
        if condition(result):
            return True
    return False


def get_quality_conditions_description() -> str:
    """获取优质Alpha筛选条件描述"""
    return """
优质Alpha筛选条件（满足任一即可）：
1. 换手率 <= 0.4, Sharpe >= 1.2, Margin >= 0.0009
2. 换手率 <= 0.4, Sharpe >= 1.5, Margin >= 0.001
3. 换手率 <= 0.6, Sharpe >= 2.0, Margin >= 0.0015
"""


class NeutralizationTester:
    """
    中性化组合测试器

    使用方式：
    1. 初始化时指定基础Alpha设置
    2. 调用 test_all_combinations() 测试所有中性化 × maxTrade 组合
    3. 结果自动筛选优质Alpha并打标签
    """

    def __init__(
        self,
        expression: str,
        region: str = "USA",
        universe: str = "TOP3000",
        decay: int = 30,
        truncation: float = 0.08,
        delay: int = 1,
        base_alpha_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, Dict], None]] = None
    ):
        """
        初始化中性化测试器

        Args:
            expression: Alpha表达式
            region: 区域（USA, CHN, IND等）
            universe: Universe设置
            decay: Decay设置
            truncation: Truncation设置
            delay: Delay设置
            base_alpha_id: 基础Alpha ID（用于打标签）
            progress_callback: 进度回调 (current, total, result)
        """
        self.expression = expression
        self.region = region
        self.universe = universe
        self.decay = decay
        self.truncation = truncation
        self.delay = delay
        self.base_alpha_id = base_alpha_id
        self.progress_callback = progress_callback

        self.client = BrainAPIClient()
        self.results: List[NeutralizationResult] = []

        # 获取中性化选项
        self.neutralizations = get_neutralization_options(region)
        self.max_trades = MAX_TRADE_OPTIONS

        # 计算总任务数
        self.total_combinations = len(self.neutralizations) * len(self.max_trades)

    def test_single_combination(self, neutralization: str, max_trade: str) -> NeutralizationResult:
        """
        测试单个中性化 × maxTrade 组合

        Args:
            neutralization: 中性化方式
            max_trade: maxTrade设置 (ON/OFF)

        Returns:
            NeutralizationResult: 测试结果
        """
        result = NeutralizationResult(
            expression=self.expression,
            neutralization=neutralization,
            max_trade=max_trade,
            status="TESTING"
        )

        try:
            # 1. 提交回测任务
            submit_response = self.client.test_alpha(
                expression=self.expression,
                universe=self.universe,
                decay=self.decay,
                neutralization=neutralization,
                truncation=self.truncation,
                delay=self.delay,
                region=self.region,
                max_trade=max_trade  # 传递 maxTrade 参数
            )

            if not submit_response or submit_response.get('status') != 'OK':
                result.status = submit_response.get('error', 'Submit failed') if submit_response else 'No response'
                return result

            # 2. 获取 simulation URL
            location = submit_response.get('location', '')
            if not location:
                result.status = 'No location returned'
                return result

            # 3. 轮询获取回测结果
            logger.info(f"等待回测完成: {neutralization}/{max_trade}")
            sim_result = self.client.get_simulation_result(location, max_retries=60)

            if sim_result.get('status') == 'OK' and sim_result.get('data'):
                data = sim_result['data']
                # 检查 simulation 状态
                if data.get('status') == 'COMPLETE':
                    result.alpha_id = data.get('alpha', '')
                    metrics = data.get('metrics', {})
                    result.sharpe = metrics.get('sharpe', 0)
                    result.fitness = metrics.get('fitness', 0)
                    result.turnover = metrics.get('turnover', 1)
                    result.margin = metrics.get('margin', 0)
                    result.returns = metrics.get('returns', 0)
                    result.drawdown = metrics.get('drawdown', 0)
                    result.is_quality = is_quality_alpha({
                        'turnover': result.turnover,
                        'sharpe': result.sharpe,
                        'margin': result.margin
                    })
                    result.status = "OK"
                else:
                    result.status = data.get('status', 'INCOMPLETE')
            else:
                result.status = sim_result.get('error', 'Get result failed')

        except Exception as e:
            result.status = f"ERROR: {str(e)}"
            logger.error(f"测试失败 [{neutralization}/{max_trade}]: {e}")

        return result

    def test_all_combinations(self, concurrency: int = 1) -> List[NeutralizationResult]:
        """
        测试所有中性化 × maxTrade 组合

        Args:
            concurrency: 并发数（默认1，同步模式）

        Returns:
            List[NeutralizationResult]: 所有组合的测试结果
        """
        self.results = []
        completed = 0

        logger.info(f"开始测试 {self.total_combinations} 个组合...")
        logger.info(f"中性化方式: {self.neutralizations}")
        logger.info(f"maxTrade选项: {self.max_trades}")

        for neutralization in self.neutralizations:
            for max_trade in self.max_trades:
                completed += 1
                logger.info(f"[{completed}/{self.total_combinations}] 测试: {neutralization}/{max_trade}")

                result = self.test_single_combination(neutralization, max_trade)
                self.results.append(result)

                # 进度回调
                if self.progress_callback:
                    self.progress_callback(completed, self.total_combinations, result.to_dict())

                # 为优质Alpha打标签
                if result.is_quality and result.alpha_id and self.base_alpha_id:
                    self._tag_quality_alpha(result)

                # 尊重API限流
                if completed < self.total_combinations:
                    time.sleep(0.5)  # 组合测试间隔较短

        logger.info(f"测试完成！共 {len(self.results)} 个组合")
        quality_count = sum(1 for r in self.results if r.is_quality)
        logger.info(f"优质Alpha数量: {quality_count}")

        return self.results

    def _tag_quality_alpha(self, result: NeutralizationResult):
        """为优质Alpha打标签"""
        try:
            tags = ['quality_alpha']
            self.client.set_alpha_properties(
                alpha_id=result.alpha_id,
                name=f"{self.base_alpha_id}_quality",
                tags=tags
            )
            logger.info(f"已为优质Alpha打标签: {result.alpha_id}")
        except Exception as e:
            logger.error(f"打标签失败: {e}")

    def get_best_result(self) -> Optional[NeutralizationResult]:
        """获取Sharpe最高的结果"""
        if not self.results:
            return None
        return max(self.results, key=lambda r: abs(r.sharpe) if r.status == "OK" else 0)

    def get_quality_results(self) -> List[NeutralizationResult]:
        """获取所有优质Alpha结果"""
        return [r for r in self.results if r.is_quality]

    def get_summary(self) -> Dict:
        """获取测试摘要"""
        ok_results = [r for r in self.results if r.status == "OK"]
        quality_results = [r for r in self.results if r.is_quality]

        return {
            'total_combinations': self.total_combinations,
            'completed': len(ok_results),
            'quality_count': len(quality_results),
            'best_sharpe': max(abs(r.sharpe) for r in ok_results) if ok_results else 0,
            'best_combination': self.get_best_result().to_dict() if self.get_best_result() else None,
            'quality_alphas': [r.to_dict() for r in quality_results]
        }


def test_neutralization_combinations(
    expression: str,
    region: str = "USA",
    universe: str = "TOP3000",
    decay: int = 30,
    truncation: float = 0.08,
    base_alpha_id: Optional[str] = None,
    concurrency: int = 1,
    progress_callback: Optional[Callable[[int, int, Dict], None]] = None
) -> List[NeutralizationResult]:
    """
    便捷函数：测试所有中性化 × maxTrade 组合

    Args:
        expression: Alpha表达式
        region: 区域
        universe: Universe设置
        decay: Decay设置
        truncation: Truncation设置
        base_alpha_id: 基础Alpha ID（用于打标签）
        concurrency: 并发数
        progress_callback: 进度回调

    Returns:
        List[NeutralizationResult]: 测试结果列表
    """
    tester = NeutralizationTester(
        expression=expression,
        region=region,
        universe=universe,
        decay=decay,
        truncation=truncation,
        base_alpha_id=base_alpha_id,
        progress_callback=progress_callback
    )

    return tester.test_all_combinations(concurrency=concurrency)
