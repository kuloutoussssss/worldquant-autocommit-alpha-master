# -*- coding: utf-8 -*-
"""测试 API 连接"""
from core.api_client import BrainAPIClient, BASE_URL

client = BrainAPIClient()
print(f'Email: {client.email[:3]}***')
print(f'Password 长度: {len(client.password)}')

print('\n正在测试认证...')
if client._authenticate():
    print('认证成功！')

    print('\n正在获取 Alphas...')
    alphas = client.get_all_user_alphas(limit=100, offset=0)
    print(f'\n获取到 {len(alphas)} 个 Alpha')

    if alphas:
        print(f'\n前3个 Alpha:')
        for a in alphas[:3]:
            print(f'  ID: {a.get("id")}')
            print(f'    表达式: {a.get("regular", {}).get("code", "")[:50]}...')
            print(f'    夏普率: {a.get("is", {}).get("sharpe", "N/A")}')
            print(f'    适应度: {a.get("is", {}).get("fitness", "N/A")}')
            print(f'    换手率: {a.get("is", {}).get("turnover", "N/A")}')
            print(f'    状态: {a.get("status")}')
else:
    print('\n认证失败！')
