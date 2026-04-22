# -*- coding: utf-8 -*-
"""
任务管理器
功能：管理后台运行的任务（回测、提交等），支持通过文件状态停止
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class TaskManager:
    """任务管理器单例"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 任务文件路径 - 使用绝对路径确保多进程一致
        base_path = Path(__file__).parent.parent.parent.absolute()
        self.tasks_file = base_path / "data" / "tasks.json"
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._initialized = True
    
    def _load_tasks(self) -> List[Dict]:
        """加载任务列表"""
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_tasks(self, tasks: List[Dict]):
        """保存任务列表"""
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    def create_task(self, task_type: str, description: str, total: int = 0) -> str:
        """创建新任务"""
        tasks = self._load_tasks()
        
        task_id = f"{task_type}_{int(time.time() * 1000)}"
        
        task = {
            "id": task_id,
            "type": task_type,
            "description": description,
            "status": "running",
            "progress": 0.0,
            "total": total,
            "completed": 0,
            "failed": 0,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "error": None,
            "details": []
        }
        
        tasks.append(task)
        self._save_tasks(tasks)
        
        return task_id
    
    def update_task(self, task_id: str, **kwargs):
        """更新任务状态"""
        tasks = self._load_tasks()
        
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
        
        self._save_tasks(tasks)
    
    def append_detail(self, task_id: str, detail: str):
        """追加任务详情"""
        tasks = self._load_tasks()
        
        for task in tasks:
            if task["id"] == task_id:
                task["details"].append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": detail
                })
                if len(task["details"]) > 100:
                    task["details"] = task["details"][-100:]
                break
        
        self._save_tasks(tasks)
    
    def stop_task(self, task_id: str) -> bool:
        """停止任务 - 更新文件状态为 stopped"""
        tasks = self._load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                task["status"] = "stopped"
                task["finished_at"] = datetime.now().isoformat()
                self._save_tasks(tasks)
                return True
        return False
    
    def is_task_stopped(self, task_id: str) -> bool:
        """检查任务是否被请求停止"""
        tasks = self._load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                return task.get("status") == "stopped"
        return True
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务信息"""
        tasks = self._load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                return task
        return None
    
    def get_running_tasks(self) -> List[Dict]:
        """获取所有运行中的任务"""
        tasks = self._load_tasks()
        return [t for t in tasks if t["status"] == "running"]
    
    def get_all_tasks(self, limit: int = 50) -> List[Dict]:
        """获取所有任务"""
        tasks = self._load_tasks()
        return sorted(tasks, key=lambda x: x.get("started_at", ""), reverse=True)[:limit]
    
    def remove_task(self, task_id: str):
        """删除任务"""
        tasks = self._load_tasks()
        tasks = [t for t in tasks if t["id"] != task_id]
        self._save_tasks(tasks)
    
    def clear_finished_tasks(self):
        """清理已完成的任务"""
        tasks = self._load_tasks()
        tasks = [t for t in tasks if t["status"] == "running"]
        self._save_tasks(tasks)


# 全局单例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取任务管理器单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


# ========== 后台回测进程函数 ==========

def _run_backtest_in_process(task_id: str, untested_data: list, params: dict, db_path: str, tasks_file: str):
    """后台回测进程函数
    
    Args:
        task_id: 任务ID
        untested_data: 待回测数据
        params: 回测参数
        db_path: 数据库路径
        tasks_file: 任务文件路径（绝对路径）
    """
    import sys
    import os
    
    # 添加项目路径
    project_root = Path(__file__).parent.parent.parent.absolute()
    sys.path.insert(0, str(project_root))
    
    # 导入必要的模块
    from core.api_client import BrainAPIClient
    from core.db_manager import AlphaDatabase
    from web.utils.helpers import load_to_test_alphas, save_to_test_alphas
    
    # 直接操作任务文件，不使用单例
    tasks_file_path = Path(tasks_file)
    
    def load_tasks():
        if tasks_file_path.exists():
            try:
                with open(tasks_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_tasks(tasks):
        with open(tasks_file_path, 'w', encoding='utf-8') as f:
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
    
    try:
        db = AlphaDatabase(db_path)
    except Exception as e:
        update_task(task_id, status="failed", error=f"数据库初始化失败: {e}")
        return
    
    client = BrainAPIClient()
    
    if not client.ensure_session():
        update_task(task_id, status="failed", error="认证失败")
        return
    
    completed = 0
    failed = 0
    total = len(untested_data)
    
    for i, (idx, expression) in enumerate(untested_data):
        # 每次循环都检查停止信号
        if is_stopped(task_id):
            append_detail(task_id, "任务已停止")
            update_task(task_id, status="stopped")
            return
        
        parts = expression.split("|")
        expr = parts[0].strip()
        p_universe = parts[1].strip() if len(parts) > 1 else params.get("universe")
        p_decay = int(parts[2].strip()) if len(parts) > 2 else params.get("decay", 30)
        p_neutralization = parts[3].strip() if len(parts) > 3 else params.get("neutralization")
        p_truncation = float(parts[4].strip()) if len(parts) > 4 else params.get("truncation", 0.08)
        
        status_msg = f"回测 [{completed + failed + 1}/{total}] #{idx}: {expr[:50]}..."
        update_task(task_id, progress=(completed + failed) / total, completed=completed, failed=failed)
        append_detail(task_id, status_msg)
        
        # 检查停止信号
        if is_stopped(task_id):
            append_detail(task_id, "任务已停止")
            update_task(task_id, status="stopped")
            return
        
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
                append_detail(task_id, f"✅ 成功: {expr[:30]}...")
            else:
                failed += 1
                append_detail(task_id, f"❌ 回测失败")
        else:
            failed += 1
            append_detail(task_id, f"❌ 提交失败")
        
        update_task(task_id, progress=(completed + failed) / total, completed=completed, failed=failed)
        
        # 检查停止信号
        if is_stopped(task_id):
            append_detail(task_id, "任务已停止")
            update_task(task_id, status="stopped")
            return
        
        import time as time_module
        time_module.sleep(1.0)
    
    # 任务完成
    if not is_stopped(task_id):
        update_task(task_id, status="completed", progress=1.0)


if __name__ == "__main__":
    pass
