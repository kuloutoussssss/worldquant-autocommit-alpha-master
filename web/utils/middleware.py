# -*- coding: utf-8 -*-
"""
中间件
"""
import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """简单的内存速率限制中间件"""
    
    def __init__(self, app: ASGIApp, max_requests: int = 100, window: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window  # 时间窗口（秒）
        self.requests: Dict[str, list] = defaultdict(list)
    
    def _clean_old_requests(self, client_id: str):
        """清理过期的请求记录"""
        now = time.time()
        cutoff = now - self.window
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if req_time > cutoff
        ]
    
    def _is_rate_limited(self, client_id: str) -> Tuple[bool, int]:
        """检查是否被限流
        
        Returns:
            (is_limited, retry_after)
        """
        self._clean_old_requests(client_id)
        
        if len(self.requests[client_id]) >= self.max_requests:
            # 计算距离下次可请求的秒数
            oldest = min(self.requests[client_id])
            retry_after = int(self.window - (time.time() - oldest)) + 1
            return True, retry_after
        
        return False, 0
    
    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查的限流
        if request.url.path in ["/api/health", "/", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        client_id = request.client.host if request.client else "unknown"
        
        is_limited, retry_after = self._is_rate_limited(client_id)
        
        if is_limited:
            return Response(
                content=f'{{"success":false,"error":"Rate limit exceeded","retry_after":{retry_after}}}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)}
            )
        
        # 记录请求
        self.requests[client_id].append(time.time())
        
        response = await call_next(request)
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        print(f"{request.method} {request.url.path} - {response.status_code} ({process_time:.3f}s)")
        
        return response
