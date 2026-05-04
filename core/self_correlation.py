# -*- coding: utf-8 -*-
"""
Alpha 自相关计算模块

功能：
1. 从 WorldQuant Brain API 获取 Alpha 的 PnL 数据
2. 计算 Alpha 与历史 OS Alpha 的自相关性
3. 增量下载数据，避免重复请求
"""
import pickle
import time
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from .logger import logger

# 数据存储路径
DATA_PATH = Path("data/os_data")
API_BASE = "https://api.worldquantbrain.com"


class SelfCorrelationCalculator:
    """Alpha 自相关计算器"""

    def __init__(self, username: str = None, password: str = None, data_path: Path = None):
        """
        初始化计算器

        Args:
            username: WorldQuant Brain 用户名
            password: 密码
            data_path: 数据存储路径
        """
        self.username = username
        self.password = password
        self.data_path = data_path or DATA_PATH
        self.data_path.mkdir(parents=True, exist_ok=True)

        self.session = None
        self._os_alpha_ids = None
        self._os_alpha_pnls = None
        self._ppac_alpha_ids = None

    def sign_in(self, username: str = None, password: str = None, max_retries: int = 3) -> bool:
        """
        登录 WorldQuant Brain API（带重试）

        Args:
            username: 用户名
            password: 密码
            max_retries: 最大重试次数

        Returns:
            bool: 登录是否成功
        """
        username = username or self.username
        password = password or self.password

        if not username or not password:
            logger.warning("未提供用户名或密码，跳过登录")
            return False

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{API_BASE}/authentication/login",
                    json={"username": username, "password": password},
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    token = data.get("token")
                    if token:
                        self.session = requests.Session()
                        self.session.headers.update({"Authorization": f"Bearer {token}"})
                        logger.info("登录成功")
                        return True
                elif response.status_code == 429:
                    # 限流，等待后重试
                    wait_time = (attempt + 1) * 10
                    logger.warning(f"API 限流，等待 {wait_time} 秒后重试 ({attempt+1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"登录失败: {response.status_code} - {response.text}")
                    return False

            except Exception as e:
                logger.error(f"登录异常: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return False

        return False

    def _get_session(self) -> Optional[requests.Session]:
        """获取会话，确保已登录"""
        if self.session is None:
            self.sign_in()
        return self.session

    def get_alpha_pnl(self, alpha_id: str, region: str = "USA") -> Optional[pd.Series]:
        """
        获取单个 Alpha 的 PnL 数据

        Args:
            alpha_id: Alpha ID
            region: 区域（USA, CHN, etc.）

        Returns:
            pd.Series: 日收益率序列，索引为日期
        """
        sess = self._get_session()
        if not sess:
            return None

        try:
            response = sess.get(
                f"{API_BASE}/alpha/{alpha_id}/pnl",
                params={"region": region},
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                pnl_data = data.get("data", [])

                if pnl_data:
                    dates = [item[0] for item in pnl_data]
                    values = [item[1] for item in pnl_data]
                    return pd.Series(values, index=pd.to_datetime(dates))

            return None

        except Exception as e:
            logger.error(f"获取 PnL 失败 {alpha_id}: {e}")
            return None

    def get_os_alphas(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        获取 OS 阶段的 Alpha 列表

        Args:
            limit: 每次请求获取的数量
            offset: 偏移量

        Returns:
            List[Dict]: Alpha 信息列表
        """
        sess = self._get_session()
        if not sess:
            return []

        try:
            response = sess.get(
                f"{API_BASE}/alpha/list",
                params={
                    "type": "LIVE",
                    "status": "OOS",
                    "limit": limit,
                    "offset": offset
                },
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])

            return []

        except Exception as e:
            logger.error(f"获取 OS Alphas 失败: {e}")
            return []

    def _download_alpha_pnl(self, alpha_id: str) -> Tuple[str, Optional[pd.Series]]:
        """下载单个 Alpha 的 PnL"""
        pnl = self.get_alpha_pnl(alpha_id)
        return alpha_id, pnl

    def download_data(self, flag_increment: bool = True, max_workers: int = 5) -> int:
        """
        增量下载 OS Alpha 数据

        Args:
            flag_increment: 是否增量下载（只下载新增的 Alpha）
            max_workers: 并行下载线程数

        Returns:
            int: 下载的 Alpha 数量
        """
        # 加载已有的 Alpha ID 列表
        existing_ids_file = self.data_path / "os_alpha_ids.pickle"
        existing_ids = set()

        if flag_increment and existing_ids_file.exists():
            try:
                with open(existing_ids_file, 'rb') as f:
                    self._os_alpha_ids = pickle.load(f)
                # 展平所有区域的所有 Alpha ID
                for region_ids in self._os_alpha_ids.values():
                    for ids in region_ids.values():
                        existing_ids.update(ids)
                logger.info(f"增量模式: 已有 {len(existing_ids)} 个 Alpha")
            except Exception as e:
                logger.warning(f"加载已有数据失败: {e}")
                existing_ids = set()

        # 获取所有 OS Alphas
        logger.info("获取 OS Alpha 列表...")
        all_alphas = []
        offset = 0
        page_size = 100

        while True:
            batch = self.get_os_alphas(limit=page_size, offset=offset)
            if not batch:
                break
            all_alphas.extend(batch)
            offset += page_size
            logger.info(f"已获取 {len(all_alphas)} 个 Alpha...")
            time.sleep(0.5)  # 避免限流

        # 按区域分类
        os_alpha_ids = {}
        for alpha in all_alphas:
            alpha_id = alpha.get("alphaId", "")
            region = alpha.get("region", "USA")

            if not alpha_id:
                continue

            # 跳过已有的
            if flag_increment and alpha_id in existing_ids:
                continue

            if region not in os_alpha_ids:
                os_alpha_ids[region] = {}
            if alpha_id not in os_alpha_ids[region]:
                os_alpha_ids[region][alpha_id] = True

        # 需要下载的 Alpha
        all_new_ids = []
        for region_ids in os_alpha_ids.values():
            all_new_ids.extend(region_ids.keys())

        if not all_new_ids:
            logger.info("没有新的 Alpha 需要下载")
            return 0

        logger.info(f"需要下载 {len(all_new_ids)} 个新 Alpha")

        # 下载 PnL 数据
        pnls_dict = {}
        success_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._download_alpha_pnl, alpha_id): alpha_id
                for alpha_id in all_new_ids
            }

            for future in tqdm(as_completed(futures), total=len(futures), desc="下载 PnL"):
                alpha_id, pnl = future.result()
                if pnl is not None and len(pnl) > 0:
                    pnls_dict[alpha_id] = pnl
                    success_count += 1

                time.sleep(0.1)  # 避免限流

        # 合并到已有数据
        pnl_file = self.data_path / "os_alpha_pnls.pickle"
        existing_pnls = {}

        if pnl_file.exists():
            try:
                with open(pnl_file, 'rb') as f:
                    existing_pnls = pickle.load(f)
            except Exception as e:
                logger.warning(f"加载已有 PnL 失败: {e}")

        existing_pnls.update(pnls_dict)

        # 保存数据
        with open(existing_ids_file, 'wb') as f:
            pickle.dump(os_alpha_ids, f)

        with open(pnl_file, 'wb') as f:
            pickle.dump(existing_pnls, f)

        logger.info(f"下载完成: {success_count}/{len(all_new_ids)} 个 Alpha")

        # 更新内存缓存
        self._os_alpha_ids = os_alpha_ids
        self._os_alpha_pnls = existing_pnls

        return success_count

    def load_data(self, tag: str = None) -> Tuple[Dict, pd.DataFrame]:
        """
        加载本地存储的 Alpha 数据

        Args:
            tag: 过滤标签
                - None: 所有 Alpha
                - 'PPAC': 只获取 PPAC 池子的 Alpha
                - 'SelfCorr': 只获取除 PPAC 外的其他 Alpha

        Returns:
            Tuple[Dict, pd.DataFrame]: (os_alpha_ids, os_alpha_pnls)
        """
        ids_file = self.data_path / "os_alpha_ids.pickle"
        pnl_file = self.data_path / "os_alpha_pnls.pickle"

        if not ids_file.exists() or not pnl_file.exists():
            logger.warning("本地数据不存在，请先调用 download_data()")
            return {}, pd.DataFrame()

        try:
            with open(ids_file, 'rb') as f:
                os_alpha_ids = pickle.load(f)

            with open(pnl_file, 'rb') as f:
                os_alpha_pnls_raw = pickle.load(f)

            # 转换为 DataFrame（统一日期索引）
            if not os_alpha_pnls_raw:
                return os_alpha_ids, pd.DataFrame()

            # 找出所有日期
            all_dates = set()
            for pnl in os_alpha_pnls_raw.values():
                if pnl is not None:
                    all_dates.update(pnl.index)

            if not all_dates:
                return os_alpha_ids, pd.DataFrame()

            all_dates = sorted(all_dates)

            # 构建 DataFrame
            pnls_dict = {}
            for alpha_id, pnl in os_alpha_pnls_raw.items():
                if pnl is not None and len(pnl) > 0:
                    # 对齐到公共日期
                    aligned = pnl.reindex(all_dates).fillna(0)
                    pnls_dict[alpha_id] = aligned.values

            os_alpha_pnls = pd.DataFrame(pnls_dict, index=all_dates)

            # 按 tag 过滤
            if tag == 'PPAC':
                # 只返回 PPAC 池子的 Alpha
                ppac_file = self.data_path / "ppac_alpha_ids.pickle"
                if ppac_file.exists():
                    with open(ppac_file, 'rb') as f:
                        ppac_ids = pickle.load(f)
                    filtered_cols = [c for c in os_alpha_pnls.columns if c in ppac_ids]
                    os_alpha_pnls = os_alpha_pnls[filtered_cols]
                    # 同时过滤 os_alpha_ids
                    for region in os_alpha_ids:
                        os_alpha_ids[region] = {
                            k: v for k, v in os_alpha_ids[region].items()
                            if k in ppac_ids
                        }

            elif tag == 'SelfCorr':
                # 排除 PPAC 池子
                ppac_file = self.data_path / "ppac_alpha_ids.pickle"
                if ppac_file.exists():
                    with open(ppac_file, 'rb') as f:
                        ppac_ids = pickle.load(f)
                    filtered_cols = [c for c in os_alpha_pnls.columns if c not in ppac_ids]
                    os_alpha_pnls = os_alpha_pnls[filtered_cols]
                    # 同时过滤 os_alpha_ids
                    for region in os_alpha_ids:
                        os_alpha_ids[region] = {
                            k: v for k, v in os_alpha_ids[region].items()
                            if k not in ppac_ids
                        }

            # 更新缓存
            self._os_alpha_ids = os_alpha_ids
            self._os_alpha_pnls = os_alpha_pnls

            logger.info(f"加载数据: {len(os_alpha_pnls.columns)} 个 Alpha, {len(os_alpha_pnls)} 天数据")
            return os_alpha_ids, os_alpha_pnls

        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            return {}, pd.DataFrame()

    def calc_self_corr(
        self,
        alpha_pnl: pd.Series,
        os_alpha_pnls: pd.DataFrame,
        min_periods: int = 60
    ) -> float:
        """
        计算 Alpha 与历史 OS Alpha 的最大自相关性

        Args:
            alpha_pnl: 待检查 Alpha 的 PnL 序列
            os_alpha_pnls: 其他 Alpha 的 PnL 数据
            min_periods: 最少需要的数据点数量

        Returns:
            float: 最大自相关系数
        """
        if alpha_pnl is None or len(alpha_pnl) < min_periods:
            return 0.0

        if os_alpha_pnls is None or os_alpha_pnls.empty:
            return 0.0

        # 对齐日期
        common_dates = alpha_pnl.index.intersection(os_alpha_pnls.index)
        if len(common_dates) < min_periods:
            return 0.0

        alpha_aligned = alpha_pnl.reindex(common_dates).fillna(0).values

        # 计算与每个 Alpha 的相关性
        max_corr = 0.0
        column_count = len(os_alpha_pnls.columns)

        for col in os_alpha_pnls.columns:
            other = os_alpha_pnls[col].reindex(common_dates).fillna(0).values

            # 跳过常量
            if np.std(alpha_aligned) < 1e-10 or np.std(other) < 1e-10:
                continue

            try:
                corr = np.corrcoef(alpha_aligned, other)[0, 1]

                if not np.isnan(corr) and abs(corr) > abs(max_corr):
                    max_corr = corr

            except Exception:
                continue

        return float(max_corr)

    def get_alpha_pnl_by_id(
        self,
        alpha_id: str,
        region: str = "USA"
    ) -> Optional[pd.Series]:
        """
        获取 Alpha PnL（带缓存）

        Args:
            alpha_id: Alpha ID
            region: 区域

        Returns:
            pd.Series: PnL 序列
        """
        # 先检查本地缓存
        if self._os_alpha_pnls is not None and alpha_id in self._os_alpha_pnls.columns:
            return self._os_alpha_pnls[alpha_id]

        # 从 API 获取
        return self.get_alpha_pnl(alpha_id, region)


# 全局单例
_calculator_instance = None


def get_self_corr_calculator(
    username: str = None,
    password: str = None,
    data_path: Path = None
) -> SelfCorrelationCalculator:
    """
    获取自相关计算器单例

    Args:
        username: 用户名
        password: 密码
        data_path: 数据路径

    Returns:
        SelfCorrelationCalculator 实例
    """
    global _calculator_instance

    if _calculator_instance is None:
        _calculator_instance = SelfCorrelationCalculator(
            username=username,
            password=password,
            data_path=data_path
        )

    return _calculator_instance


def calc_alpha_self_corr(
    alpha_pnl: pd.Series,
    os_alpha_pnls: pd.DataFrame = None,
    data_path: Path = None
) -> float:
    """
    便捷函数：计算 Alpha 自相关性

    Args:
        alpha_pnl: Alpha 的 PnL 序列
        os_alpha_pnls: 其他 Alpha 的 PnL 数据（可选）
        data_path: 数据路径（可选）

    Returns:
        float: 最大自相关系数
    """
    calculator = get_self_corr_calculator(data_path=data_path)

    if os_alpha_pnls is None:
        _, os_alpha_pnls = calculator.load_data(tag='SelfCorr')

    return calculator.calc_self_corr(alpha_pnl, os_alpha_pnls)
