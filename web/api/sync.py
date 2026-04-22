# -*- coding: utf-8 -*-
"""
Sync API - 与 Flask api_server.py 保持一致的同步逻辑
"""
import sys
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks

from web.config import get_settings, PROJECT_ROOT
from web.api.schemas import SyncResponse

router = APIRouter()
settings = get_settings()


@router.post("/incremental", response_model=SyncResponse)
async def sync_incremental():
    """增量同步 - 后台执行"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.api_client import BrainAPIClient
    from core.db_manager import get_database
    
    client = BrainAPIClient()
    db = get_database()
    
    if not client.ensure_session():
        return SyncResponse(
            success=False,
            message="认证失败",
            new_count=0,
            update_count=0,
            total=0
        )
    
    # 获取上次同步时间
    last_sync = db.get_last_sync_time()
    
    if last_sync:
        alphas = client.get_updated_alphas(
            since=last_sync,
            min_sharpe=-999,
            min_fitness=-999,
            max_turnover=1e9
        )
    else:
        # 首次同步，获取所有
        alphas = client.get_all_user_alphas(
            min_sharpe=-999,
            min_fitness=-999,
            max_turnover=1e9
        )
    
    new_count = 0
    update_count = 0
    
    if alphas:
        new_count, update_count = db.save_alphas(alphas, is_full_sync=not last_sync)
        db.update_candidate_pool()
    
    client.session.close()
    
    return SyncResponse(
        success=True,
        message=f"增量同步完成: 新增{new_count}个, 更新{update_count}个",
        new_count=new_count,
        update_count=update_count,
        total=len(alphas)
    )


@router.post("/full", response_model=SyncResponse)
async def sync_full(background_tasks: BackgroundTasks):
    """全量同步 - 后台执行"""
    import threading
    
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from web.api.tasks import load_tasks, save_tasks
    import time
    
    # 创建同步任务
    task_id = f"sync_full_{int(time.time() * 1000)}"
    tasks = load_tasks()
    
    task = {
        "id": task_id,
        "name": "全量同步",
        "type": "sync",
        "status": "running",
        "progress": 0.0,
        "total": 1,
        "completed": 0,
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [{"time": datetime.now().strftime("%H:%M:%S"), "message": "全量同步开始..."}]
    }
    tasks.append(task)
    save_tasks(tasks)
    
    # 在新线程中执行后台任务
    thread = threading.Thread(target=_run_sync_full, args=(task_id,), daemon=True)
    thread.start()
    
    return SyncResponse(
        success=True,
        message=f"全量同步任务已启动: {task_id}",
        new_count=0,
        update_count=0,
        total=0
    )


def _run_sync_full(task_id: str):
    """后台执行全量同步"""
    import traceback
    import threading
    
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.api_client import BrainAPIClient
    from core.db_manager import get_database
    from web.api.tasks import load_tasks, save_tasks
    
    def _update_task_detail(tasks_list, tid, msg):
        """安全更新任务详情"""
        for t in tasks_list:
            if t["id"] == tid:
                t["details"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": msg})
                break
    
    def _update_task_status(tasks_list, tid, status, error=None):
        """安全更新任务状态"""
        for t in tasks_list:
            if t["id"] == tid:
                t["status"] = status
                if error:
                    t["error"] = str(error)
                if status in ["completed", "failed", "stopped"]:
                    t["finished_at"] = datetime.now().isoformat()
                break
    
    client = None
    db = None
    
    try:
        print(f"[SYNC] 任务 {task_id} 开始执行")
        
        # 更新任务状态
        tasks = load_tasks()
        _update_task_detail(tasks, task_id, "正在初始化客户端...")
        save_tasks(tasks)
        
        client = BrainAPIClient()
        db = get_database()
        
        tasks = load_tasks()
        _update_task_detail(tasks, task_id, "正在认证...")
        save_tasks(tasks)
        
        if not client.ensure_session():
            tasks = load_tasks()
            _update_task_status(tasks, task_id, "failed", "认证失败")
            save_tasks(tasks)
            print(f"[SYNC] 任务 {task_id} 认证失败")
            return
        
        tasks = load_tasks()
        _update_task_detail(tasks, task_id, "正在获取所有 Alpha (这可能需要几分钟...)")
        save_tasks(tasks)
        print(f"[SYNC] 任务 {task_id} 开始获取 Alpha")
        
        # 获取所有 Alpha
        alphas = client.get_all_user_alphas(
            min_sharpe=-999,
            min_fitness=-999,
            max_turnover=1e9
        )
        
        print(f"[SYNC] 任务 {task_id} 获取到 {len(alphas)} 个 Alpha")
        
        tasks = load_tasks()
        _update_task_detail(tasks, task_id, f"获取完成，共 {len(alphas)} 个 Alpha，正在保存...")
        save_tasks(tasks)
        
        if alphas:
            # 保存
            new_count, update_count = db.save_alphas(alphas, is_full_sync=True)
            db.update_candidate_pool()
            
            tasks = load_tasks()
            _update_task_detail(tasks, task_id, f"保存完成: 新增{new_count}, 更新{update_count}")
            _update_task_status(tasks, task_id, "completed")
            save_tasks(tasks)
            print(f"[SYNC] 任务 {task_id} 完成: 新增{new_count}, 更新{update_count}")
        else:
            tasks = load_tasks()
            _update_task_detail(tasks, task_id, "没有获取到 Alpha")
            _update_task_status(tasks, task_id, "completed")
            save_tasks(tasks)
            print(f"[SYNC] 任务 {task_id} 没有获取到 Alpha")
        
        if client:
            client.session.close()
        
    except Exception as e:
        error_msg = str(e)
        print(f"[SYNC] 任务 {task_id} 错误: {error_msg}")
        traceback.print_exc()
        try:
            tasks = load_tasks()
            _update_task_detail(tasks, task_id, f"错误: {error_msg}")
            _update_task_status(tasks, task_id, "failed", error_msg)
            save_tasks(tasks)
        except:
            pass
