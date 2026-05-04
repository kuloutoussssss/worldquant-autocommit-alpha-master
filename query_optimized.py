# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect('data/alphas.db')
c = conn.cursor()

# 查询包含 enterprise_value 的最新结果（EV/CF 和 EV/EBITDA）
c.execute("""
SELECT alpha_id, expression, sharpe, turnover, fitness 
FROM alphas 
WHERE expression LIKE '%enterprise_value%'
ORDER BY sharpe DESC
LIMIT 20
""")

print("=" * 80)
print("TOP 20 enterprise_value 相关 Alpha (按 Sharpe 排序)")
print("=" * 80)
for row in c.fetchall():
    aid, expr, sharpe, turn, fit = row
    status = "OK" if sharpe >= 1.25 and 1 <= turn <= 70 and fit >= 1.0 else "--"
    print(f'{status} {aid} | Sharpe:{sharpe:.2f} | Turn:{turn:.1f}% | Fit:{fit:.2f}')
    print(f'   {expr[:70]}...' if len(expr) > 70 else f'   {expr}')
    print()

# 统计合格数量
c.execute("""
SELECT COUNT(*) FROM alphas 
WHERE expression LIKE '%enterprise_value%'
AND sharpe >= 1.25 AND turnover >= 1 AND turnover <= 70 AND fitness >= 1.0
""")
qualified = c.fetchone()[0]

c.execute("""
SELECT COUNT(*) FROM alphas 
WHERE expression LIKE '%enterprise_value%'
""")
total = c.fetchone()[0]

print("=" * 80)
print(f"统计: {qualified}/{total} 条合格 (Sharpe≥1.25, Turnover 1-70%, Fitness≥1.0)")
print("=" * 80)

conn.close()
