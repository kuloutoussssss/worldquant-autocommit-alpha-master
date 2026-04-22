#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""替换 regression_neut 为 group_neutralize 版本"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

F = 'fnd6_newqv1300_ivltq'
slow_signals = [
    'ts_regression(ts_sum(ts_backfill(' + F + ',60),252),ts_step(1),756,rettype=2)',
    'ts_regression(ts_sum(ts_backfill(' + F + ',60),60),ts_step(1),252,rettype=2)',
    'ts_regression(ts_backfill(' + F + ',60),ts_step(1),252,rettype=2)',
    'ts_regression(ts_backfill(' + F + ',20),ts_step(1),126,rettype=2)',
]

price_factors = [
    'returns', 'ts_mean(returns, 5)', 'ts_mean(returns, 10)',
    'volume/ts_mean(volume, 20)', 'ts_zscore(volume, 10)', 'scl12_buzz'
]

# 读取现有
with open('data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    existing = set(l.strip().split('|')[0] for l in f if l.strip())

new_alphas = []

# 1. group_neutralize(group_rank(slow, G), bucket(rank(cap)))
for s in slow_signals:
    for g in ['sector', 'industry', 'subindustry']:
        expr = f'group_neutralize(group_rank({s}, {g}), bucket(rank(cap), range="0.1,1,0.1"))'
        if expr not in existing:
            new_alphas.append(expr)

# 2. group_neutralize(slow * pf, bucket(rank(cap)))
for s in slow_signals:
    for pf in price_factors:
        expr = f'group_neutralize({s} * {pf}, bucket(rank(cap), range="0.1,1,0.1"))'
        if expr not in existing:
            new_alphas.append(expr)

# 3. group_neutralize(slow, bucket(rank(cap))) * pf
for s in slow_signals:
    for pf in price_factors:
        expr = f'group_neutralize({s}, bucket(rank(cap), range="0.1,1,0.1")) * {pf}'
        if expr not in existing:
            new_alphas.append(expr)

# 4. group_neutralize(group_rank(slow, G) * rank(pf), bucket(rank(cap)))
for s in slow_signals[:2]:
    for g in ['sector', 'industry']:
        for pf in ['returns', 'volume/ts_mean(volume, 20)', 'ts_mean(returns, 5)']:
            expr = f'group_neutralize(group_rank({s}, {g}) * rank({pf}), bucket(rank(cap), range="0.1,1,0.1"))'
            if expr not in existing:
                new_alphas.append(expr)

# 5. group_neutralize + trade_when 组合
for s in slow_signals:
    for cond in ['volume > ts_mean(volume, 20)', 'returns < 0']:
        inner = f'group_neutralize({s}, bucket(rank(cap), range="0.1,1,0.1"))'
        expr = f'trade_when({cond}, {inner}, -1)'
        if expr not in existing:
            new_alphas.append(expr)

# 去重
seen = set()
unique = []
for a in new_alphas:
    if a not in seen:
        seen.add(a)
        unique.append(a)

# 追加写入
with open('data/alphas/to_test.txt', 'a', encoding='utf-8') as f:
    for a in unique:
        f.write(f'{a}|TOP3000|1|SUBINDUSTRY|0|0.08\n')

# 计数
with open('data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    total = sum(1 for _ in f)

print(f'新增: {len(unique)} 条 (替换 regression_neut)')
print(f'总计: {total} 条')
