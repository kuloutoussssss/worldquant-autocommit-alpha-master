# -*- coding: utf-8 -*-
"""
WorldQuant Brain API 有效变量配置

基于 WorldQuant-Brain-Alpha-main 项目数据集配置整理

数据集文档：https://www.worldquant.com/data/datasets
"""

# ============================================================
# pv1 - 股市成交量数据 (最常用的数据集)
# ============================================================
PV1_FIELDS = [
    "volume",     # 成交量
    "close",      # 收盘价
    "open",       # 开盘价
    "high",       # 最高价
    "low",        # 最低价
    "vwap",       # 成交量加权平均价
    "returns",    # 日收益率
    # "turnover",  # 换手率 - 部分数据集可能不支持
    # "volatility" # 波动率 - 部分数据集可能不支持
]

# ============================================================
# fundamental6 - 基础财务数据
# ============================================================
FUNDAMENTAL6_FIELDS = [
    "assets",         # 总资产
    "liabilities",   # 总负债
    "revenue",        # 营业收入
    "netincome",      # 净利润
    "cash",           # 现金
    "debt",           # 债务
    "equity",         # 股东权益
    "eps",            # 每股收益
    "pe_ratio",       # 市盈率
    "pb_ratio",       # 市净率
    "market_cap",     # 市值 (与 cap 相同)
    "dividend_yield"  # 股息率
]

# ============================================================
# analyst4 - 分析师预测数据
# ============================================================
ANALYST4_FIELDS = [
    "anl4_tbvps_low",      # 分析师预测每股账面价值低值
    "anl4_tbvps_high",     # 分析师预测每股账面价值高值
    "anl4_tbvps_mean",     # 分析师预测每股账面价值均值
    "anl4_tbvps_median",   # 分析师预测每股账面价值中值
]

# ============================================================
# 所有验证有效的变量 (推荐使用)
# ============================================================
VALID_VARIABLES = {
    "价格": ["close", "open", "high", "low", "vwap"],
    "成交量": ["volume"],
    "市值": ["cap", "market_cap"],
    "收益": ["returns"],
    "财务": ["assets", "liabilities", "revenue", "netincome", "cash", "debt", "equity", "eps"],
}

# ============================================================
# 无效变量 (会报 unknown variable 错误)
# ============================================================
INVALID_VARIABLES = [
    "ret_20d", "ret_60d", "ret_120d", "ret_252d",  # 用 ts_delta(close, N)/close 替代
    "adv5", "adv10", "adv20",                      # 用 ts_mean(volume, N) 替代
    "bid", "ask",                                  # 部分数据集不支持
    "vwp",                                        # 用 vwap 替代
    "turnover",                                   # 用 volume/cap 替代
    "rel_ret_all", "rel_ret_industry", "rel_ret_sector",  # 未验证
    "fcf", "ebit", "net_income", "gross_profit",  # 未在 fundamental6 中验证
    "est_eps", "ebitda", "operating_income",      # 未验证
]

# ============================================================
# 常用函数组合 (替代无效变量的方法)
# ============================================================
FUNCTION_SUBSTITUTIONS = {
    # 替代 ret_120d (120天收益率)
    "ret_120d": "ts_delta(close, 120) / close",
    "ret_60d": "ts_delta(close, 60) / close",
    "ret_20d": "ts_delta(close, 20) / close",
    "ret_252d": "ts_delta(close, 252) / close",

    # 替代 adv20 (20日平均成交量)
    "adv20": "ts_mean(volume, 20)",
    "adv10": "ts_mean(volume, 10)",
    "adv5": "ts_mean(volume, 5)",

    # 替代 turnover (换手率)
    "turnover": "volume / cap",

    # 替代 market_cap
    "market_cap": "cap",
}
