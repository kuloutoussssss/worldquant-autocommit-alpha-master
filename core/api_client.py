# -*- coding: utf-8 -*-
"""
WorldQuant Brain API Client

基于 ace_lib.py 和 brain_adapter.py 最佳实践重构:
- Basic Auth 认证
- Session 持久化管理
- 同步版本 (BrainAPIClient) 和异步版本 (AsyncBrainAPIClient)
"""

import os
import json
import time
import asyncio
import httpx
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from requests.auth import HTTPBasicAuth

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

from .logger import logger

# API 配置
BASE_URL = "https://api.worldquantbrain.com"
DEFAULT_TIMEOUT = 60.0
SESSION_BUFFER_SECONDS = 300  # token 过期前 5 分钟刷新


class BrainAPIClient:
    """WorldQuant Brain API 客户端（同步版本）- 使用 Basic Auth"""
    
    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        """
        初始化 API 客户端
        
        凭证优先级:
        1. 构造函数参数
        2. 环境变量 BRAIN_EMAIL / BRAIN_PASSWORD
        3. 环境变量 WQ_USERNAME / WQ_PASSWORD (兼容旧格式)
        """
        self.email = email or os.getenv("BRAIN_EMAIL", "") or os.getenv("WQ_USERNAME", "")
        self.password = password or os.getenv("BRAIN_PASSWORD", "") or os.getenv("WQ_PASSWORD", "")
        self.session = requests.Session()
        self.session_token = None
        
        # 配置 session headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://platform.worldquantbrain.com",
            "Referer": "https://platform.worldquantbrain.com/",
            "Accept": "application/json;version=2.0",
            "Content-Type": "application/json"
        })
        
        if not self.email or not self.password:
            logger.warning("BRAIN_EMAIL/BRAIN_PASSWORD or WQ_USERNAME/WQ_PASSWORD not configured")
    
    def _authenticate(self) -> bool:
        """使用 Basic Auth 进行认证"""
        try:
            response = self.session.post(
                f"{BASE_URL}/authentication",
                auth=HTTPBasicAuth(self.email, self.password),
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code == 201:
                logger.info("Brain authentication successful")
                data = response.json()
                self.session_token = data.get("token", {}).get("expiry", 0)
                return True
            else:
                logger.error(f"Auth failed: {response.status_code} - {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Auth error: {e}")
            return False
    
    def _check_session(self) -> bool:
        """检查 session 是否有效"""
        try:
            response = self.session.get(
                f"{BASE_URL}/authentication",
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                expiry = data.get("token", {}).get("expiry", 0)
                return expiry > SESSION_BUFFER_SECONDS
            return False
        except Exception:
            return False
    
    def ensure_session(self) -> bool:
        """确保 session 有效"""
        if self._check_session():
            return True
        return self._authenticate()
    
    def test_alpha(self, expression: str, universe: str = "TOP3000",
                   decay: int = 30, neutralization: str = "SECTOR",
                   truncation: float = 0.08, delay: int = 1,
                   region: str = "USA",
                   test_period: str = "P2Y0M") -> Optional[Dict]:
        """回测单个 Alpha"""
        if not self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        url = f"{BASE_URL}/simulations"
        payload = {
            "type": "REGULAR",
            "settings": {
                "instrumentType": "EQUITY",
                "region": region,
                "universe": universe,
                "delay": delay,
                "decay": decay,
                "neutralization": neutralization,
                "truncation": truncation,
                "testPeriod": test_period,
                "nanHandling": "OFF",
                "unitHandling": "VERIFY",
                "pasteurization": "ON",
                "language": "FASTEXPR",
                "visualization": False
            },
            "regular": expression
        }
        
        # 429限流重试配置（指数退避）
        MAX_RETRIES = 5
        INITIAL_DELAY = 2  # 初始等待2秒
        BACKOFF_FACTOR = 2  # 指数退避因子
        
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
                
                # 429限流 - 指数退避重试
                if response.status_code == 429:
                    wait_time = INITIAL_DELAY * (BACKOFF_FACTOR ** attempt)
                    logger.warning(f"[{attempt+1}/{MAX_RETRIES}] 429 Rate Limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                if response.status_code not in [200, 201, 202]:
                    return {"status": "ERROR", "error": f"HTTP {response.status_code}: {response.text}"}
                
                # 获取 simulation ID
                location = response.headers.get("Location", "")
                if not location:
                    sim_id = response.json().get("id", "")
                    location = f"/simulations/{sim_id}"
                
                return {"status": "OK", "location": location}
                
            except requests.exceptions.Timeout:
                return {"status": "ERROR", "error": "Request timeout"}
            except requests.exceptions.RequestException as e:
                return {"status": "ERROR", "error": str(e)}
        
        # 超过最大重试次数
        return {"status": "ERROR", "error": "Failed after max retries (429 Rate Limit)"}
    
    def get_simulation_result(self, location: str, max_retries: int = 60) -> Optional[Dict]:
        """获取 simulation 结果
        
        Args:
            location: simulation URL
            max_retries: 最大重试次数，默认60次（约10分钟）
        """
        if not self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        # 构建完整 URL
        if location.startswith("http"):
            url = location
        else:
            url = f"{BASE_URL}{location}"
        
        retry_count = 0
        # 429限流重试配置
        MAX_429_RETRIES = 3
        INITIAL_DELAY = 2
        
        try:
            while retry_count < max_retries:
                response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
                
                # 429限流 - 指数退避重试
                if response.status_code == 429:
                    wait_time = INITIAL_DELAY * (2 ** min(retry_count, MAX_429_RETRIES))
                    logger.warning(f"[429] Rate Limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    retry_count += 1
                    continue
                
                if response.status_code != 200:
                    return {"status": "ERROR", "error": f"HTTP {response.status_code}"}
                
                # 检查是否完成
                retry_after = response.headers.get("Retry-After", "0")
                if not retry_after or retry_after == "0":
                    data = response.json()
                    if data.get("status") == "ERROR":
                        return {"status": "ERROR", "error": data.get("message", "Simulation failed")}
                    return {"status": "OK", "data": data}
                
                wait_time = min(float(retry_after), 10)  # 最大等待10秒
                time.sleep(wait_time)
                retry_count += 1
                
            # 超过最大重试次数
            return {"status": "ERROR", "error": "Simulation timeout: exceeded maximum retries"}
            
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    def submit_alpha(self, alpha_id: str) -> Optional[Dict]:
        """提交 Alpha"""
        if not self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        url = f"{BASE_URL}/alphas/{alpha_id}/submit"
        try:
            response = self.session.post(url, timeout=DEFAULT_TIMEOUT)
            if response.status_code in [200, 201, 202]:
                return {"status": "OK", "data": response.json()}
            return {"status": "ERROR", "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    def get_alpha(self, alpha_id: str) -> Optional[Dict]:
        """获取 Alpha 信息"""
        if not self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        url = f"{BASE_URL}/alphas/{alpha_id}"
        try:
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                return {"status": "OK", "data": response.json()}
            return {"status": "ERROR", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    def get_all_user_alphas(self, limit: int = 100, offset: int = 0,
                           min_sharpe: float = 0, min_fitness: float = 0,
                           max_turnover: float = 1e9) -> List[Dict]:
        """获取所有用户 Alpha"""
        if not self.ensure_session():
            logger.error("Authentication failed")
            return []
        
        all_alphas = []
        url = f"{BASE_URL}/users/self/alphas"
        max_pages = 100  # 最多获取 100 * 100 = 10000 条
        
        try:
            while offset < max_pages * limit:
                params = {
                    "limit": limit,
                    "offset": offset,
                }
                
                response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
                if response.status_code != 200:
                    logger.error(f"Failed to get alphas: {response.status_code}")
                    break
                
                data = response.json()
                results = data.get("results", [])
                
                if not results:
                    break
                
                # 过滤
                for a in results:
                    is_data = a.get("is") or {}
                    sharpe = is_data.get("sharpe", 0) or 0
                    fitness = is_data.get("fitness", 0) or 0
                    turnover = is_data.get("turnover", 1) or 1
                    
                    if sharpe >= min_sharpe and fitness >= min_fitness and turnover <= max_turnover:
                        all_alphas.append(a)
                
                if len(results) < limit:
                    break
                
                offset += limit
            
            logger.info(f"Fetched {len(all_alphas)} alphas (offset went up to {offset})")
                
        except Exception as e:
            logger.error(f"Failed to get alphas: {e}")
        
        return all_alphas
    
    def get_updated_alphas(self, since: datetime, **kwargs) -> List[Dict]:
        """获取更新的 Alpha"""
        all_alphas = self.get_all_user_alphas(**kwargs)
        since_str = since.isoformat() if since else ""
        
        return [
            a for a in all_alphas
            if a.get('dateModified') and a['dateModified'] > since_str
        ]
    
    def get_datasets(self, region: str = "USA") -> List[Dict]:
        """获取可用数据集"""
        if not self.ensure_session():
            return []
        
        url = f"{BASE_URL}/data-sets"
        try:
            response = self.session.get(
                url,
                params={"region": region, "instrumentType": "EQUITY"},
                timeout=DEFAULT_TIMEOUT
            )
            if response.status_code == 200:
                return response.json().get("results", [])
        except Exception as e:
            logger.error(f"Failed to get datasets: {e}")
        return []
    
    def get_datafields(self, dataset_id: str, region: str = "USA") -> List[Dict]:
        """获取数据集字段"""
        if not self.ensure_session():
            return []
        
        all_fields = []
        offset = 0
        limit = 50
        
        url = f"{BASE_URL}/data-fields"
        try:
            while True:
                response = self.session.get(
                    url,
                    params={
                        "dataset.id": dataset_id,
                        "region": region,
                        "instrumentType": "EQUITY",
                        "limit": limit,
                        "offset": offset
                    },
                    timeout=DEFAULT_TIMEOUT
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                results = data.get("results", [])
                
                if not results:
                    break
                
                all_fields.extend(results)
                
                if len(results) < limit:
                    break
                
                offset += limit
                
        except Exception as e:
            logger.error(f"Failed to get datafields: {e}")
        
        return all_fields


class AsyncBrainAPIClient:
    """WorldQuant Brain API 客户端（异步版本）- 使用 Basic Auth"""
    
    _client: Optional[httpx.AsyncClient] = None
    
    def __init__(self, email: Optional[str] = None, password: Optional[str] = None,
                 max_concurrent: int = 10):
        """
        初始化异步 API 客户端
        
        凭证优先级:
        1. 构造函数参数
        2. 环境变量 BRAIN_EMAIL / BRAIN_PASSWORD
        3. 环境变量 WQ_USERNAME / WQ_PASSWORD (兼容旧格式)
        """
        self.email = email or os.getenv("BRAIN_EMAIL", "") or os.getenv("WQ_USERNAME", "")
        self.password = password or os.getenv("BRAIN_PASSWORD", "") or os.getenv("WQ_PASSWORD", "")
        self.max_concurrent = max_concurrent
        self.session_token = None
        self._client: Optional[httpx.AsyncClient] = None
        self.semaphore: Optional[asyncio.Semaphore] = None
    
    async def __aenter__(self):
        await self.open()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def open(self):
        """初始化会话"""
        if not self.email or not self.password:
            logger.warning("BRAIN_EMAIL and BRAIN_PASSWORD not configured")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://platform.worldquantbrain.com",
            "Referer": "https://platform.worldquantbrain.com/",
            "Accept": "application/json;version=2.0",
            "Content-Type": "application/json"
        }
        
        self._client = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers=headers,
            follow_redirects=True
        )
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self._auth_lock = asyncio.Lock()  # 认证锁，防止并发认证冲突
    
    async def close(self):
        """关闭会话"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _authenticate(self) -> bool:
        """使用 Basic Auth 进行认证"""
        try:
            response = await self._client.post(
                f"{BASE_URL}/authentication",
                auth=(self.email, self.password)
            )
            
            if response.status_code == 201:
                logger.info("Brain authentication successful")
                data = response.json()
                self.session_token = data.get("token", {}).get("expiry", 0)
                return True
            else:
                logger.error(f"Auth failed: {response.status_code} - {response.text}")
                return False
        except httpx.RequestError as e:
            logger.error(f"Auth error: {e}")
            return False
    
    async def _check_session(self) -> bool:
        """检查 session 是否有效"""
        try:
            response = await self._client.get(f"{BASE_URL}/authentication")
            
            if response.status_code == 200:
                data = response.json()
                expiry = data.get("token", {}).get("expiry", 0)
                return expiry > SESSION_BUFFER_SECONDS
            return False
        except Exception:
            return False
    
    async def ensure_session(self) -> bool:
        """确保 session 有效 - 使用锁防止并发认证冲突"""
        # 先检查 session 是否有效（不锁）
        if await self._check_session():
            return True
        
        # Session 无效，需要认证，使用锁防止并发认证
        async with self._auth_lock:
            # 双重检查，获取锁后再次验证 session
            if await self._check_session():
                return True
            return await self._authenticate()
    
    async def test_alpha(self, expression: str, universe: str = "TOP3000",
                        decay: int = 30, neutralization: str = "SECTOR",
                        truncation: float = 0.08, delay: int = 1,
                        region: str = "USA",
                        test_period: str = "P2Y0M",
                        max_retries: int = 5) -> Optional[Dict]:
        """异步回测 Alpha - 带429限流重试"""
        if not self._client:
            await self.open()
        
        if not await self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        url = f"{BASE_URL}/simulations"
        payload = {
            "type": "REGULAR",
            "settings": {
                "instrumentType": "EQUITY",
                "region": region,
                "universe": universe,
                "delay": delay,
                "decay": decay,
                "neutralization": neutralization,
                "truncation": truncation,
                "testPeriod": test_period,
                "nanHandling": "OFF",
                "unitHandling": "VERIFY",
                "pasteurization": "ON",
                "language": "FASTEXPR",
                "visualization": False
            },
            "regular": expression
        }
        
        async with self.semaphore:
            for attempt in range(max_retries):
                try:
                    response = await self._client.post(url, json=payload)
                    
                    # 429 Too Many Requests - 限流，等待后重试
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", "60"))
                        wait_time = min(retry_after, 120)
                        logger.warning(f"429 Rate Limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    if response.status_code not in [200, 201, 202]:
                        return {"status": "ERROR", "error": f"HTTP {response.status_code}: {response.text}"}
                    
                    location = response.headers.get("Location", "")
                    if not location:
                        sim_id = response.json().get("id", "")
                        location = f"/simulations/{sim_id}"
                    
                    return {"status": "OK", "location": location}
                    
                except httpx.TimeoutException:
                    return {"status": "ERROR", "error": "Request timeout"}
                except httpx.RequestError as e:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"Network error: {e}, retrying in {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    return {"status": "ERROR", "error": str(e)}
            
            return {"status": "ERROR", "error": f"Failed after {max_retries} attempts (429 Rate Limit)"}
    
    async def get_simulation_result(self, location: str) -> Optional[Dict]:
        """获取 simulation 结果"""
        if not self._client:
            await self.open()
        
        if not await self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        if location.startswith("http"):
            url = location
        else:
            url = f"{BASE_URL}{location}"
        
        try:
            while True:
                response = await self._client.get(url)
                
                if response.status_code != 200:
                    return {"status": "ERROR", "error": f"HTTP {response.status_code}"}
                
                retry_after = response.headers.get("Retry-After", "0")
                if not retry_after or retry_after == "0":
                    data = response.json()
                    if data.get("status") == "ERROR":
                        return {"status": "ERROR", "error": data.get("message", "Simulation failed")}
                    return {"status": "OK", "data": data}
                
                await asyncio.sleep(float(retry_after))
                
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    async def submit_alpha(self, alpha_id: str) -> Optional[Dict]:
        """异步提交 Alpha"""
        if not self._client:
            await self.open()
        
        if not await self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        url = f"{BASE_URL}/alphas/{alpha_id}/submit"
        
        async with self.semaphore:
            try:
                response = await self._client.post(url)
                if response.status_code in [200, 201, 202]:
                    return {"status": "OK", "data": response.json()}
                return {"status": "ERROR", "error": f"HTTP {response.status_code}: {response.text}"}
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}
    
    async def get_alpha(self, alpha_id: str) -> Optional[Dict]:
        """异步获取 Alpha 信息"""
        if not self._client:
            await self.open()
        
        if not await self.ensure_session():
            return {"status": "ERROR", "error": "Authentication failed"}
        
        url = f"{BASE_URL}/alphas/{alpha_id}"
        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                return {"status": "OK", "data": response.json()}
            return {"status": "ERROR", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    async def get_all_user_alphas_async(self, limit: int = 100, offset: int = 0,
                                        min_sharpe: float = 0, min_fitness: float = 0,
                                        max_turnover: float = 1e9) -> List[Dict]:
        """异步获取所有用户 Alpha"""
        if not self._client:
            await self.open()
        
        if not await self.ensure_session():
            logger.error("Authentication failed")
            return []
        
        all_alphas = []
        url = f"{BASE_URL}/users/self/alphas"
        max_pages = 100  # 最多获取 100 * 100 = 10000 条
        
        try:
            while offset < max_pages * limit:
                params = {
                    "limit": limit,
                    "offset": offset,
                }
                
                response = await self._client.get(url, params=params)
                if response.status_code != 200:
                    logger.error(f"Failed to get alphas: {response.status_code}")
                    break
                
                data = response.json()
                results = data.get("results", [])
                
                if not results:
                    break
                
                for a in results:
                    is_stats = a.get("is") or {}
                    sharpe = is_stats.get("sharpe", 0) or 0
                    fitness = is_stats.get("fitness", 0) or 0
                    turnover = is_stats.get("turnover", 1) or 1
                    
                    if sharpe >= min_sharpe and fitness >= min_fitness and turnover <= max_turnover:
                        all_alphas.append(a)
                
                if len(results) < limit:
                    break
                
                offset += limit
            
            logger.info(f"Fetched {len(all_alphas)} alphas (offset went up to {offset})")
                
        except httpx.RequestError as e:
            logger.error(f"Failed to get alphas: {e}")
        
        return all_alphas
    
    async def get_updated_alphas_async(self, since: datetime, **kwargs) -> List[Dict]:
        """异步获取更新的 Alpha"""
        all_alphas = await self.get_all_user_alphas_async(**kwargs)
        since_str = since.isoformat() if since else ""
        
        return [
            a for a in all_alphas
            if a.get('dateModified') and a['dateModified'] > since_str
        ]


def run_async(coro):
    """运行异步函数"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
