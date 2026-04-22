"""直接获取高质量 Alpha 并更新数据库"""
from core.api_client import BrainAPIClient
from core.db_manager import AlphaDatabase
import time

def get_quality_alphas():
    client = BrainAPIClient()
    db = AlphaDatabase()

    print("正在登录...")
    if not client._authenticate():
        return

    # 获取高质量 Alpha（其他7项可能 PASS 的）
    print("\n获取高质量 Alpha (sharpe>=1.2, fitness>=0.9)...")
    alphas = client.get_all_user_alphas(
        limit=100, 
        min_sharpe=1.2, 
        min_fitness=0.9,
        max_turnover=0.7
    )
    print(f"获取到 {len(alphas)} 个 Alpha")

    # 分析 checks 状态
    passed_7 = 0
    pending_self_corr = 0
    failed_other = 0
    
    for alpha in alphas:
        is_data = alpha.get('is') or {}
        checks = is_data.get('checks') or []
        
        self_corr_pending = False
        all_pass_except_self = True
        
        for c in checks:
            name = c.get('name')
            result = c.get('result')
            
            if name == 'SELF_CORRELATION' and result == 'PENDING':
                self_corr_pending = True
            elif result != 'PASS':
                all_pass_except_self = False
        
        if all_pass_except_self:
            if self_corr_pending:
                pending_self_corr += 1
                alpha_id = alpha.get('id')
                print(f"  7项全PASS, SELF_CORRELATION=PENDING: {alpha_id}")
                print(f"    sharpe={is_data.get('sharpe')}, fitness={is_data.get('fitness')}")
            else:
                passed_7 += 1
        else:
            failed_other += 1

    print(f"\n=== 统计 ===")
    print(f"7项全PASS + SELF_CORRELATION=PENDING: {pending_self_corr}")
    print(f"7项全PASS + SELF_CORRELATION=PASS: {passed_7}")
    print(f"其他失败: {failed_other}")

    # 更新数据库
    if alphas:
        print("\n正在更新数据库...")
        new_count, update_count = db.save_alphas(alphas, is_full_sync=False)
        print(f"保存完成: {new_count} 新增, {update_count} 更新")
        
        # 更新候选池
        db.update_candidate_pool()
        print(f"候选池数量: {db.get_candidate_pool_count()}")

if __name__ == '__main__':
    get_quality_alphas()
