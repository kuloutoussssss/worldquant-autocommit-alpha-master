# -*- coding: utf-8 -*-
"""Alpha 完整工作流 - 回测 -> 筛选 -> 提交"""
import sys
import time
from pathlib import Path
from typing import List, Optional
from core.batch_tester import AlphaBatchTester
from core.submit import submit_alpha_ids
from core.logger import logger


def run_full_workflow(num_to_submit: int = 10, delay: float = 5.0,
                     min_sharpe: float = 1.25, min_fitness: float = 1.0,
                     max_turnover: float = 0.70,
                     input_file: str = "data/alphas/to_test.txt",
                     alpha_id_file: str = "data/alphas/alpha_ids.txt"):
    """
    Alpha 完整工作流
    
    Args:
        num_to_submit: 最大提交数量
        delay: 回测间隔秒数
        min_sharpe: 最小夏普率
        min_fitness: 最小适应度
        max_turnover: 最大换手率
        input_file: 待回测的 Alpha 文件
        alpha_id_file: 合格 Alpha ID 输出文件
    """
    print(f"\n{'='*60}")
    print(f"Alpha Full Workflow")
    print(f"{'='*60}")
    print(f"  Input: {input_file}")
    print(f"  Min Sharpe: {min_sharpe}")
    print(f"  Min Fitness: {min_fitness}")
    print(f"  Max Turnover: {max_turnover*100}%")
    print(f"  Delay: {delay}s")
    print(f"{'='*60}\n")
    
    # Step 1: 批量回测
    print(f"\n[Step 1/3] Batch Testing...")
    print(f"{'='*60}")
    tester = AlphaBatchTester(input_file=input_file)
    tester.run(delay=delay)
    
    # Step 2: 增量同步，确保提交时 checks_passed 是最新状态
    print(f"\n[Step 2/4] Incremental Sync...")
    print(f"{'='*60}")
    from core.db_manager import get_database
    from core.api_client import BrainAPIClient
    
    db = get_database()
    client = BrainAPIClient()
    last_sync = db.get_last_sync_time()
    if last_sync:
        print(f"同步自 {last_sync.strftime('%Y-%m-%d %H:%M')} 以来的数据...")
        alphas = client.get_updated_alphas(
            since=last_sync,
            min_sharpe=-999,
            min_fitness=-999,
            max_turnover=1e9
        )
    else:
        alphas = client.get_all_alphas()
    db.save_alphas(alphas)
    print(f"已同步 {len(alphas)} 个 Alpha 到数据库")
    
    # Step 3: 筛选合格 Alpha
    print(f"\n[Step 3/4] Filtering Qualified Alphas...")
    print(f"{'='*60}")
    
    results_file = tester.output_file
    if not Path(results_file).exists():
        logger.error(f"Results file not found: {results_file}")
        return
    
    import json
    with open(results_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_results = data.get('results', [])
    qualified = [
        r for r in all_results
        if r.get('status') == 'OK'
        and r.get('sharpe', 0) >= min_sharpe
        and r.get('fitness', 0) >= min_fitness
        and r.get('turnover', 1) <= max_turnover
    ]
    
    print(f"\nQualified Alphas: {len(qualified)}")
    
    if len(qualified) > 5:
        for i, r in enumerate(qualified[:5], 1):
            print(f"  {i}. {r.get('alpha_id', 'N/A')}: "
                  f"Sharpe={r.get('sharpe', 0):.2f} "
                  f"Fitness={r.get('fitness', 0):.2f} "
                  f"Turnover={r.get('turnover', 0)*100:.1f}%")
    
    # 保存合格 Alpha ID（先按回测指标筛选，再按8项Checks筛选）
    Path(alpha_id_file).parent.mkdir(parents=True, exist_ok=True)
    
    # 更新候选池（从数据库获取checks_passed=1的Alpha）
    db.update_candidate_pool()
    candidates = db.get_candidates()
    
    # 候选池中有回测结果的Alpha
    qualified_alpha_ids = {r.get('alpha_id') for r in qualified if r.get('alpha_id')}
    final_candidates = [
        c for c in candidates 
        if c.get('alpha_id') in qualified_alpha_ids
    ][:num_to_submit]
    
    with open(alpha_id_file, 'w', encoding='utf-8') as f:
        for c in final_candidates:
            f.write(c['alpha_id'] + '\n')
    
    print(f"\nFinal candidates (passed backtest + 8 checks): {len(final_candidates)}")
    if final_candidates:
        for i, c in enumerate(final_candidates[:5], 1):
            print(f"  {i}. {c.get('alpha_id')}: "
                  f"Sharpe={c.get('sharpe', 0):.2f} "
                  f"Fitness={c.get('fitness', 0):.2f}")
    
    print(f"\nSaved {len(final_candidates)} alpha IDs to {alpha_id_file}")
    
    # Step 4: 提交
    if final_candidates:
        print(f"\n[Step 4/4] Submitting Alphas...")
        print(f"{'='*60}")
        submit_alpha_ids(alpha_id_file, num_to_submit=len(final_candidates))
    else:
        print(f"\nNo qualified alphas to submit (need both backtest pass + 8 checks pass)")
    
    print(f"\n{'='*60}")
    print(f"Workflow Complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Alpha Full Workflow")
    parser.add_argument("--num", type=int, default=10, help="Number to submit")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between tests")
    parser.add_argument("--input", default="data/alphas/to_test_max.txt", help="Input file")
    args = parser.parse_args()
    
    run_full_workflow(num_to_submit=args.num, delay=args.delay, input_file=args.input)
