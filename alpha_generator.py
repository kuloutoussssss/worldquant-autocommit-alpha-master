# -*- coding: utf-8 -*-
"""
Alpha 表达式生成器 - 统一版

整合了4个历史脚本：
- alpha_generator_v4.py (21个模板)
- scripts/generate_valid_alpha.py (13种随机生成)
- generate_optimized.py (基于合格alpha优化)
- generate_ivltq_400.py (特定字段变体)

基于 WorldQuant Brain API 官方数据集验证的变量：
- pv1 (股市): close, open, high, low, vwap, volume, cap, returns
- fundamental6 (财务): assets, liabilities, revenue, netincome, cash, debt, equity, eps

不支持的变量: ret_*d, adv*, turnover, bid, ask, fnd6_*, anl4_*, implied_volatility_*, scl12_*, fn_*
"""

import argparse
import random
from pathlib import Path
from typing import List, Dict, Set

# ============================================================
# ✅ 有效变量定义 (WorldQuant Brain API 验证)
# ============================================================

# 价格/市场字段 (pv1)
PRICE_FIELDS = ["close", "open", "high", "low", "vwap", "volume", "cap", "returns"]

# 财务字段 (fundamental6)
FINANCIAL_FIELDS = ["assets", "liabilities", "revenue", "netincome", "cash", "debt", "equity", "eps"]

# 行业分组
GROUP_FIELDS = ["sector", "industry", "subindustry"]

# 时间窗口
SHORT_WINDOWS = [1, 2, 3, 5, 10]
MID_WINDOWS = [15, 20, 30, 40, 60]
LONG_WINDOWS = [90, 120, 180, 252]
ALL_WINDOWS = SHORT_WINDOWS + MID_WINDOWS + LONG_WINDOWS

# Decay 值
DECAY_VALUES = [5, 10, 15, 22, 30, 35, 40, 45, 60]


# ============================================================
# 模板 1-21: 确定性生成 (来自 alpha_generator_v4.py)
# ============================================================

