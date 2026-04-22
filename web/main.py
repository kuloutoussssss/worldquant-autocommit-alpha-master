# -*- coding: utf-8 -*-
"""
FastAPI 主入口
WorldQuant Alpha 自动化系统后端 API
"""
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from web.api import tasks, backtest, submit, sync, database
from web.utils.middleware import RateLimitMiddleware
from web.utils.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("🚀 FastAPI 服务器启动中...")
    yield
    # 关闭时
    print("👋 FastAPI 服务器关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="WorldQuant Alpha Manager API",
    description="Alpha 自动化回测、提交、管理系统",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 速率限制中间件（可选，每分钟 100 请求）
# app.add_middleware(RateLimitMiddleware, max_requests=100, window=60)

# 注册异常处理器
register_exception_handlers(app)

# 注册路由
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务管理"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])
app.include_router(submit.router, prefix="/api/submit", tags=["提交"])
app.include_router(sync.router, prefix="/api/sync", tags=["同步"])
app.include_router(database.router, prefix="/api/db", tags=["数据库"])


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"success": True, "status": "healthy", "service": "WorldQuant Alpha API v2.0"}


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "WorldQuant Alpha Manager API",
        "version": "2.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }
