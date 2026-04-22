# -*- coding: utf-8 -*-
"""
工作流任务执行器
功能：封装工作流逻辑（回测→同步→筛选→提交）
"""
import json
import time
import sys
from datetime import datetime
from pathlib import Path

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
sys_path = str(PROJECT_ROOT)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)


def run_workflow_task(task_id: str, config: dict):
    """
    执行一键工作流
    
    Args:
        task_id: 任务ID
        config: 工作流配置参数
    """
    from core.api_client import BrainAPIClient
    from core.db_manager import AlphaDatabase, get_database
    from core.submit import submit_alpha_ids
    from web.utils.helpers import load_to_test_alphas, save_to_test_alphas
    
    # 任务文件路径
    tasks_file = PROJECT_ROOT / "data" / "tasks.json"
    db_path = PROJECT_ROOT / "data" / "alphas.db"
    to_test_file = PROJECT_ROOT / "data" / "alphas" / "to_test.txt"
    
    def load_tasks():
        if tasks_file.exists():
            try:
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_tasks(tasks):
        with open(tasks_file, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    def update_task(task_id, **kwargs):
        tasks = load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                for key, value in kwargs.items():
                    if key in ["progress", "completed", "failed", "status"]:
                        task[key] = value
                    elif key == "error":
                        task["error"] = value
                    elif key == "details":
                        task["details"] = value
                if task["status"] in ["completed", "stopped", "failed"]:
                    task["finished_at"] = datetime.now().isoformat()
                break
        save_tasks(tasks)
    
    def append_detail(task_id, detail):
        tasks = load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                task["details"].append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": detail
                })
                if len(task["details"]) > 100:
                    task["details"] = task["details"][-100:]
                break
        save_tasks(tasks)
    
    def is_stopped(task_id):
        tasks = load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                return task.get("status") == "stopped"
        return True
    
    # 更新任务描述
    update_task(task_id, description="一键工作流: 回测→同步→筛选→提交")
    
    try:
        db = AlphaDatabase(str(db_path))
        client = BrainAPIClient()
        
        if not client.ensure_session():
            update_task(task_id, status="failed", error="认证失败")
            return
        
        # ===== 步骤1: 批量回测 =====
        append_detail(task_id, "步骤 1/4: 批量回测")
        update_task(task_id, progress=0.05)
        
        # 加载待回测数据
        alphas = load_to_test_alphas()
        tested_exprs = set(row[0] for row in db.get_tested_expressions())
        untested = [a for a in alphas if a.split("|")[0].strip() not in tested_exprs]
        
        if untested:
            completed = 0
            failed = 0
            total = len(untested)
            
            params = config.get("backtest_params", {})
            
            for i, expression in enumerate(untested):
                if is_stopped(task_id):
                    append_detail(task_id, "任务已停止")
                    update_task(task_id, status="stopped")
                    return
                
                parts = expression.split("|")
                expr = parts[0].strip()
                p_universe = parts[1].strip() if len(parts) > 1 else params.get("universe", "TOP3000")
                p_decay = int(parts[2].strip()) if len(parts) > 2 else params.get("decay", 30)
                p_neutralization = parts[3].strip() if len(parts) > 3 else params.get("neutralization", "SUBINDUSTRY")
                p_truncation = float(parts[4].strip()) if len(parts) > 4 else params.get("truncation", 0.08)
                
                append_detail(task_id, f"回测 [{completed + failed + 1}/{total}]: {expr[:40]}...")
                update_task(task_id, progress=0.05 + 0.25 * (completed + failed) / total)
                
                result = client.test_alpha(
                    expression=expr,
                    universe=p_universe,
                    region=params.get("region", "USA"),
                    decay=p_decay,
                    neutralization=p_neutralization,
                    truncation=p_truncation,
                    test_period=params.get("test_period", "P2Y0M")
                )
                
                if result.get("status") == "OK":
                    location = result.get("location", "")
                    result = client.get_simulation_result(location)
                    
                    if result.get("status") == "OK":
                        data = result.get("data", {})
                        is_data = data.get("is", {})
                        
                        db.add_tested_expression(
                            expression=expr,
                            alpha_id=location.split("/")[-1] if "/" in location else "",
                            sharpe=is_data.get("sharpe"),
                            fitness=is_data.get("fitness"),
                            turnover=is_data.get("turnover"),
                            returns=is_data.get("returns"),
                            drawdown=is_data.get("drawdown"),
                            status="OK"
                        )
                        
                        # 从待测列表移除
                        alphas = load_to_test_alphas()
                        alphas = [a for a in alphas if a.split("|")[0].strip() != expr]
                        save_to_test_alphas(alphas)
                        
                        completed += 1
                        append_detail(task_id, f"✅ 成功")
                    else:
                        failed += 1
                        append_detail(task_id, f"❌ 回测失败")
                else:
                    failed += 1
                    append_detail(task_id, f"❌ 提交失败")
                
                update_task(task_id, completed=completed, failed=failed)
                time.sleep(config.get("delay", 5))
            
            append_detail(task_id, f"回测完成: {completed} 成功, {failed} 失败")
        
        # ===== 步骤2: 增量同步 =====
        if is_stopped(task_id):
            update_task(task_id, status="stopped")
            return
        
        append_detail(task_id, "步骤 2/4: 增量同步")
        update_task(task_id, progress=0.35)
        
        db_instance = get_database()
        last_sync = db_instance.get_last_sync_time()
        
        if last_sync:
            append_detail(task_id, f"同步自 {last_sync.strftime('%Y-%m-%d %H:%M')} 以来的数据...")
            alphas = client.get_updated_alphas(
                since=last_sync,
                min_sharpe=-999,
                min_fitness=-999,
                max_turnover=1e9
            )
        else:
            append_detail(task_id, "执行全量同步...")
            alphas = client.get_all_user_alphas(
                min_sharpe=-999,
                min_fitness=-999,
                max_turnover=1e9
            )
        
        if alphas:
            new_count, update_count = db_instance.save_alphas(alphas)
            append_detail(task_id, f"同步完成: 新增 {new_count} 个, 更新 {update_count} 个")
        
        # ===== 步骤3: 筛选候选 =====
        if is_stopped(task_id):
            update_task(task_id, status="stopped")
            return
        
        append_detail(task_id, "步骤 3/4: 筛选候选")
        update_task(task_id, progress=0.65)
        
        db_instance.update_candidate_pool()
        candidates = db_instance.get_candidates()
        
        min_sharpe = config.get("min_sharpe", 1.25)
        min_fitness = config.get("min_fitness", 1.0)
        max_turnover = config.get("max_turnover", 0.70)
        
        # 筛选符合条件的
        filtered = [
            c for c in candidates
            if (c.get('sharpe', 0) >= min_sharpe and
                c.get('fitness', 0) >= min_fitness and
                c.get('turnover', 1) <= max_turnover)
        ]
        
        append_detail(task_id, f"筛选出 {len(filtered)} 个候选 Alpha")
        
        # ===== 步骤4: 提交 =====
        if is_stopped(task_id):
            update_task(task_id, status="stopped")
            return
        
        append_detail(task_id, "步骤 4/4: 提交 Alpha")
        update_task(task_id, progress=0.75)
        
        num_to_submit = config.get("num_to_submit", 10)
        submit_candidates = filtered[:num_to_submit]
        
        if submit_candidates:
            alpha_id_file = str(PROJECT_ROOT / "data" / "alphas" / "workflow_alpha_ids.txt")
            with open(alpha_id_file, 'w', encoding='utf-8') as f:
                for c in submit_candidates:
                    f.write(c['alpha_id'] + '\n')
            
            append_detail(task_id, f"开始提交 {len(submit_candidates)} 个 Alpha")
            
            # 使用 submit_alpha_ids
            result = submit_alpha_ids(alpha_id_file, num_to_submit=len(submit_candidates))
            
            append_detail(task_id, f"提交完成: {result['success']} 成功, {result['failed']} 失败, {result['skipped_429']} 限流")
            update_task(task_id, progress=0.95)
        else:
            append_detail(task_id, "没有符合条件的 Alpha 可提交")
        
        # 完成
        update_task(task_id, status="completed", progress=1.0)
        append_detail(task_id, "✅ 一键工作流完成")
        
        client.session.close()
        
    except Exception as e:
        import traceback
        error_msg = f"工作流执行失败: {str(e)}"
        append_detail(task_id, f"❌ {error_msg}")
        update_task(task_id, status="failed", error=error_msg)
        traceback.print_exc()
