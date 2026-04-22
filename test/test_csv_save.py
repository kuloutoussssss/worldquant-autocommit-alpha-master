# -*- coding: utf-8 -*-
"""
测试脚本 - 使用 CSV 保存 Alpha 数据
"""

import asyncio
import csv
import json
import os
from datetime import datetime
from api_client import AsyncBrainAPIClient


CSV_PATH = "data/alphas.csv"


def save_alphas_to_csv(alphas: list, csv_path: str = CSV_PATH):
    """保存 Alpha 列表到 CSV"""
    if not alphas:
        return
    
    # 确保目录存在
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    # 定义字段
    fieldnames = [
        'alpha_id', 'name', 'stage', 'sharpe', 'fitness', 'turnover',
        'returns', 'drawdown', 'margin', 'checks', 'expression',
        'settings', 'dateCreated', 'dateUpdated', 'saved_at'
    ]
    
    # 检查文件是否存在
    file_exists = os.path.exists(csv_path)
    
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        for alpha in alphas:
            row = {
                'alpha_id': alpha.get('alpha_id', ''),
                'name': alpha.get('name', ''),
                'stage': alpha.get('stage', ''),
                'sharpe': alpha.get('sharpe', 0),
                'fitness': alpha.get('fitness', 0),
                'turnover': alpha.get('turnover', 0),
                'returns': alpha.get('returns', 0),
                'drawdown': alpha.get('drawdown', 0),
                'margin': alpha.get('margin', 0),
                'checks': json.dumps(alpha.get('checks', []), ensure_ascii=False),
                'expression': alpha.get('expression', ''),
                'settings': json.dumps(alpha.get('settings', {}), ensure_ascii=False),
                'dateCreated': alpha.get('dateCreated', ''),
                'dateUpdated': alpha.get('dateUpdated', ''),
                'saved_at': datetime.now().isoformat()
            }
            writer.writerow(row)
    
    print(f"✅ 已保存 {len(alphas)} 个 Alpha 到 {csv_path}")


def load_alphas_from_csv(csv_path: str = CSV_PATH) -> list:
    """从 CSV 加载 Alpha 列表"""
    if not os.path.exists(csv_path):
        return []
    
    alphas = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            alpha = {
                'alpha_id': row['alpha_id'],
                'name': row['name'],
                'stage': row['stage'],
                'sharpe': float(row['sharpe']) if row['sharpe'] else 0,
                'fitness': float(row['fitness']) if row['fitness'] else 0,
                'turnover': float(row['turnover']) if row['turnover'] else 0,
                'returns': float(row['returns']) if row['returns'] else 0,
                'drawdown': float(row['drawdown']) if row['drawdown'] else 0,
                'margin': float(row['margin']) if row['margin'] else 0,
                'checks': json.loads(row['checks']) if row['checks'] else [],
                'expression': row['expression'],
                'settings': json.loads(row['settings']) if row['settings'] else {},
                'dateCreated': row['dateCreated'],
                'dateUpdated': row['dateUpdated']
            }
            alphas.append(alpha)
    
    return alphas


async def test_csv_save():
    """测试 CSV 保存"""
    print("=" * 50)
    print("🧪 测试 CSV 保存 Alpha")
    print("=" * 50)
    
    client = AsyncBrainAPIClient()
    
    try:
        print("\n📥 正在获取账户 Alpha 列表...")
        await client._authenticate()
        
        result = await client.get_user_alphas_async(limit=10, offset=0)
        alpha_list = result.get("results", []) or result.get("data", [])
        
        if not alpha_list:
            print("❌ 没有获取到任何 Alpha")
            return
        
        print(f"✅ 获取到 {len(alpha_list)} 个 Alpha 列表项")
        
        # 只取第一个获取详情
        first_alpha = alpha_list[0]
        alpha_id = first_alpha.get("id")
        print(f"🎯 测试 Alpha ID: {alpha_id}")
        
        # 获取详情
        alpha = await client.get_alpha_details_async(alpha_id)
        
        if 'error' in alpha:
            print(f"❌ 获取详情失败: {alpha['error']}")
            return
        
        print(f"\n📊 Alpha 信息:")
        print(f"   ID: {alpha.get('alpha_id')}")
        print(f"   Sharpe: {alpha.get('sharpe')}")
        print(f"   Fitness: {alpha.get('fitness')}")
        print(f"   Turnover: {alpha.get('turnover')}")
        print(f"   Checks: {len(alpha.get('checks', []))} 项")
        
        # 保存到 CSV
        print("\n💾 保存到 CSV...")
        save_alphas_to_csv([alpha])
        
        # 验证读取
        print("\n📋 验证 CSV 读取:")
        loaded = load_alphas_from_csv()
        print(f"   CSV 中总记录数: {len(loaded)}")
        if loaded:
            last = loaded[-1]
            print(f"   最后一条记录 ID: {last.get('alpha_id')}")
            print(f"   Sharpe: {last.get('sharpe')}")
        
        print("\n" + "=" * 50)
        print("🎉 CSV 测试完成!")
        print("=" * 50)
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_csv_save())
