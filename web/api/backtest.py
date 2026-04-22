# -*- coding: utf-8 -*-
"""
Backtest API
"""
import json
import subprocess
import time
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from web.config import get_settings, PROJECT_ROOT
from web.api.schemas import BacktestRequest, BacktestResponse
from web.api.tasks import load_tasks, save_tasks

router = APIRouter()
settings = get_settings()


@router.post("/start", response_model=BacktestResponse)
async def start_backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    """Start backtest task"""
    sys.path.insert(0, str(PROJECT_ROOT))
    from web.utils.helpers import load_to_test_alphas, save_to_test_alphas
    
    # 使用请求中的 alphas 或从文件加载
    if request.data:
        alphas = request.data
        input_file = None  # 内存数据不删除
    else:
        alphas = load_to_test_alphas()
        input_file = str(settings.DATA_DIR / "alphas" / "to_test.txt")  # 待回测文件
    
    if not alphas:
        raise HTTPException(status_code=400, detail="No alphas to test")
    
    if request.max_count:
        alphas = alphas[:request.max_count]
    
    task_id = f"backtest_{int(time.time() * 1000)}"
    tasks = load_tasks()
    
    # 获取回测参数（如果没有提供，使用默认值）
    bt_params = request.params
    if bt_params is None:
        from web.api.schemas import BacktestParams
        bt_params = BacktestParams()
    
    task = {
        "id": task_id,
        "name": f"Backtest {len(alphas)} Alphas",
        "type": "backtest",
        "status": "running",
        "progress": 0,
        "completed": 0,
        "total": len(alphas),
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [],
        "params": {
            "universe": bt_params.universe,
            "region": bt_params.region,
            "decay": bt_params.decay,
            "neutralization": bt_params.neutralization,
            "truncation": bt_params.truncation,
            "test_period": bt_params.test_period,
            "delay": bt_params.delay,
            "auto_retry": bt_params.auto_retry,
            "concurrency": bt_params.concurrency,  # 新增
            "request_delay": bt_params.request_delay  # 新增
        }
    }
    
    tasks.append(task)
    save_tasks(tasks)
    
    executor_path = PROJECT_ROOT / "web" / "api" / "backtest_executor.py"
    param_file = PROJECT_ROOT / "data" / f"params_{task_id}.json"
    with open(param_file, 'w', encoding='utf-8') as f:
        json.dump({
            "task_id": task_id,
            "data": alphas,
            "input_file": input_file,  # 成功时从该文件删除
            "params": {
                "universe": bt_params.universe,
                "region": bt_params.region,
                "decay": bt_params.decay,
                "neutralization": bt_params.neutralization,
                "truncation": bt_params.truncation,
                "test_period": bt_params.test_period,
                "delay": bt_params.delay,
                "auto_retry": bt_params.auto_retry,
                "concurrency": bt_params.concurrency,  # 新增
                "request_delay": bt_params.request_delay  # 新增
            }
        }, f, ensure_ascii=False)
    
    python_exe = sys.executable
    # 输出到日志文件以便调试
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"backtest_{task_id}.log"
    
    with open(log_file, 'w', encoding='utf-8') as stdout_file:
        subprocess.Popen(
            [python_exe, str(executor_path), str(param_file)],
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            stdout=stdout_file,
            stderr=subprocess.STDOUT
        )
    
    return BacktestResponse(
        success=True,
        task_id=task_id,
        total=len(alphas),
        message=f"Backtest task started, {len(alphas)} Alphas"
    )


@router.get("/status/{task_id}")
async def get_backtest_status(task_id: str):
    """Get backtest task status"""
    tasks = load_tasks()
    
    for task in tasks:
        if task.get("id") == task_id and task.get("type") == "backtest":
            return {"success": True, "task": task}
    
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@router.post("/stop/{task_id}")
async def stop_backtest(task_id: str):
    """Stop backtest task"""
    tasks = load_tasks()
    
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "stopped"
            task["finished_at"] = datetime.now().isoformat()
            save_tasks(tasks)
            return {"success": True, "message": f"Task {task_id} stopped"}
    
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@router.get("/results")
async def get_backtest_results(limit: int = 100):
    """Get backtest results"""
    results_file = PROJECT_ROOT / "data" / "results" / "batch_results.json"
    
    if not results_file.exists():
        return {"success": True, "results": [], "total": 0}
    
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        results = data.get("results", [])[:limit]
        return {"success": True, "results": results, "total": data.get("total", len(results))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
