# -*- coding: utf-8 -*-
"""
Submit API - 异步任务模式
"""
import sys
import json
import time
import subprocess
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException

from web.config import get_settings, PROJECT_ROOT
from web.api.schemas import SubmitRequest, SubmitResponse, SubmitResult
from web.api.tasks import load_tasks, save_tasks
from web.utils.exceptions import APIException

router = APIRouter()
settings = get_settings()


@router.post("/alpha", response_model=SubmitResponse)
async def submit_single_alpha(alpha_id: str):
    """Submit single Alpha"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.api_client import BrainAPIClient
    from core.db_manager import get_database
    
    client = BrainAPIClient()
    result = client.submit_alpha(alpha_id)
    client.session.close()
    
    if result and result.get('status') == 'OK':
        db = get_database()
        db.mark_submitted(alpha_id)
        return SubmitResponse(
            success=True,
            message="Alpha submitted successfully",
            result=SubmitResult(
                success=[alpha_id],
                failed=[],
                skipped_429=[],
                total=1
            )
        )
    else:
        error = result.get('error', 'Unknown error') if result else 'No response'
        return SubmitResponse(
            success=False,
            message=f"Failed to submit: {error}",
            result=SubmitResult(
                success=[],
                failed=[alpha_id],
                skipped_429=[],
                total=1
            )
        )


@router.post("", response_model=SubmitResponse)
@router.post("/", response_model=SubmitResponse)
async def submit_batch(request: SubmitRequest, background_tasks: BackgroundTasks):
    """提交任务 - 立即返回 task_id，后台执行"""
    sys.path.insert(0, str(PROJECT_ROOT))
    from web.utils.helpers import get_db
    
    db = get_db()
    
    # 获取候选池
    if request.alpha_ids:
        alpha_ids = request.alpha_ids
    else:
        candidates, total = db.get_candidates()
        alpha_ids = [c['alpha_id'] for c in candidates]
    
    if not alpha_ids:
        raise APIException(message="No alphas to submit", code="NO_CANDIDATES")
    
    # 创建任务
    task_id = f"submit_{int(time.time() * 1000)}"
    tasks = load_tasks()
    
    task = {
        "id": task_id,
        "name": f"Submit {min(request.target_success, len(alpha_ids))} Alphas",
        "type": "submit",
        "status": "running",
        "progress": 0,
        "completed": 0,
        "total": len(alpha_ids),
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [{"time": datetime.now().strftime("%H:%M:%S"), "message": "提交任务已启动..."}],
        "params": {
            "target_success": request.target_success,
            "alpha_ids": alpha_ids
        },
        "result": {
            "success": [],
            "failed": [],
            "skipped_429": []
        }
    }
    
    tasks.append(task)
    save_tasks(tasks)
    
    # 启动后台进程执行
    executor_path = PROJECT_ROOT / "web" / "api" / "submit_executor.py"
    param_file = PROJECT_ROOT / "data" / f"submit_{task_id}.json"
    
    with open(param_file, 'w', encoding='utf-8') as f:
        json.dump({
            "task_id": task_id,
            "target_success": request.target_success,
            "alpha_ids": alpha_ids
        }, f, ensure_ascii=False)
    
    python_exe = sys.executable
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"submit_{task_id}.log"
    
    with open(log_file, 'w', encoding='utf-8') as stdout_file:
        subprocess.Popen(
            [python_exe, str(executor_path), str(param_file)],
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            stdout=stdout_file,
            stderr=subprocess.STDOUT
        )
    
    return SubmitResponse(
        success=True,
        message=f"提交任务已启动，请在任务列表查看进度",
        result=SubmitResult(
            success=[],
            failed=[],
            skipped_429=[],
            total=len(alpha_ids)
        )
    )


@router.get("/candidates")
async def get_candidates():
    """Get candidate pool"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.db_manager import get_database
    
    db = get_database()
    db.update_candidate_pool()
    candidates, total = db.get_candidates()
    
    return {
        "success": True,
        "total": total,
        "available": len(candidates),
        "candidates": candidates
    }


@router.get("/pool")
async def get_pool_status():
    """Get submission pool status"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.db_manager import get_database
    
    db = get_database()
    
    # Count statuses
    with db._get_connection() as conn:
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN submitted_at IS NOT NULL THEN 1 ELSE 0 END) as submitted,
                SUM(CASE WHEN checks_passed = 1 AND submitted_at IS NULL THEN 1 ELSE 0 END) as available,
                SUM(CASE WHEN submit_fail_count >= 3 THEN 1 ELSE 0 END) as failed
            FROM alphas
            WHERE sharpe >= 1.25 AND fitness >= 1.0 AND turnover <= 0.70
        """)
        row = cursor.fetchone()
    
    return {
        "success": True,
        "total": row[0] or 0,
        "submitted": row[1] or 0,
        "available": row[2] or 0,
        "failed": row[3] or 0
    }
