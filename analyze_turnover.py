# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect('data/alphas.db')
c = conn.cursor()

# 查询优化变体的具体结果（decay=5/10, window=63/21）
print("=" * 80)
print("优化变体回测结果 (Decay 5/10, 窗口 63/21)")
print("=" * 80)

# 查询包含 ts_delta 和 ts_av_diff 的变体
c.execute("""
SELECT alpha_id, expression, sharpe, turnover, fitness 
FROM alphas 
WHERE expression LIKE '%ts_delta(enterprise_value%' 
   OR expression LIKE '%ts_av_diff(enterprise_value%'
ORDER BY sharpe DESC
LIMIT 15
""")

for row in c.fetchall():
    aid, expr, sharpe, turn, fit = row
    print(f'{aid} | Sharpe:{sharpe:.2f} | Turn:{turn:.2f}% | Fit:{fit:.2f}')
    print(f'   {expr}')
    print()

# 查询 trade_when 组合
print("=" * 80)
print("trade_when 组合结果")
print("=" * 80)

c.execute("""
SELECT alpha_id, expression, sharpe, turnover, fitness 
FROM alphas 
WHERE expression LIKE '%trade_when%enterprise_value%'
ORDER BY sharpe DESC
""")

for row in c.fetchall():
    aid, expr, sharpe, turn, fit = row
    print(f'{aid} | Sharpe:{sharpe:.2f} | Turn:{turn:.2f}% | Fit:{fit:.2f}')
    print(f'   {expr}')
    print()

# 对比：查看 Turnover > 1% 的 Alpha 长什么样
print("=" * 80)
print("对比：Turnover > 1% 的 Alpha 示例")
print("=" * 80)

c.execute("""
SELECT alpha_id, expression, sharpe, turnover, fitness 
FROM alphas 
WHERE turnover > 1 AND sharpe > 1.0
ORDER BY sharpe DESC
LIMIT 5
""")

for row in c.fetchall():
    aid, expr, sharpe, turn, fit = row
    print(f'{aid} | Sharpe:{sharpe:.2f} | Turn:{turn:.1f}% | Fit:{fit:.2f}')
    print(f'   {expr[:80]}...' if len(expr) > 80 else f'   {expr}')
    print()

conn.close()
