# -*- coding: utf-8 -*-
"""迁移脚本：将 JSON 文件数据迁移到 SQLite 数据库"""
import sys
sys.path.insert(0, '.')

from core.db_manager import get_database

def main():
    print("=" * 60)
    print("Alpha 数据迁移工具 - JSON → SQLite")
    print("=" * 60)
    
    db = get_database()
    
    # 1. 迁移 results 目录下的 JSON 文件
    print("\n[1/3] 迁移 results 目录下的回测结果...")
    stats = db.migrate_results_directory("data/results")
    print(f"   - batch_results.json: {stats['batch_results']} 条")
    print(f"   - all_results_*.json: {stats['all_results']} 条")
    
    # 2. 清理重复数据
    print("\n[2/3] 清理重复数据...")
    deleted = db.cleanup_duplicate_tested_expressions()
    print(f"   - 删除重复记录: {deleted} 条")
    
    # 3. 删除已迁移的文件
    print("\n[3/3] 删除已迁移的 JSON 文件...")
    import os
    from pathlib import Path
    
    deleted_files = []
    
    # 删除 results 目录下的已迁移文件
    results_dir = Path("data/results")
    for f in results_dir.glob("batch_results.json"):
        f.unlink()
        deleted_files.append(str(f))
    for f in results_dir.glob("all_results_*.json"):
        f.unlink()
        deleted_files.append(str(f))
    
    # 删除 candidate_pool.json（已迁移到数据库）
    candidate_file = Path("data/alphas/candidate_pool.json")
    if candidate_file.exists():
        candidate_file.unlink()
        deleted_files.append(str(candidate_file))
    
    # 删除 submitted_ids.json（已迁移到数据库 alphas.submitted_at）
    submitted_ids = Path("data/alphas/submitted_ids.json")
    if submitted_ids.exists():
        submitted_ids.unlink()
        deleted_files.append(str(submitted_ids))
    
    for f in deleted_files:
        print(f"   - 已删除: {f}")
    
    # 最终统计
    print("\n" + "=" * 60)
    print("迁移完成!")
    print("=" * 60)
    
    db.print_report()
    print(f"\n数据库统计:")
    print(f"  已回测表达式总数: {db.get_tested_count()}")
    print(f"  候选池数量: {db.get_candidate_pool_count()}")

if __name__ == "__main__":
    main()
