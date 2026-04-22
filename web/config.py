# -*- coding: utf-8 -*-
"""
配置管理
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.absolute()


class Settings(BaseSettings):
    """应用配置"""
    # API 配置
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 5000
    API_DEBUG: bool = True

    # WorldQuant API 配置
    BRAIN_EMAIL: str = ""
    BRAIN_PASSWORD: str = ""
    WQ_USERNAME: str = ""
    WQ_PASSWORD: str = ""

    # 数据目录配置
    DATA_DIR: Path = PROJECT_ROOT / "data"

    # 数据库配置
    DB_PATH: Path = PROJECT_ROOT / "data" / "alphas.db"
    TASKS_FILE: Path = PROJECT_ROOT / "data" / "tasks.json"
    
    # 速率限制
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60
    
    # 缓存配置
    CACHE_ENABLED: bool = True
    CACHE_TTL: int = 300
    
    class Config:
        env_file = PROJECT_ROOT / ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
