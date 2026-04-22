# -*- coding: utf-8 -*-
"""
提交任务执行器 - 后台运行
"""
import sys
import json
import time
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from core.api_client import BrainAPIClient
from core.db_manager import get_database
from core.submit import _retry_submit_with_backoff, MAX_SUBMIT_RETRIES, SUBMIT_INITIAL_DELAY, SUBMIT_BACKOFF_FACTOR
from web.api.tasks import load_tasks, save_tasks


def update_task_progress(task_id: str, completed: int, failed: int, message: str):
    """更新任务进度"""
    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            task["completed"] = completed
            task["failed"] = failed
            total = task.get("total", 1)
            task["progress"] = completed / total if total > 0 else 1.0
            task["details"].append({
                "time": time.strftime("%H:%M:%S"),
                "message": message
            })
            # 保持最近 100 条
            if len(task["details"]) > 100:
                task["details"] = task["details"][-100:]
            save_tasks(tasks)
            break


def update_task_result(task_id: str, result: dict, status: str = "running"):
    """更新任务结果"""
    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            task["result"] = result
            task["status"] = status
            if status in ["completed", "failed"]:
                task["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_tasks(tasks)
            break


def run_submit(task_id: str, target_success: int, alpha_ids: list):
    """执行提交任务"""
    print(f"[Submit Executor] Task {task_id} started")
    print(f"[Submit Executor] Target: {target_success} successful, Total: {len(alpha_ids)}")
    
    db = get_database()
    client = BrainAPIClient()
    
    successful = []
    failed = []
    skipped_429 = []
    
    try:
        for i, alpha_id in enumerate(alpha_ids, 1):
            # 检查是否已达到目标
            if len(successful) >= target_success:
                msg = f"[OK] 达到目标 ({len(successful)}/{target_success})，停止提交"
                print(f"[Submit Executor] {msg}")
                update_task_progress(task_id, len(successful), len(failed), msg)
                break
            
            msg = f"[{i}/{len(alpha_ids)}] {alpha_id} (成功: {len(successful)}/{target_success})"
            print(msg)
            update_task_progress(task_id, i, len(failed), msg)
            
            # 使用指数退避重试
            result = _retry_submit_with_backoff(client, alpha_id, i)
            
            if result['success']:
                msg = f"  [OK] 成功: {alpha_id}"
                print(msg)
                update_task_progress(task_id, i, len(failed), msg)
                successful.append(alpha_id)
                db.mark_submitted(alpha_id)
            elif result['is_429']:
                msg = f"  [429] 限流超过最大重试: {alpha_id}"
                print(msg)
                update_task_progress(task_id, i, len(failed), msg)
                skipped_429.append(alpha_id)
            else:
                error = result['error']
                msg = f"  [FAIL] 失败: {error}"
                print(msg)
                update_task_progress(task_id, i, len(failed), msg)
                failed.append(alpha_id)
                db.mark_submit_failed(alpha_id, error)
            
            # 请求间隔
            if i < len(alpha_ids) and len(successful) < target_success:
                time.sleep(1)
        
        # 任务完成
        status = "completed" if successful else "failed"
        msg = f"提交完成: {len(successful)} 成功, {len(failed)} 失败, {len(skipped_429)} 429限流"
        print(f"[Submit Executor] {msg}")
        
        update_task_result(task_id, {
            "success": successful,
            "failed": failed,
            "skipped_429": skipped_429,
            "total": len(alpha_ids)
        }, status)
        
    except Exception as e:
        print(f"[Submit Executor] Error: {e}")
        update_task_result(task_id, {
            "success": successful,
            "failed": failed,
            "skipped_429": skipped_429,
            "total": len(alpha_ids),
            "error": str(e)
        }, "failed")
    finally:
        client.session.close()
        print(f"[Submit Executor] Task {task_id} finished")


def main():
    if len(sys.argv) < 2:
        print("[Submit Executor] Usage: python submit_executor.py <param_file.json>")
        sys.exit(1)
    
    param_file = Path(sys.argv[1])
    if not param_file.exists():
        print(f"[Submit Executor] Param file not found: {param_file}")
        sys.exit(1)
    
    with open(param_file, 'r', encoding='utf-8') as f:
        params = json.load(f)
    
    task_id = params["task_id"]
    target_success = params["target_success"]
    alpha_ids = params["alpha_ids"]
    
    run_submit(task_id, target_success, alpha_ids)
    
    # 删除参数文件
    param_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
