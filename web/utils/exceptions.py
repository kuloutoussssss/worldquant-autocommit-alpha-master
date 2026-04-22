# -*- coding: utf-8 -*-
"""
自定义异常和统一错误处理
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import traceback


class APIException(Exception):
    """API 基础异常"""
    def __init__(self, message: str, code: str = "API_ERROR", status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class TaskNotFoundError(APIException):
    """任务未找到"""
    def __init__(self, task_id: str):
        super().__init__(
            message=f"Task '{task_id}' not found",
            code="TASK_NOT_FOUND",
            status_code=404
        )


class AlphaNotFoundError(APIException):
    """Alpha 未找到"""
    def __init__(self, alpha_id: str):
        super().__init__(
            message=f"Alpha '{alpha_id}' not found",
            code="ALPHA_NOT_FOUND",
            status_code=404
        )


class AuthenticationError(APIException):
    """认证失败"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            code="AUTH_ERROR",
            status_code=401
        )


class RateLimitError(APIException):
    """请求过于频繁"""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"Rate limit exceeded. Retry after {retry_after} seconds",
            code="RATE_LIMIT",
            status_code=429
        )


def register_exception_handlers(app: FastAPI):
    """注册全局异常处理器"""
    
    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.message,
                "code": exc.code
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "Validation error",
                "code": "VALIDATION_ERROR",
                "details": errors
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        # 生产环境应记录日志而非返回详情
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "detail": str(exc) if __debug__ else None
            }
        )
