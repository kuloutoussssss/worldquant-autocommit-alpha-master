# -*- coding: utf-8 -*-
"""
Core 模块
"""
from .api_client import BrainAPIClient
from .db_manager import get_database
from .backtest_engine import BacktestEngine, BacktestResult
from .submit import submit_alpha_ids, submit_from_db
from .neutralization_tester import (
    NeutralizationTester,
    NeutralizationResult,
    test_neutralization_combinations,
    get_neutralization_options,
    is_quality_alpha,
    get_quality_conditions_description,
    NEUTRALIZATION_OPTIONS
)

# 异步模块（可选导入，需要 aiohttp）
try:
    from .async_backtest_engine import AsyncBacktestEngine, AsyncBacktestWrapper
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    AsyncBacktestEngine = None
    AsyncBacktestWrapper = None

try:
    from .async_submit import submit_alpha_ids_async, submit_alpha_ids_sync
    ASYNC_SUBMIT_AVAILABLE = True
except ImportError:
    ASYNC_SUBMIT_AVAILABLE = False
    submit_alpha_ids_async = None
    submit_alpha_ids_sync = None

__all__ = [
    'BrainAPIClient',
    'get_database',
    'BacktestEngine',
    'BacktestResult',
    'submit_alpha_ids',
    'submit_from_db',
    'AsyncBacktestEngine',
    'AsyncBacktestWrapper',
    'submit_alpha_ids_async',
    'submit_alpha_ids_sync',
    'ASYNC_AVAILABLE',
    'ASYNC_SUBMIT_AVAILABLE',
    # 中性化测试模块
    'NeutralizationTester',
    'NeutralizationResult',
    'test_neutralization_combinations',
    'get_neutralization_options',
    'is_quality_alpha',
    'get_quality_conditions_description',
    'NEUTRALIZATION_OPTIONS',
]
