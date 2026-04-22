# -*- coding: utf-8 -*-
"""彻底检查问题表达式"""
import re

with open(r'd:/python_repo/worldquant-autocommit-alpha-master/data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

problems = []
for i, line in enumerate(lines, 1):
    expr = line.strip().split('|')[0]
    
    # 检查 ts_xxx(单字母, 或 ts_xxx(单字母) 的模式
    if re.search(r'ts_\w+\(\s*[a-z]\s*[,)]', expr, re.IGNORECASE):
        problems.append((i, line.strip()[:150]))
    
    # 检查操作符后跟单个字母
    if re.search(r'[\+\-\*\/\(\,]\s*[a-z]\s*[\)\+\-\*\/\,]', expr):
        problems.append((i, line.strip()[:150]))

print(f'Found {len(problems)} potential problem lines')
for i, l in problems[:30]:
    print(f'Line {i}: {l}')