def generate_01_ts_rank_stddev() -> List[Dict]:
    """group_rank(ts_rank(X/Y, N), G) - ts_std_dev"""
    alphas = []
    for fin in FINANCIAL_FIELDS:
        for price in PRICE_FIELDS[:6]:
            for rank_window in SHORT_WINDOWS + MID_WINDOWS[:3]:
                for group in GROUP_FIELDS:
                    for std_window in [5, 10, 15, 20]:
                        for decay in DECAY_VALUES[:5]:
                            expr = (
                                f"group_rank(ts_rank({fin}/{price}, {rank_window}), {group}) "
                                f"- ts_std_dev(ts_std_dev(close, {std_window}), 5)"
                            )
                            alphas.append({"expression": expr, "universe": "TOP3000",
                                          "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_02_volatility_spread() -> List[Dict]:
    """波动率价差: ts_std_dev(close, W1) - ts_std_dev(close, W2)"""
    alphas = []
    vol_windows = [5, 10, 15, 20, 30, 40, 60, 90, 120]
    for i, w1 in enumerate(vol_windows):
        for w2 in vol_windows[i+1:]:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    expr = f"group_neutralize(ts_std_dev(close, {w1}) - ts_std_dev(close, {w2}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    # 波动率比率
    for w1 in vol_windows:
        for w2 in vol_windows:
            if w1 >= w2:
                continue
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    expr = f"group_neutralize(ts_std_dev(close, {w1}) / (ts_std_dev(close, {w2}) + 0.0001), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_03_cum_return_diff() -> List[Dict]:
    """累积收益差: ts_sum(returns, W) - ts_sum(returns, W)"""
    alphas = []
    windows = [5, 10, 15, 20, 30, 40, 60]
    for ret in ["returns"]:
        for window in windows:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    expr = f"group_neutralize(ts_sum({ret},{window}) - ts_sum(returns,{window}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_04_delta_sum() -> List[Dict]:
    """ts_delta + ts_sum 组合"""
    alphas = []
    backfill_windows = [10, 15, 20, 30, 40]
    sum_windows = [60, 90, 120, 180]
    for fund in FINANCIAL_FIELDS:
        for backfill_win in backfill_windows:
            for sum_win in sum_windows:
                for group in GROUP_FIELDS:
                    expr = (
                        f"group_neutralize("
                        f"ts_sum(ts_delta({fund}, 1), {sum_win}) - "
                        f"ts_delay(ts_sum(ts_delta({fund}, 1), {sum_win}), {backfill_win}), "
                        f"{group})"
                    )
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": 22, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_05_zscore_diff() -> List[Dict]:
    """ts_zscore 差异"""
    alphas = []
    for fin1 in FINANCIAL_FIELDS:
        for fin2 in FINANCIAL_FIELDS:
            if fin1 == fin2:
                continue
            for scale_win in [60, 90, 120, 180, 252]:
                for decay in [15, 22, 30, 35, 40, 45]:
                    for group in GROUP_FIELDS:
                        expr = (
                            f"group_rank("
                            f"ts_zscore(ts_delta({fin1}, {decay}), 20) "
                            f"- ts_zscore(ts_delta({fin2}, {decay}), 20), "
                            f"{group})"
                        )
                        alphas.append({"expression": expr, "universe": "TOP3000",
                                      "decay": 22, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_06_conditional() -> List[Dict]:
    """条件表达式: ? :"""
    alphas = []
    max_count = 3000
    thresholds = [0.8, 0.9, 1.0, 1.1, 1.2]
    for vol_win in [10, 20, 30]:
        for threshold in thresholds:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = (
                        f"(ts_std_dev(returns, {vol_win}) > {threshold}) ? "
                        f"group_rank(-ts_delta(close, 5), {group}) : "
                        f"group_rank(ts_delta(close, 5), {group})"
                    )
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    for vol_threshold in [0.8, 1.0, 1.2, 1.5]:
        for decay in DECAY_VALUES:
            for group in GROUP_FIELDS:
                if len(alphas) >= max_count:
                    return alphas
                expr = (
                    f"(volume / ts_mean(volume, 20) > {vol_threshold}) ? "
                    f"group_rank(-returns, {group}) : "
                    f"group_rank(returns, {group})"
                )
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_07_momentum_reversal() -> List[Dict]:
    """动量/反转: ts_delta(close, rev) + ts_delta(close, mom)"""
    alphas = []
    max_count = 2000
    momentum_windows = [5, 10, 20, 30]
    reversal_windows = [1, 2, 3, 5]
    for mom_win in momentum_windows:
        for rev_win in reversal_windows:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"group_rank(ts_delta(close, {rev_win}) + ts_delta(close, {mom_win}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_08_volume_price() -> List[Dict]:
    """量价组合: ts_mean(returns * (volume/ts_mean(volume, W)), W)"""
    alphas = []
    max_count = 2000
    for price in PRICE_FIELDS[:5]:
        for vol_win in [5, 10, 20, 30]:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = (
                        f"group_rank("
                        f"ts_mean(returns * (volume / ts_mean(volume, {vol_win})), {vol_win}), "
                        f"{group})"
                    )
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_09_zscore_neutral() -> List[Dict]:
    """ts_zscore 中性化"""
    alphas = []
    max_count = 2000
    for fin in FINANCIAL_FIELDS[:10]:
        for zscore_win in [60, 90, 120, 180, 252]:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"group_neutralize(ts_zscore({fin}, {zscore_win}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_10_corr_pattern() -> List[Dict]:
    """相关性: ts_corr(price, volume, W)"""
    alphas = []
    max_count = 1500
    corr_windows = [5, 10, 20, 30]
    for price in PRICE_FIELDS[:4]:
        for corr_win in corr_windows:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"group_neutralize(ts_corr({price}, volume, {corr_win}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_11_mean_reversion() -> List[Dict]:
    """均值回归: price - ts_mean(price, W)"""
    alphas = []
    max_count = 2000
    for price in ["close", "vwap", "open"]:
        for lookback in [5, 10, 15, 20, 30]:
            for decay in DECAY_VALUES[:3]:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"group_neutralize({price} - ts_mean({price}, {lookback}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_12_volume_anomaly() -> List[Dict]:
    """成交量异常: ts_zscore(volume/ts_mean(volume, W), W)"""
    alphas = []
    max_count = 2000
    vol_windows = [10, 20, 30, 60]
    for win in vol_windows:
        for decay in DECAY_VALUES[:3]:
            for group in GROUP_FIELDS:
                if len(alphas) >= max_count:
                    return alphas
                expr = f"group_neutralize(ts_zscore(volume / ts_mean(volume, {win}), {win}), {group})"
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_13_relative_strength() -> List[Dict]:
    """相对强弱: ts_mean(returns, W)"""
    alphas = []
    max_count = 1500
    for win in [5, 10, 20, 30, 60]:
        for decay in [15, 22, 30]:
            for group in GROUP_FIELDS:
                if len(alphas) >= max_count:
                    return alphas
                expr = f"ts_mean(returns, {win})"
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_14_multi_signal() -> List[Dict]:
    """多信号: ts_zscore(X/Y, W)"""
    alphas = []
    max_count = 2000
    for i, fin1 in enumerate(FINANCIAL_FIELDS[:8]):
        for fin2 in FINANCIAL_FIELDS[i+1:i+5]:
            for win in [20, 40, 60]:
                for decay in [22, 30, 40]:
                    for group in GROUP_FIELDS:
                        if len(alphas) >= max_count:
                            return alphas
                        expr = f"group_neutralize(ts_zscore({fin1}/{fin2}, {win}), {group})"
                        alphas.append({"expression": expr, "universe": "TOP3000",
                                      "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_15_tick_diff() -> List[Dict]:
    """Tick差异: ts_delta(price, D)"""
    alphas = []
    max_count = 1500
    for delay in [1, 2, 3, 5]:
        for price in ["close", "vwap", "high", "low"]:
            for decay in [15, 22]:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"group_neutralize(ts_delta({price}, {delay}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_16_industry_rotation() -> List[Dict]:
    """行业轮动: group_rank(returns, G)"""
    alphas = []
    max_count = 1500
    for win in [20, 40, 60, 90]:
        for decay in DECAY_VALUES[:3]:
            for group in ["sector", "industry", "subindustry"]:
                if len(alphas) >= max_count:
                    return alphas
                expr = f"group_rank(returns, {group})"
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_17_cap_weighted() -> List[Dict]:
    """市值加权: cap * ts_mean(X, W)"""
    alphas = []
    max_count = 1500
    for field in ["returns", "close", "volume"]:
        for win in [5, 10, 20, 30, 60]:
            for decay in DECAY_VALUES:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"cap * ts_mean({field}, {win})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_18_momentum_acceleration() -> List[Dict]:
    """动量加速: ts_mean(returns, W1) - ts_mean(returns, W2)"""
    alphas = []
    max_count = 2000
    for win1 in [5, 10, 20]:
        for win2 in [20, 40, 60]:
            for decay in [22, 30, 40]:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"group_neutralize(ts_mean(returns, {win1}) - ts_mean(returns, {win2}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_19_volatility_regime() -> List[Dict]:
    """波动率regime: ts_std_dev(price, short) / ts_std_dev(price, long)"""
    alphas = []
    max_count = 1500
    for price in ["close", "vwap"]:
        for short_vol in [5, 10, 20]:
            for long_vol in [40, 60, 90]:
                for decay in [15, 22, 30]:
                    for group in GROUP_FIELDS:
                        if len(alphas) >= max_count:
                            return alphas
                        expr = (
                            f"group_neutralize("
                            f"ts_std_dev({price}, {short_vol}) / "
                            f"ts_std_dev({price}, {long_vol}), "
                            f"{group})"
                        )
                        alphas.append({"expression": expr, "universe": "TOP3000",
                                      "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_20_price_momentum() -> List[Dict]:
    """价格动量: ts_mean(price, W)"""
    alphas = []
    max_count = 2000
    for price in ["close", "vwap", "open"]:
        for win in [5, 10, 20, 30, 60, 90, 120]:
            for decay in [15, 22, 30, 40]:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"ts_mean({price}, {win})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": decay, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


# ============================================================
# 模板 22-34: 随机生成 (来自 scripts/generate_valid_alpha.py)
# ============================================================

class RandomGenerator:
    """随机 Alpha 生成器"""
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
    
    def generate_simple_delta(self, count: int = 200) -> List[Dict]:
        alphas, seen = [], set()
        for _ in range(count * 2):
            if len(alphas) >= count:
                break
            field = random.choice(PRICE_FIELDS)
            window = random.choice(ALL_WINDOWS)
            neutral = random.choice(GROUP_FIELDS)
            sign = random.choice([-1, 1])
            templates = [
                f"{'rank' if sign > 0 else '-rank'}(ts_delta({field}, {window}))",
                f"group_neutralize({'rank' if sign > 0 else '-rank'}(ts_delta({field}, {window})), {neutral})",
            ]
            expr = random.choice(templates)
            if expr not in seen:
                seen.add(expr)
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([5, 10, 15, 20, 30]), "neutralization": neutral.upper(), "truncation": 0.08})
        return alphas
    
    def generate_mean_reversion(self, count: int = 150) -> List[Dict]:
        alphas, seen = [], set()
        for _ in range(count * 2):
            if len(alphas) >= count:
                break
            field = random.choice(PRICE_FIELDS)
            window = random.choice(MID_WINDOWS + LONG_WINDOWS)
            neutral = random.choice(GROUP_FIELDS)
            templates = [
                f"-rank(ts_zscore({field}, {window}))",
                f"-group_neutralize(ts_zscore({field}, {window}), {neutral})",
                f"rank(-ts_zscore({field}, {window}) * ts_zscore(volume, {window}))",
            ]
            expr = random.choice(templates)
            if expr not in seen:
                seen.add(expr)
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([10, 20, 30]), "neutralization": neutral.upper(), "truncation": 0.08})
        return alphas
    
    def generate_momentum(self, count: int = 150) -> List[Dict]:
        alphas, seen = [], set()
        for _ in range(count * 2):
            if len(alphas) >= count:
                break
            field = random.choice(PRICE_FIELDS)
            window = random.choice(MID_WINDOWS + LONG_WINDOWS)
            neutral = random.choice(GROUP_FIELDS)
            templates = [
                f"rank(ts_delta({field}, {window}))",
                f"group_neutralize(rank(ts_delta({field}, {window})), {neutral})",
                f"rank(ts_delta({field}, {window}) - ts_delta({field}, {window // 2}))",
            ]
            expr = random.choice(templates)
            if expr not in seen:
                seen.add(expr)
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([10, 20, 30, 40]), "neutralization": neutral.upper(), "truncation": 0.08})
        return alphas
    
    def generate_volatility(self, count: int = 100) -> List[Dict]:
        alphas, seen = [], set()
        for _ in range(count * 2):
            if len(alphas) >= count:
                break
            field = random.choice(PRICE_FIELDS)
            window = random.choice(MID_WINDOWS)
            neutral = random.choice(GROUP_FIELDS)
            templates = [
                f"rank(ts_std_dev({field}, {window}))",
                f"-rank(ts_std_dev({field}, {window}))",
                f"rank(ts_mean({field}, {window}) / (ts_std_dev({field}, {window}) + 1e-10))",
            ]
            expr = random.choice(templates)
            if expr not in seen:
                seen.add(expr)
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([15, 20, 25, 30]), "neutralization": neutral.upper(), "truncation": 0.08})
        return alphas
    
    def generate_ts_rank(self, count: int = 100) -> List[Dict]:
        alphas, seen = [], set()
        for _ in range(count * 2):
            if len(alphas) >= count:
                break
            field = random.choice(PRICE_FIELDS)
            window = random.choice(MID_WINDOWS)
            neutral = random.choice(GROUP_FIELDS)
            templates = [
                f"rank(ts_rank({field}, {window}))",
                f"group_neutralize(rank(ts_rank({field}, {window})), {neutral})",
                f"rank(ts_rank({field}, {window}) - ts_rank(volume, {window}))",
            ]
            expr = random.choice(templates)
            if expr not in seen:
                seen.add(expr)
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([10, 20, 30]), "neutralization": neutral.upper(), "truncation": 0.08})
        return alphas
    
    def generate_cross_signal(self, count: int = 100) -> List[Dict]:
        alphas, seen = [], set()
        for _ in range(count * 2):
            if len(alphas) >= count:
                break
            field1 = random.choice(PRICE_FIELDS)
            field2 = random.choice(PRICE_FIELDS)
            window1 = random.choice(SHORT_WINDOWS + MID_WINDOWS[:2])
            window2 = random.choice(MID_WINDOWS)
            neutral = random.choice(GROUP_FIELDS)
            templates = [
                f"rank(ts_delta({field1}, {window1})) - rank(ts_delta({field2}, {window2}))",
                f"rank(ts_zscore({field1}, {window1})) * rank(-ts_zscore({field2}, {window2}))",
            ]
            expr = random.choice(templates)
            if expr not in seen:
                seen.add(expr)
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([10, 15, 20, 25]), "neutralization": neutral.upper(), "truncation": 0.08})
        return alphas
    
    def generate_corr_factor(self, count: int = 80) -> List[Dict]:
        alphas, seen = [], set()
        for _ in range(count * 2):
            if len(alphas) >= count:
                break
            field1 = random.choice(PRICE_FIELDS)
            field2 = random.choice(PRICE_FIELDS)
            window = random.choice(MID_WINDOWS)
            neutral = random.choice(GROUP_FIELDS)
            templates = [
                f"rank(ts_corr({field1}, {field2}, {window}))",
                f"rank(-ts_corr({field1}, {field2}, {window}))",
                f"rank(ts_corr({field1}, returns, {window}))",
            ]
            expr = random.choice(templates)
            if expr not in seen:
                seen.add(expr)
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([10, 20, 30]), "neutralization": neutral.upper(), "truncation": 0.08})
        return alphas
    
    def generate_all_random(self, total: int = 1500) -> List[Dict]:
        """生成所有随机类型"""
        alphas, seen = [], set()
        generators = [
            (self.generate_simple_delta, int(total * 0.20)),
            (self.generate_mean_reversion, int(total * 0.18)),
            (self.generate_momentum, int(total * 0.18)),
            (self.generate_volatility, int(total * 0.15)),
            (self.generate_ts_rank, int(total * 0.12)),
            (self.generate_cross_signal, int(total * 0.10)),
            (self.generate_corr_factor, int(total * 0.07)),
        ]
        for gen_func, count in generators:
            for alpha in gen_func(count):
                expr = alpha["expression"]
                if expr not in seen:
                    seen.add(expr)
                    alphas.append(alpha)
                    if len(alphas) >= total:
                        return alphas
        return alphas


