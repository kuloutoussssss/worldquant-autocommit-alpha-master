# -*- coding: utf-8 -*-
"""
启动脚本
"""
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from web.config import get_settings


def main():
    """启动 FastAPI 服务器"""
    settings = get_settings()
    
    print(f"""
╔════════════════════════════════════════════════════════════╗
║     WorldQuant Alpha Manager API v2.0 (FastAPI)            ║
╠════════════════════════════════════════════════════════════╣
║  API Server: http://{settings.API_HOST}:{settings.API_PORT}                      ║
║  Docs:       http://{settings.API_HOST}:{settings.API_PORT}/docs                  ║
║  ReDoc:      http://{settings.API_HOST}:{settings.API_PORT}/redoc                ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "web.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_DEBUG,
        log_level="info"
    )


if __name__ == "__main__":
    main()
