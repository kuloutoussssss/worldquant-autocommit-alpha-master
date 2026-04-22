# -*- coding: utf-8 -*-
"""检查表达式中是否有单独的字母 a"""
import re

with open(r'd:/python_repo/worldquant-autocommit-alpha-master/data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

problems = []
for i, line in enumerate(lines, 1):
    expr = line.strip().split('|')[0]
    
    # 检查是否有 , a, 或 (a, 或 ,a) 这样的模式
    # 这表示有一个单独的字母作为参数
    if re.search(r'[,\(\s]a[\),\s]', expr):
        problems.append((i, line.strip()[:150]))
    # 检查是否有 ,a, 或 , a, 但不是数字的一部分
    if re.search(r',a,|,\s*a\s*,|,a\)|,\s*a\s\)', expr):
        problems.append((i, line.strip()[:150]))

print(f'Found {len(problems)} potential problem lines')
for i, l in problems[:20]:
    print(f'Line {i}: {l}')
