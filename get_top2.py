# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect('data/alphas.db')
c = conn.cursor()

# 查询两个勉强接近合格的 Alpha
alpha_ids = ['0mK2Vlw8', 'd5lr9qRv']
for aid in alpha_ids:
    c.execute("SELECT alpha_id, expression, sharpe, turnover, fitness FROM alphas WHERE alpha_id = ?", (aid,))
    row = c.fetchone()
    if row:
        print(f'{row[0]} | Sharpe:{row[2]:.2f} | Turn:{row[3]:.1f} | Fit:{row[4]:.2f}')
        print(f'  {row[1]}')
        print()

conn.close()
