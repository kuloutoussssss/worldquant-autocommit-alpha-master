# -*- coding: utf-8 -*-
"""测试 API 获取 Alpha"""
import sys
import os
sys.path.insert(0, '.')

# 设置编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from api_client import BrainAPIClient

def main():
    print("[*] Connecting to WorldQuant Brain API...")

    client = BrainAPIClient()

    # 测试获取单个 Alpha 详情
    test_ids = ['xAm6rxRq', 'xAmAMWnJ', 'xAm7Q2fR']

    for alpha_id in test_ids:
        print(f"\n[*] Get Alpha: {alpha_id}")
        result = client.get_alpha_details(alpha_id)
        if "error" in result:
            print(f"  [ERROR] {result['error']}")
        else:
            print(f"  [OK] Sharpe={result['sharpe']:.2f}, Fitness={result['fitness']:.2f}, Turnover={result['turnover']*100:.1f}%")
            checks = result.get('checks', [])
            print(f"  Checks ({len(checks)}):")
            for c in checks:
                print(f"    - {c.get('name')}: {c.get('result')}")

    # 测试获取用户 Alpha 列表
    print("\n\n[*] Get user alphas...")
    result = client.get_user_alphas(limit=10, offset=0)
    print(f"  Result: {result}")

    # 尝试不同 stage
    for stage in ['SIM', 'LIVE', 'PROD', None]:
        print(f"\n[*] Get stage={stage}...")
        result = client.get_user_alphas(limit=5, offset=0, stage=stage)
        count = result.get('count', 0)
        results = result.get('results', [])
        print(f"  count={count}, returned {len(results)}")
        if results:
            for a in results[:3]:
                print(f"    - {a.get('id')}")

if __name__ == "__main__":
    main()
