# -*- coding: utf-8 -*-
"""
测试脚本 - 同步单个 Alpha 到数据库
用于验证数据库保存逻辑
"""

import asyncio
import json
from api_client import AsyncBrainAPIClient
from db_manager import get_database


async def test_single_alpha_save():
    """测试保存单个 Alpha"""
    print("=" * 50)
    print("测试同步单个 Alpha 到数据库")
    print("=" * 50)
    
    db = get_database()
    client = AsyncBrainAPIClient()
    
    try:
        print("\n正在获取账户 Alpha 列表（只取第一个）...")
        
        # 先认证
        await client._authenticate()
        
        # 只获取第一页（最多100个）
        result = await client.get_user_alphas_async(limit=10, offset=0)
        alpha_list = result.get("results", []) or result.get("data", [])
        
        if not alpha_list:
            print("没有获取到任何 Alpha")
            return
        
        print(f"获取到 {len(alpha_list)} 个 Alpha 列表项")
        
        # 只取第一个获取详情
        first_alpha = alpha_list[0]
        alpha_id = first_alpha.get("id")
        print(f"测试 Alpha ID: {alpha_id}")
        
        # 获取详情（添加延迟避免429）
        await asyncio.sleep(1)
        alpha = await client.get_alpha_details_async(alpha_id)
        
        # 检查返回内容
        print(f"\nAlpha 详情 Keys: {list(alpha.keys())}")
        if 'error' in alpha:
            print(f"   包含 error 字段: {alpha['error']}")
            # 如果是429错误，等待后重试
            if '429' in str(alpha.get('error', '')):
                print("   等待3秒后重试...")
                await asyncio.sleep(3)
                alpha = await client.get_alpha_details_async(alpha_id)
                if 'error' in alpha:
                    print(f"   重试失败: {alpha['error']}")
                    return
            else:
                return
        
        alpha_id = alpha.get('alpha_id')
        
        print(f"\n测试 Alpha: {alpha_id}")
        print(f"   名称: {alpha.get('name', 'N/A')}")
        
        # 打印各字段类型信息
        print("\n字段类型检查:")
        fields_to_check = ['settings', 'checks', 'dateUpdated', 'dateCreated', 
                          'sharpe', 'fitness', 'turnover', 'name', 'stage', 'expression']
        for field in fields_to_check:
            value = alpha.get(field)
            value_type = type(value).__name__
            preview = str(value)[:50] if value is not None else "None"
            print(f"   {field}: {value_type} = {preview}")
        
        # 尝试保存
        print("\n尝试保存到数据库...")
        
        # 调试：打印 settings 的详细信息
        settings = alpha.get('settings')
        print(f"\n调试 - settings 类型: {type(settings).__name__}")
        print(f"调试 - settings 值: {settings}")
        print(f"调试 - settings 是否为 dict: {isinstance(settings, dict)}")
        
        try:
            new_count, update_count = db.save_alphas([alpha], is_full_sync=False)
            print(f"保存成功! 新增: {new_count}, 更新: {update_count}")
        except Exception as e:
            print(f"保存失败: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # 验证保存结果
        print("\n验证数据库记录:")
        all_alphas = db.get_all_alphas()
        print(f"   数据库中总记录数: {len(all_alphas)}")
        
        if all_alphas:
            saved = all_alphas[0]
            print(f"   最新记录 ID: {saved.get('alpha_id')}")
            print(f"   名称: {saved.get('name')}")
            print(f"   Sharpe: {saved.get('sharpe')}")
            print(f"   Fitness: {saved.get('fitness')}")
            print(f"   创建时间: {saved.get('created_at')}")
        
        print("\n" + "=" * 50)
        print("测试完成!")
        print("=" * 50)
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_single_alpha_save())
