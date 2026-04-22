# -*- coding: utf-8 -*-
"""
任务管理 API
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from web.config import get_settings
from web.api.schemas import TaskResponse, TaskListResponse, TaskCreateRequest, TaskUpdateRequest
from web.utils.exceptions import TaskNotFoundError

router = APIRouter()

settings = get_settings()


def load_tasks() -> List[dict]:
    """加载任务列表"""
    if settings.TASKS_FILE.exists():
        try:
            with open(settings.TASKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_tasks(tasks: List[dict]):
    """保存任务列表"""
    settings.TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


@router.get("/", response_model=TaskListResponse)
async def get_tasks(limit: int = 50):
    """获取任务列表"""
    tasks = load_tasks()
    sorted_tasks = sorted(tasks, key=lambda x: x.get("started_at", ""), reverse=True)[:limit]
    return TaskListResponse(
        tasks=[TaskResponse(**task) for task in sorted_tasks]
    )


@router.get("/running")
async def get_running_tasks():
    """获取运行中的任务"""
    tasks = load_tasks()
    running = [t for t in tasks if t.get("status") == "running"]
    return {"success": True, "tasks": running}


@router.post("/stop-all")
async def stop_all_tasks():
    """停止所有运行中的任务"""
    tasks = load_tasks()
    stopped = 0
    for task in tasks:
        if task.get("status") == "running":
            task["status"] = "stopped"
            task["finished_at"] = datetime.now().isoformat()
            stopped += 1
    if stopped > 0:
        save_tasks(tasks)
    return {"success": True, "message": f"Stopped {stopped} tasks"}


@router.post("/clear")
async def clear_completed_tasks():
    """清除已完成的任务（completed/stopped/failed）"""
    tasks = load_tasks()
    original_len = len(tasks)
    tasks = [t for t in tasks if t.get("status") not in ["completed", "stopped", "failed"]]
    cleared = original_len - len(tasks)
    if cleared > 0:
        save_tasks(tasks)
    return {"success": True, "message": f"Cleared {cleared} tasks"}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取单个任务"""
    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            return {"success": True, "task": task}
    raise TaskNotFoundError(task_id)


@router.post("/")
async def create_task(request: TaskCreateRequest):
    """创建新任务"""
    tasks = load_tasks()
    
    # 生成任务 ID
    task_id = f"{request.type}_{int(time.time() * 1000)}"
    
    new_task = {
        "id": task_id,
        "name": request.name,
        "type": request.type,
        "status": "pending",
        "progress": 0,
        "completed": 0,
        "total": 0,
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [],
        "params": request.params
    }
    
    tasks.append(new_task)
    save_tasks(tasks)
    
    return {"success": True, "task_id": task_id, "task": new_task}


@router.put("/{task_id}")
async def update_task(task_id: str, request: TaskUpdateRequest):
    """更新任务状态"""
    tasks = load_tasks()
    
    for task in tasks:
        if task.get("id") == task_id:
            if request.status is not None:
                task["status"] = request.status
            if request.progress is not None:
                task["progress"] = request.progress
            if request.error is not None:
                task["error"] = request.error
            
            if task["status"] in ["completed", "stopped", "failed"]:
                task["finished_at"] = datetime.now().isoformat()
            
            save_tasks(tasks)
            return {"success": True, "task": task}
    
    raise TaskNotFoundError(task_id)


@router.post("/{task_id}/detail")
async def append_detail(task_id: str, detail: str):
    """追加任务详情"""
    tasks = load_tasks()
    
    for task in tasks:
        if task.get("id") == task_id:
            task["details"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": detail
            })
            # 保持最近 100 条
            if len(task["details"]) > 100:
                task["details"] = task["details"][-100:]
            save_tasks(tasks)
            return {"success": True}
    
    raise TaskNotFoundError(task_id)


@router.post("/{task_id}/stop")
async def stop_task(task_id: str):
    """停止任务"""
    tasks = load_tasks()
    
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "stopped"
            task["finished_at"] = datetime.now().isoformat()
            save_tasks(tasks)
            return {"success": True, "message": f"Task {task_id} stopped"}
    
    raise TaskNotFoundError(task_id)


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    tasks = load_tasks()
    original_len = len(tasks)
    
    tasks = [t for t in tasks if t.get("id") != task_id]
    
    if len(tasks) == original_len:
        raise TaskNotFoundError(task_id)
    
    save_tasks(tasks)
    return {"success": True, "message": f"Task {task_id} deleted"}
