# -*- coding: utf-8 -*-
"""彻底检查所有可能的变量问题"""
import re

with open(r'd:/python_repo/worldquant-autocommit-alpha-master/data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 检查所有可能的独立字母变量
single_letters = set('abcdefghijklmnopqrstuvwxyz')
problems = []

for i, line in enumerate(lines, 1):
    expr = line.strip().split('|')[0]
    
    # 检查是否有逗号、空格、括号后跟单个字母
    for letter in single_letters:
        patterns = [
            f',{letter},',  # ,a,
            f', {letter},',  # , a,
            f'({letter},',  # (a,
            f'( {letter},',  # ( a,
            f',{letter})',  # ,a)
            f', {letter})',  # , a)
            f'({letter})',  # (a)
            f'( {letter} )',  # ( a )
        ]
        for pattern in patterns:
            if pattern in expr:
                problems.append((i, letter, pattern, line.strip()[:150]))
                break

print(f'Found {len(problems)} potential problem lines')
for i, letter, pattern, line in problems[:30]:
    print(f'Line {i} (letter={letter}, pattern={pattern}): {line}')
