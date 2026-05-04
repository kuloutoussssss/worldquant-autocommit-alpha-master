# -*- coding: utf-8 -*-
"""查询 EVCF 变体的回测结果"""
import sqlite3

conn = sqlite3.connect('data/alphas.db')
c = conn.cursor()

# 查询包含 enterprise_value 的结果
c.execute("""
SELECT alpha_id, expression, sharpe, turnover, fitness, returns, checks_passed, status
FROM alphas
WHERE expression LIKE '%enterprise_value%'
ORDER BY sharpe DESC
""")
rows = c.fetchall()

print(f'共 {len(rows)} 条 EVCF 变体结果\n')
print('Top 15 (按 Sharpe 排序):')
print('-' * 130)
for r in rows[:15]:
    expr = r[1][:55] + '...' if len(r[1]) > 55 else r[1]
    print(f'{r[0]:10} | {expr:60} | Sharpe:{r[2]:6.2f} | Turn:{r[3]:6.1f} | Fit:{r[4]:5.2f} | Checks:{r[6]}')

print('\n' + '=' * 130)
print('合格统计 (Sharpe>=1.25, Turnover 1-70%, Fitness>=1.0):')
print('-' * 130)

passed = []
failed_turnover = []
failed_other = []

for r in rows:
    alpha_id, expression, sharpe, turnover, fitness, returns, checks_passed, status = r
    # 检查是否合格
    if sharpe >= 1.25 and fitness >= 1.0:
        if 1 <= turnover <= 70:
            passed.append(r)
        else:
            failed_turnover.append(r)
    else:
        failed_other.append(r)

print(f'[合格] {len(passed)} 条')
print(f'[因Turnover失败] {len(failed_turnover)} 条')
print(f'[其他原因失败] {len(failed_other)} 条')

if passed:
    print('\n[合格 Alpha]:')
    for r in passed:
        print(f'  {r[0]:10} | {r[1][:70]:70} | Sharpe:{r[2]:6.2f} | Turn:{r[3]:6.1f} | Fit:{r[4]:5.2f}')

# 统计 Turnover 分布
print('\n' + '=' * 130)
print('Turnover 分布:')
turnover_ranges = {'< 1%': 0, '1-10%': 0, '10-30%': 0, '30-70%': 0, '> 70%': 0}
for r in rows:
    turn = r[3]
    if turn < 1:
        turnover_ranges['< 1%'] += 1
    elif turn < 10:
        turnover_ranges['1-10%'] += 1
    elif turn < 30:
        turnover_ranges['10-30%'] += 1
    elif turn <= 70:
        turnover_ranges['30-70%'] += 1
    else:
        turnover_ranges['> 70%'] += 1

for k, v in turnover_ranges.items():
    print(f'  {k:10}: {v:3} 条')

conn.close()
