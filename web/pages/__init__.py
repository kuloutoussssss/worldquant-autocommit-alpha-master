# -*- coding: utf-8 -*-
"""
页面模块
"""
from .alpha_list import page_alpha_list
from .backtest import page_backtest
from .results import page_results
from .filter import page_filter
from .submit import page_submit
from .factor_builder import page_factor_builder
from .workflow import page_one_click_workflow
from .logs import page_logs
from .database import page_database
from .tasks import page_tasks

__all__ = [
    'page_alpha_list',
    'page_backtest',
    'page_results',
    'page_filter',
    'page_submit',
    'page_factor_builder',
    'page_one_click_workflow',
    'page_logs',
    'page_database',
    'page_tasks'
]
