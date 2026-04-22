# -*- coding: utf-8 -*-
"""
简化版 API 服务器 - 已禁用
注意：此文件已合并到 api_server.py，请勿单独运行
"""

# 本文件已弃用，所有功能已移至 api_server.py
import json
import time
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from pathlib import Path

# 项目路径
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

# 任务存储
TASKS_FILE = project_root / "data" / "tasks.json"
_tasks = []

def load_tasks():
    global _tasks
    if TASKS_FILE.exists():
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                _tasks = json.load(f)
        except:
            _tasks = []

def save_tasks():
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(_tasks, f, ensure_ascii=False, indent=2)

load_tasks()

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/health':
            running = len([t for t in _tasks if t.get("status") == "running"])
            self.send_json({
                "success": True,
                "status": "healthy",
                "running_tasks": running,
                "total_tasks": len(_tasks)
            })
        elif parsed.path == '/api/tasks':
            tasks = sorted(_tasks, key=lambda x: x.get("started_at", ""), reverse=True)[:50]
            self.send_json({"success": True, "tasks": tasks})
        elif parsed.path.startswith('/api/tasks/'):
            task_id = parsed.path.split('/')[-1]
            for task in _tasks:
                if task["id"] == task_id:
                    self.send_json({"success": True, "task": task})
                    return
            self.send_json({"success": False, "error": "Task not found"}, 404)
        else:
            self.send_json({"error": "Not found"}, 404)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
        
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}
        
        print(f"POST {parsed.path}: {data}")
        
        if parsed.path == '/api/tasks/stop-all':
            for task in _tasks:
                if task["status"] == "running":
                    task["status"] = "stopped"
                    task["finished_at"] = datetime.now().isoformat()
            save_tasks()
            self.send_json({"success": True})
        
        elif parsed.path == '/api/backtest/start':
            untested_data = data.get('data', [])
            params = data.get('params', {})
            
            if not untested_data:
                self.send_json({"success": False, "error": "没有待回测数据"}, 400)
                return
            
            task_id = f"backtest_{int(time.time() * 1000)}"
            task = {
                "id": task_id,
                "type": "backtest",
                "description": f"回测 {len(untested_data)} 个 Alpha",
                "status": "running",
                "progress": 0.0,
                "total": len(untested_data),
                "completed": 0,
                "failed": 0,
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
                "error": None,
                "details": [{"time": datetime.now().strftime("%H:%M:%S"), "message": "任务已创建"}]
            }
            _tasks.append(task)
            save_tasks()
            
            # 启动子进程
            temp_path = os.path.join(str(project_root), 'data', f'task_{task_id}.json')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'task_id': task_id,
                    'data': untested_data,
                    'params': params
                }, f, ensure_ascii=False)
            
            python_exe = sys.executable
            script_path = str(project_root / "web" / "api" / "backtest_executor.py")
            
            if sys.platform == 'win32':
                cmd = f'start cmd /C "cd /D {project_root} && {python_exe} {script_path} {temp_path}"'
                print(f"执行: {cmd}")
                os.system(cmd)
            
            self.send_json({"success": True, "task_id": task_id})
        
        else:
            self.send_json({"error": "Not found"}, 404)

def run_server(port=5000):
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    print(f"API 服务器启动在 http://0.0.0.0:{port}")
    server.serve_forever()

if __name__ == '__main__':
    run_server()
