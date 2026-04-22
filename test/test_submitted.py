"""获取已提交的 Alpha 并追加到文件"""
from core.api_client import BrainAPIClient
import json
from pathlib import Path

def get_submitted_alphas():
    client = BrainAPIClient()

    print("登录...")
    if not client._authenticate():
        return

    # 读取现有的已提交 ID
    path = Path('data/alphas/submitted_ids.json')
    existing_ids = set()
    if path.exists():
        with open(path) as f:
            existing_ids = set(json.load(f))
    print(f"现有已提交: {len(existing_ids)} 个")

    # 获取所有 Alpha 并检查 status
    print("\n获取所有 Alpha...")
    alphas = client.get_all_user_alphas(limit=2500)
    print(f"获取到 {len(alphas)} 个")

    new_submitted = []
    for alpha in alphas:
        alpha_id = alpha.get('id')
        status = alpha.get('status')
        date_submitted = alpha.get('dateSubmitted')

        if (status == 'SUBMITTED' or status == 'ACTIVE') and date_submitted:
            if alpha_id not in existing_ids:
                new_submitted.append(alpha_id)
                print(f"新提交: {alpha_id} (status={status}, submitted={date_submitted})")

    # 合并并保存
    all_submitted = list(existing_ids) + new_submitted
    print(f"\n=== 统计 ===")
    print(f"原有已提交: {len(existing_ids)}")
    print(f"新增已提交: {len(new_submitted)}")
    print(f"总计: {len(all_submitted)}")

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(all_submitted, f, ensure_ascii=False, indent=2)
    print(f"已保存到 {path}")

    return all_submitted

if __name__ == '__main__':
    get_submitted_alphas()
