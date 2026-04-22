# -*- coding: utf-8 -*-
"""检查 ts_zscore 缺少窗口参数的情况"""
import re

with open(r'd:/python_repo/worldquant-autocommit-alpha-master/data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

problems = []
for i, line in enumerate(lines, 1):
    expr = line.strip().split('|')[0]
    # 查找 ts_zscore(字段) 没有第二个参数的情况
    if re.search(r'ts_zscore\([^,)]+\)', expr):
        problems.append((i, line.strip()[:150]))

print(f'ts_zscore without window: {len(problems)}')
for i, l in problems[:10]:
    print(f'Line {i}: {l}')
