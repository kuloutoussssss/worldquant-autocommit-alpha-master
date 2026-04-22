# -*- coding: utf-8 -*-
"""
任务进度管理器
功能：保存和恢复任务进度，支持断点续传
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime
from threading import Lock

class TaskProgress:
    """任务进度数据"""
    def __init__(self, task_id: str, task_type: str, total: int):
        self.task_id = task_id
        self.task_type = task_type
        self.total = total
        self.completed = 0
        self.failed = 0
        self.current_index = 0  # 当前处理到第几个
        self.processed_ids = []  # 已处理的ID列表
        self.last_update = datetime.now().isoformat()
        self.start_time = datetime.now().isoformat()
        self.progress_file = None
        
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "current_index": self.current_index,
            "processed_ids": self.processed_ids,
            "last_update": self.last_update,
            "start_time": self.start_time
        }
        
    @classmethod
    def from_dict(cls, data: dict):
        p = cls(data["task_id"], data["task_type"], data["total"])
        p.completed = data.get("completed", 0)
        p.failed = data.get("failed", 0)
        p.current_index = data.get("current_index", 0)
        p.processed_ids = data.get("processed_ids", [])
        p.last_update = data.get("last_update", "")
        p.start_time = data.get("start_time", "")
        return p


class TaskProgressManager:
    """任务进度管理器（单例）"""
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.progress_dir = Path("data/task_progress")
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}  # 内存缓存
        self._cache_lock = Lock()
        
    def _get_progress_file(self, task_id: str) -> Path:
        """获取进度文件路径"""
        return self.progress_dir / f"{task_id}.json"
    
    def save_progress(self, progress: TaskProgress):
        """保存进度到文件"""
        with self._cache_lock:
            self._cache[progress.task_id] = progress
        
        progress.last_update = datetime.now().isoformat()
        file_path = self._get_progress_file(progress.task_id)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(progress.to_dict(), f, ensure_ascii=False, indent=2)
        
        return file_path
    
    def load_progress(self, task_id: str) -> TaskProgress:
        """从文件加载进度"""
        with self._cache_lock:
            if task_id in self._cache:
                return self._cache[task_id]
        
        file_path = self._get_progress_file(task_id)
        if not file_path.exists():
            return None
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        progress = TaskProgress.from_dict(data)
        
        with self._cache_lock:
            self._cache[task_id] = progress
        
        return progress
    
    def delete_progress(self, task_id: str):
        """删除进度文件"""
        with self._cache_lock:
            if task_id in self._cache:
                del self._cache[task_id]
        
        file_path = self._get_progress_file(task_id)
        if file_path.exists():
            file_path.unlink()
    
    def is_processed(self, task_id: str, item_id: str) -> bool:
        """检查是否已处理"""
        progress = self.load_progress(task_id)
        if progress:
            return item_id in progress.processed_ids
        return False
    
    def mark_processed(self, task_id: str, item_id: str, success: bool = True):
        """标记已处理"""
        progress = self.load_progress(task_id)
        if not progress:
            return
        
        if item_id not in progress.processed_ids:
            progress.processed_ids.append(item_id)
            progress.current_index += 1
            if success:
                progress.completed += 1
            else:
                progress.failed += 1
            self.save_progress(progress)
    
    def get_pending_ids(self, task_id: str, all_ids: list) -> list:
        """获取未处理的ID列表"""
        progress = self.load_progress(task_id)
        if not progress:
            return all_ids
        
        pending = [id for id in all_ids if id not in progress.processed_ids]
        return pending
    
    def get_all_progress_files(self) -> list:
        """获取所有进度文件"""
        if not self.progress_dir.exists():
            return []
        return list(self.progress_dir.glob("*.json"))
    
    def load_all_progress(self) -> list:
        """加载所有进度"""
        progress_list = []
        for file_path in self.get_all_progress_files():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                progress_list.append(TaskProgress.from_dict(data))
            except Exception as e:
                print(f"加载进度文件失败 {file_path}: {e}")
        return progress_list
    
    def clear_completed(self, task_id: str):
        """清除已完成任务的进度"""
        progress = self.load_progress(task_id)
        if progress and progress.completed + progress.failed >= progress.total:
            self.delete_progress(task_id)


# 全局实例
_progress_manager = None

def get_progress_manager() -> TaskProgressManager:
    """获取进度管理器单例"""
    global _progress_manager
    if _progress_manager is None:
        _progress_manager = TaskProgressManager()
    return _progress_manager
