# -*- coding: utf-8 -*-
"""生成基于勉强接近合格 Alpha 的优化变体"""

# 原表达式
# 1. group_rank(-ts_av_diff(enterprise_value/cashflow, 252), industry)  # Sharpe 1.83, Turn 0.1%
# 2. group_rank(-ts_zscore(enterprise_value/ebitda, 63), industry)       # Sharpe 1.66, Turn 0.2%

# 核心问题：Turnover < 1%
# 优化策略：降低 Decay、缩短窗口、用 ts_delta 捕捉边际变化

variants = []

# ========== 基于 ts_av_diff(enterprise_value/cashflow) 的变体 ==========
# 降低 Decay (30 -> 5, 10) + 缩短窗口 (252 -> 63, 21)
for decay in [5, 10]:
    for window in [63, 21]:
        variants.append(f'group_rank(-ts_av_diff(enterprise_value/cashflow, {window}), industry)|TOP3000|{decay}|SECTOR|0.08')

# 用 ts_delta 替代 ts_av_diff（捕捉边际变化）
for decay in [5, 10]:
    for window in [63, 21, 10]:
        variants.append(f'group_rank(-ts_delta(enterprise_value/cashflow, {window}), industry)|TOP3000|{decay}|SECTOR|0.08')

# 用 ts_rank 替代 ts_av_diff
for decay in [5, 10]:
    for window in [63, 21]:
        variants.append(f'group_rank(-ts_rank(enterprise_value/cashflow, {window}), industry)|TOP3000|{decay}|SECTOR|0.08')

# 换 group (industry -> sector)
for decay in [5, 10]:
    for window in [63, 21]:
        variants.append(f'group_rank(-ts_av_diff(enterprise_value/cashflow, {window}), sector)|TOP3000|{decay}|SECTOR|0.08')

# ========== 基于 ts_zscore(enterprise_value/ebitda) 的变体 ==========
# 降低 Decay + 缩短窗口
for decay in [5, 10]:
    for window in [21, 10]:
        variants.append(f'group_rank(-ts_zscore(enterprise_value/ebitda, {window}), industry)|TOP3000|{decay}|SECTOR|0.08')

# 用 ts_delta 替代
for decay in [5, 10]:
    for window in [63, 21, 10]:
        variants.append(f'group_rank(-ts_delta(enterprise_value/ebitda, {window}), industry)|TOP3000|{decay}|SECTOR|0.08')

# 用 ts_rank 替代
for decay in [5, 10]:
    for window in [21, 10]:
        variants.append(f'group_rank(-ts_rank(enterprise_value/ebitda, {window}), industry)|TOP3000|{decay}|SECTOR|0.08')

# 换 group
for decay in [5, 10]:
    for window in [21, 10]:
        variants.append(f'group_rank(-ts_zscore(enterprise_value/ebitda, {window}), sector)|TOP3000|{decay}|SECTOR|0.08')

# ========== 组合策略（尝试提高 Turnover）==========
# trade_when: 用高频条件触发
for decay in [5, 10]:
    variants.append(f'trade_when(rank(enterprise_value/cashflow) < 0.3, -ts_delta(close, 5), -1)|TOP3000|{decay}|SECTOR|0.08')
    variants.append(f'trade_when(rank(enterprise_value/ebitda) < 0.3, -ts_delta(close, 5), -1)|TOP3000|{decay}|SECTOR|0.08')

# 双因子组合
for decay in [5, 10]:
    variants.append(f'group_rank(rank(enterprise_value/cashflow) + rank(roe), industry)|TOP3000|{decay}|SECTOR|0.08')
    variants.append(f'group_rank(rank(enterprise_value/ebitda) + rank(roe), industry)|TOP3000|{decay}|SECTOR|0.08')

# 输出
print(f'生成 {len(variants)} 条优化变体')
for v in variants:
    print(v)

# 写入文件开头
with open('data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    original = f.read()

with open('data/alphas/to_test.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(variants) + '\n')
    f.write(original)

print(f'\n已追加到 to_test.txt 开头')
