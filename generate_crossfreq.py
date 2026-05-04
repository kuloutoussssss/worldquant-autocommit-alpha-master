# -*- coding: utf-8 -*-
"""
生成 Cross-Frequency 组合策略
- 估值因子做条件（低频）
- 高频信号触发（日频）
- 目标：突破 Turnover 1% 门槛
"""

variants = []

# ========== 策略 A: 估值条件 + 动量信号 ==========
# 低估值股票 + 价格动量
base_ev_cf = "rank(enterprise_value/cashflow_from_operating_activities)"
base_ev_ebitda = "rank(enterprise_value/ebitda)"

# 动量信号
momentum_signals = [
    "ts_delta(close, 5)",
    "ts_delta(close, 10)",
    "ts_rank(close, 10)",
    "ts_rank(returns, 5)",
    "-ts_delta(close, 5)",  # 反转
    "-ts_rank(close, 10)",
]

# 组合：低估值 + 动量
for ev in [base_ev_cf, base_ev_ebitda]:
    for mom in momentum_signals:
        variants.append(f"trade_when({ev} < 0.3, {mom}, -1)")
        variants.append(f"trade_when({ev} < 0.2, {mom}, -1)")
        variants.append(f"trade_when({ev} < 0.1, {mom}, -1)")

# ========== 策略 B: 估值条件 + 成交量信号 ==========
volume_signals = [
    "ts_rank(volume, 10)",
    "ts_rank(volume, 5)",
    "-ts_rank(volume, 10)",
    "rank(volume/ts_mean(volume, 20))",
]

for ev in [base_ev_cf, base_ev_ebitda]:
    for vol in volume_signals:
        variants.append(f"trade_when({ev} < 0.3, {vol}, -1)")
        variants.append(f"trade_when({ev} < 0.2, {vol}, -1)")

# ========== 策略 C: 估值条件 + 波动率信号 ==========
volatility_signals = [
    "-ts_std_dev(returns, 10)",
    "-ts_std_dev(returns, 20)",
    "rank(-ts_std_dev(returns, 10))",
    "-ts_rank(ts_std_dev(returns, 10), 20)",
]

for ev in [base_ev_cf, base_ev_ebitda]:
    for vol in volatility_signals:
        variants.append(f"trade_when({ev} < 0.3, {vol}, -1)")
        variants.append(f"trade_when({ev} < 0.2, {vol}, -1)")

# ========== 策略 D: 估值条件 + 新闻情绪 ==========
news_signals = [
    "ts_delta(news_eod_close, 5)",
    "ts_rank(news_eod_close, 10)",
    "-ts_rank(news_eod_close, 10)",
]

for ev in [base_ev_cf, base_ev_ebitda]:
    for news in news_signals:
        variants.append(f"trade_when({ev} < 0.3, {news}, -1)")

# ========== 策略 E: 估值×质量 组合（无 trade_when）==========
# 直接组合，用乘法/加法
quality_factors = [
    "ts_rank(roe, 63)",
    "ts_rank(roa, 63)",
    "ts_rank(gross_margin, 63)",
    "ts_rank(asset_turnover, 63)",
]

for q in quality_factors:
    variants.append(f"-rank(enterprise_value/cashflow_from_operating_activities) * {q}")
    variants.append(f"-rank(enterprise_value/ebitda) * {q}")
    variants.append(f"group_rank(-enterprise_value/cashflow_from_operating_activities * {q}, industry)")
    variants.append(f"group_rank(-enterprise_value/ebitda * {q}, industry)")

# ========== 策略 F: 高频估值变化 ==========
# 用 ts_delta 捕捉估值因子的日频变化
variants.extend([
    "ts_delta(rank(enterprise_value/cashflow_from_operating_activities), 1)",
    "ts_delta(rank(enterprise_value/ebitda), 1)",
    "-ts_delta(rank(enterprise_value/cashflow_from_operating_activities), 5)",
    "-ts_delta(rank(enterprise_value/ebitda), 5)",
    "group_rank(-ts_delta(rank(enterprise_value/cashflow_from_operating_activities), 5), industry)",
    "group_rank(-ts_delta(rank(enterprise_value/ebitda), 5), industry)",
])

# ========== 输出 ==========
print(f"生成 {len(variants)} 条策略")

# 写入文件
with open('data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    existing = f.read()

with open('data/alphas/to_test.txt', 'w', encoding='utf-8') as f:
    for v in variants:
        f.write(v + '\n')
    f.write(existing)

print(f"已写入 to_test.txt 开头，原有内容保留")
