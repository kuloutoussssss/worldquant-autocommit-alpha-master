# -*- coding: utf-8 -*-
"""导出自相关高的 Alpha 表达式（仅表达式）"""
import sys
sys.path.insert(0, '.')

from core.db_manager import get_database

db = get_database()
conn = db._get_connection()

# 查询 SELF_CORRELATION 失败的 Alpha
rows = conn.execute("""
SELECT expression
FROM alphas 
WHERE checks_passed = 1 AND submit_fail_count > 0
AND submit_fail_reason LIKE '%SELF_CORRELATION%'
ORDER BY submit_fail_count DESC
""").fetchall()

with open('data/alphas/self_correlation_expressions.txt', 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(r[0] + '\n')

print(f"Exported {len(rows)} expressions to data/alphas/self_correlation_expressions.txt")