# ============================================================
# 模板 35-38: 基于合格 Alpha 优化 (来自 generate_optimized.py)
# ============================================================

def generate_35_seed_variants() -> List[Dict]:
    """从简单种子生成变体"""
    alphas = []
    seeds = [
        "liabilities/assets",
        "assets/debt",
        "equity/assets",
        "revenue/assets",
    ]
    for seed in seeds:
        # 分组变体
        for group in GROUP_FIELDS:
            alphas.append({"expression": f"group_rank({seed}, {group})", "universe": "TOP3000",
                          "decay": 22, "neutralization": group.upper(), "truncation": 0.08})
        # 时间变化
        for w in [20, 60, 120]:
            for group in ["sector"]:
                alphas.append({"expression": f"group_rank(ts_delta({seed}, {w}), {group})", "universe": "TOP3000",
                              "decay": 22, "neutralization": group.upper(), "truncation": 0.08})
        # 中性化
        for group in GROUP_FIELDS:
            alphas.append({"expression": f"group_neutralize(regression_neut({seed}, log(cap)), {group})", "universe": "TOP3000",
                          "decay": 22, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_36_group_rank_variants() -> List[Dict]:
    """group_rank 变体"""
    alphas = []
    max_count = 2000
    for fin in FINANCIAL_FIELDS:
        for price in ["close", "volume", "cap"]:
            if fin == price:
                continue
            for rank_win in [10, 20, 40, 60]:
                for group in GROUP_FIELDS:
                    if len(alphas) >= max_count:
                        return alphas
                    expr = f"group_rank(ts_rank({fin}/{price}, {rank_win}), {group})"
                    alphas.append({"expression": expr, "universe": "TOP3000",
                                  "decay": random.choice([15, 22, 30]), "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_37_signed_power_variants() -> List[Dict]:
    """signed_power 变体"""
    alphas = []
    max_count = 1500
    powers = [0.5, 1, 2, 3]
    for fin in FINANCIAL_FIELDS:
        for price in ["close", "volume"]:
            for win in [20, 40, 60]:
                for power in powers:
                    for group in GROUP_FIELDS:
                        if len(alphas) >= max_count:
                            return alphas
                        expr = f"group_rank(signed_power({fin}/{price}, {power}), {group})"
                        alphas.append({"expression": expr, "universe": "TOP3000",
                                      "decay": 22, "neutralization": group.upper(), "truncation": 0.08})
    return alphas


def generate_38_scale_normalized() -> List[Dict]:
    """scale 归一化"""
    alphas = []
    max_count = 1500
    for fin in FINANCIAL_FIELDS:
        for win in MID_WINDOWS:
            for group in GROUP_FIELDS:
                if len(alphas) >= max_count:
                    return alphas
                expr = f"group_neutralize(scale(ts_delta({fin}, {win})), {group})"
                alphas.append({"expression": expr, "universe": "TOP3000",
                              "decay": random.choice([10, 15, 20]), "neutralization": group.upper(), "truncation": 0.08})
    return alphas


# ============================================================
# 主生成函数
# ============================================================

def get_all_templates():
    """获取所有模板"""
    return [
        # 确定性模板
        ("T01_ts_rank_stddev", generate_01_ts_rank_stddev),
        ("T02_volatility_spread", generate_02_volatility_spread),
        ("T03_cum_return_diff", generate_03_cum_return_diff),
        ("T04_delta_sum", generate_04_delta_sum),
        ("T05_zscore_diff", generate_05_zscore_diff),
        ("T06_conditional", generate_06_conditional),
        ("T07_momentum_reversal", generate_07_momentum_reversal),
        ("T08_volume_price", generate_08_volume_price),
        ("T09_zscore_neutral", generate_09_zscore_neutral),
        ("T10_corr_pattern", generate_10_corr_pattern),
        ("T11_mean_reversion", generate_11_mean_reversion),
        ("T12_volume_anomaly", generate_12_volume_anomaly),
        ("T13_relative_strength", generate_13_relative_strength),
        ("T14_multi_signal", generate_14_multi_signal),
        ("T15_tick_diff", generate_15_tick_diff),
        ("T16_industry_rotation", generate_16_industry_rotation),
        ("T17_cap_weighted", generate_17_cap_weighted),
        ("T18_momentum_acceleration", generate_18_momentum_acceleration),
        ("T19_volatility_regime", generate_19_volatility_regime),
        ("T20_price_momentum", generate_20_price_momentum),
        # 随机模板
        ("T22_random_simple_delta", lambda: RandomGenerator(42).generate_simple_delta(200)),
        ("T23_random_mean_reversion", lambda: RandomGenerator(43).generate_mean_reversion(150)),
        ("T24_random_momentum", lambda: RandomGenerator(44).generate_momentum(150)),
        ("T25_random_volatility", lambda: RandomGenerator(45).generate_volatility(100)),
        ("T26_random_ts_rank", lambda: RandomGenerator(46).generate_ts_rank(100)),
        ("T27_random_cross_signal", lambda: RandomGenerator(47).generate_cross_signal(100)),
        ("T28_random_corr_factor", lambda: RandomGenerator(48).generate_corr_factor(80)),
        # 优化模板
        ("T35_seed_variants", generate_35_seed_variants),
        ("T36_group_rank_variants", generate_36_group_rank_variants),
        ("T37_signed_power_variants", generate_37_signed_power_variants),
        ("T38_scale_normalized", generate_38_scale_normalized),
    ]


def generate_all(output_file: str = "data/alphas/to_test.txt",
                mode: str = "all",
                max_count: int = 0,
                append: bool = False) -> List[Dict]:
    """
    生成 Alpha 表达式
    
    Args:
        output_file: 输出文件路径
        mode: 生成模式 (all/quick/full/random)
        max_count: 最大数量限制 (0=无限制)
        append: 是否追加
    """
    templates = get_all_templates()
    
    # 根据模式选择模板
    if mode == "quick":
        selected = [t for t in templates if "random" in t[0] or "T13" in t[0] or "T20" in t[0]]
    elif mode == "full":
        selected = templates
    elif mode == "random":
        selected = [t for t in templates if "random" in t[0]]
    else:  # all
        selected = templates
    
    print(f"=" * 60)
    print(f"Alpha Generator - Unified")
    print(f"模式: {mode}, 模板数: {len(selected)}")
    print(f"=" * 60)
    
    all_alphas = []
    seen = set()
    
    for i, (name, func) in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {name}...", end=" ", flush=True)
        try:
            alphas = func()
            # 去重
            new_count = 0
            for alpha in alphas:
                expr = alpha["expression"]
                if expr not in seen:
                    seen.add(expr)
                    all_alphas.append(alpha)
                    new_count += 1
            print(f"+{new_count} (共{len(all_alphas)})")
        except Exception as e:
            print(f"错误: {e}")
    
    # 限制数量
    if max_count > 0 and len(all_alphas) > max_count:
        all_alphas = all_alphas[:max_count]
    
    print(f"\n总计: {len(all_alphas)} alphas")
    
    # 保存
    save_alphas(all_alphas, output_file, append=append)
    
    return all_alphas


def save_alphas(alphas: List[Dict], filepath: str, append: bool = False):
    """保存 Alpha 到文件"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    mode = 'a' if append else 'w'
    with open(filepath, mode, encoding='utf-8') as f:
        for alpha in alphas:
            line = (
                f"{alpha['expression']}|{alpha.get('universe', 'TOP3000')}|{alpha.get('decay', 0)}"
                f"|{alpha.get('neutralization', 'SUBINDUSTRY')}|{alpha.get('truncation', 0.08)}\n"
            )
            f.write(line)
    
    action = "追加" if append else "覆盖"
    print(f"[{action}] → {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Alpha 表达式生成器 - 统一版")
    parser.add_argument("--mode", "-m", default="all",
                       choices=["all", "quick", "full", "random"],
                       help="生成模式: all(全部), quick(快速), full(完整), random(随机)")
    parser.add_argument("--output", "-o", default="data/alphas/to_test.txt",
                       help="输出文件")
    parser.add_argument("--max", "-n", type=int, default=0,
                       help="最大数量 (0=无限制)")
    parser.add_argument("--append", "-a", action="store_true",
                       help="追加模式")
    args = parser.parse_args()
    
    generate_all(
        output_file=args.output,
        mode=args.mode,
        max_count=args.max,
        append=args.append
    )


if __name__ == "__main__":
    main()
