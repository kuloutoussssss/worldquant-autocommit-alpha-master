# -*- coding: utf-8 -*-
"""
Pydantic Schemas - 请求/响应模型定义
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# ========== 通用响应 ==========
class BaseResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    code: Optional[str] = None
    detail: Optional[Any] = None


# ========== 任务相关 ==========
class TaskDetail(BaseModel):
    """任务详情"""
    time: str
    message: str


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    name: Optional[str] = None
    status: str
    progress: float = 0
    completed: int = 0
    total: int = 0
    failed: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    details: List[TaskDetail] = []
    description: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class TaskListResponse(BaseResponse):
    tasks: List[TaskResponse]


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(backtest|submit|sync)$")
    params: Dict[str, Any] = Field(default_factory=dict)


class TaskUpdateRequest(BaseModel):
    """更新任务请求"""
    status: Optional[str] = Field(None, pattern="^(running|completed|failed|stopped)$")
    progress: Optional[float] = Field(None, ge=0, le=100)
    error: Optional[str] = None


# ========== 回测相关 ==========
class BacktestParams(BaseModel):
    """回测参数"""
    universe: str = "TOP3000"
    region: str = "USA"
    decay: int = 30
    neutralization: str = "SUBINDUSTRY"
    truncation: float = 0.08
    test_period: str = "P2Y0M"
    delay: float = 5.0
    auto_retry: bool = True
    concurrency: int = 1  # 并发数（安全值：1）
    request_delay: float = 3.0  # 请求间隔（秒）


class BacktestRequest(BaseModel):
    """回测请求"""
    data: Optional[List[str]] = None  # 待回测的 Alpha 列表
    params: Optional[BacktestParams] = None  # 回测参数（可选，由 Alpha 自带）
    max_count: Optional[int] = Field(None, gt=0, le=50000)


class BacktestResult(BaseModel):
    """回测结果"""
    alpha_id: str
    expression: str
    sharpe: Optional[float]
    fitness: Optional[float]
    turnover: Optional[float]
    returns: Optional[float]
    drawdown: Optional[float]
    status: str
    error: Optional[str] = None


class BacktestResponse(BaseResponse):
    task_id: str
    total: int
    results: List[BacktestResult] = []


# ========== 提交相关 ==========
class SubmitRequest(BaseModel):
    """提交请求"""
    alpha_ids: Optional[List[str]] = None
    target_success: int = Field(2, ge=1, le=10)
    num_to_submit: Optional[int] = Field(None, ge=1, le=10, description="兼容前端字段名")
    
    def __init__(self, **data):
        # 兼容前端发送的 num_to_submit 字段
        if 'num_to_submit' in data and 'target_success' not in data:
            data['target_success'] = data.pop('num_to_submit')
        super().__init__(**data)


class SubmitResult(BaseModel):
    """提交结果"""
    success: List[str]
    failed: List[str]
    skipped_429: List[str]
    total: int


class SubmitResponse(BaseResponse):
    result: SubmitResult


# ========== 同步相关 ==========
class SyncResponse(BaseResponse):
    """同步响应"""
    new_count: int = 0
    update_count: int = 0
    total: int = 0


# ========== 数据库相关 ==========
class AlphaInfo(BaseModel):
    """Alpha 信息"""
    alpha_id: str
    expression: str
    sharpe: Optional[float]
    fitness: Optional[float]
    turnover: Optional[float]
    returns: Optional[float]
    drawdown: Optional[float]
    created_at: Optional[str]
    submitted_at: Optional[str]
    checks_passed: bool
    submit_fail_count: int = 0


class AlphaListResponse(BaseResponse):
    alphas: List[AlphaInfo]
    total: int


class CandidatePoolResponse(BaseResponse):
    """候选池响应"""
    total: int
    submitted: int
    available: int
    failed: int
    candidates: List[AlphaInfo]
