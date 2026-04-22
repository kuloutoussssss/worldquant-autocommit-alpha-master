# -*- coding: utf-8 -*-
"""
Streamlit API 客户端工具
统一封装 API 请求，减少代码重复
"""
import requests
import streamlit as st
from typing import Any, Dict, Optional
from functools import lru_cache

# API 基础地址
API_BASE = "http://localhost:5000/api"


class APIClient:
    """API 客户端类"""
    
    def __init__(self, base_url: str = API_BASE, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self._session = None
    
    @property
    def session(self) -> requests.Session:
        """获取或创建会话（复用连接）"""
        if self._session is None:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=10,
                pool_maxsize=20,
                max_retries=3
            )
            self._session.mount('http://', adapter)
            self._session.mount('https://', adapter)
        return self._session
    
    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """GET 请求"""
        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return {"success": False, "error": "请求超时，请检查 API 服务器是否响应"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "无法连接到 API 服务器，请确保服务器已启动"}
        except requests.exceptions.HTTPError as e:
            return {"success": False, "error": f"HTTP 错误: {e.response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def post(self, endpoint: str, data: Optional[Dict] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """POST 请求"""
        url = f"{self.base_url}/{endpoint}"
        try:
            resp = self.session.post(url, json=data or {}, timeout=timeout or self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return {"success": False, "error": "请求超时，请检查 API 服务器是否响应"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "无法连接到 API 服务器，请确保服务器已启动"}
        except requests.exceptions.HTTPError as e:
            return {"success": False, "error": f"HTTP 错误: {e.response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# 全局客户端实例（连接复用）
@st.cache_resource
def get_api_client() -> APIClient:
    """获取 API 客户端单例"""
    return APIClient()


def api_get(endpoint: str, params: Optional[Dict] = None, use_cache: bool = False) -> Dict[str, Any]:
    """快捷 GET 请求"""
    client = get_api_client()
    
    # 缓存键
    cache_key = f"api_get_{endpoint}_{str(params)}"
    
    if use_cache and cache_key in st.session_state:
        return st.session_state[cache_key]
    
    result = client.get(endpoint, params)
    
    if use_cache:
        st.session_state[cache_key] = result
    
    return result


def api_post(endpoint: str, data: Optional[Dict] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
    """快捷 POST 请求"""
    client = get_api_client()
    return client.post(endpoint, data, timeout)


def check_api_connection() -> tuple[bool, str]:
    """检查 API 连接状态
    
    Returns:
        (是否连接成功, 错误信息)
    """
    result = api_get("health", use_cache=False)
    if result.get("success"):
        return True, ""
    return False, result.get("error", "未知错误")


@lru_cache(maxsize=1)
def cached_health_check() -> tuple[bool, str]:
    """缓存的健康检查（避免频繁请求）"""
    return check_api_connection()
