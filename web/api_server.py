# -*- coding: utf-8 -*-
"""
Flask API 服务器 - 基于 HTTP 服务器架构
功能：提供 REST API 管理后台任务
"""
import json
import time
import os
import sys
import sqlite3
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

# 项目路径
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

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

# ========== 任务管理 API ==========

@app.route('/api/health', methods=['GET'])
def health():
    running = len([t for t in _tasks if t.get("status") == "running"])
    return jsonify({
        "success": True,
        "status": "healthy",
        "running_tasks": running,
        "total_tasks": len(_tasks)
    })

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    limit = request.args.get('limit', 50, type=int)
    tasks = sorted(_tasks, key=lambda x: x.get("started_at", ""), reverse=True)[:limit]
    return jsonify({"success": True, "tasks": tasks})

@app.route('/api/tasks/running', methods=['GET'])
def get_running_tasks():
    running = [t for t in _tasks if t["status"] == "running"]
    return jsonify({"success": True, "tasks": running})

@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    for task in _tasks:
        if task["id"] == task_id:
            return jsonify({"success": True, "task": task})
    return jsonify({"success": False, "error": "Task not found"}), 404

@app.route('/api/tasks/<task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.json
    for task in _tasks:
        if task["id"] == task_id:
            for key, value in data.items():
                if key in ["progress", "completed", "failed", "status"]:
                    task[key] = value
                elif key == "error":
                    task["error"] = value
                elif key == "details":
                    task["details"] = value
            if task["status"] in ["completed", "stopped", "failed"]:
                task["finished_at"] = datetime.now().isoformat()
            save_tasks()
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Task not found"}), 404

@app.route('/api/tasks/<task_id>/detail', methods=['POST'])
def append_detail(task_id):
    data = request.json
    detail = data.get('detail', '')
    for task in _tasks:
        if task["id"] == task_id:
            task["details"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "message": detail
            })
            if len(task["details"]) > 100:
                task["details"] = task["details"][-100:]
            save_tasks()
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Task not found"}), 404

@app.route('/api/tasks/<task_id>/stop', methods=['POST'])
def stop_task(task_id):
    for task in _tasks:
        if task["id"] == task_id:
            task["status"] = "stopped"
            task["finished_at"] = datetime.now().isoformat()
            save_tasks()
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Task not found"}), 404

@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    global _tasks
    _tasks = [t for t in _tasks if t["id"] != task_id]
    save_tasks()
    return jsonify({"success": True})

@app.route('/api/tasks/stop-all', methods=['POST'])
def stop_all():
    for task in _tasks:
        if task["status"] == "running":
            task["status"] = "stopped"
            task["finished_at"] = datetime.now().isoformat()
    save_tasks()
    return jsonify({"success": True})

# ========== 回测 API ==========

def _start_backtest_process(task_id: str, untested_data: list, params: dict, resume: bool = False):
    """在新进程中启动回测任务"""
    try:
        # 保存参数到临时文件
        temp_path = os.path.join(str(project_root), 'data', f'task_{task_id}.json')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump({
                'task_id': task_id,
                'data': untested_data,
                'params': params,
                'resume': resume
            }, f, ensure_ascii=False)
        
        python_exe = sys.executable
        script_path = str(project_root / "web" / "api" / "backtest_executor.py")
        log_file = os.path.join(str(project_root), 'logs', f'backtest_{task_id}.log')
        
        # 使用 subprocess.Popen 启动子进程（跨平台兼容）
        print(f"[{task_id}] 启动子进程: {python_exe} {script_path} (resume={resume})")
        with open(log_file, 'w', encoding='utf-8') as log_f:
            subprocess.Popen(
                [python_exe, script_path, temp_path],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True if sys.platform != 'win32' else False,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == 'win32' else 0
            )
        
        print(f"[{task_id}] 子进程已启动，日志: {log_file}")
        
    except Exception as e:
        print(f"[{task_id}] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "failed"
                task["error"] = f"启动进程失败: {e}"
                task["finished_at"] = datetime.now().isoformat()
                break
        save_tasks()

@app.route('/api/backtest/start', methods=['POST'])
def start_backtest():
    """启动回测任务"""
    data = request.json
    untested_data = data.get('data', [])
    params = data.get('params', {})
    
    if not untested_data:
        return jsonify({"success": False, "error": "没有待回测数据"}), 400
    
    total = len(untested_data)
    task_id = f"backtest_{int(time.time() * 1000)}"
    
    task = {
        "id": task_id,
        "type": "backtest",
        "description": f"回测 {total} 个 Alpha",
        "status": "running",
        "progress": 0.0,
        "total": total,
        "completed": 0,
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [{"time": datetime.now().strftime("%H:%M:%S"), "message": "任务已创建，等待子进程启动..."}]
    }
    
    _tasks.append(task)
    save_tasks()
    
    # 启动子进程
    _start_backtest_process(task_id, untested_data, params, resume=False)
    
    return jsonify({"success": True, "task_id": task_id})


@app.route('/api/backtest/resume', methods=['POST'])
def resume_backtest():
    """恢复回测任务（从断点继续）"""
    data = request.json
    task_id = data.get('task_id')
    
    if not task_id:
        return jsonify({"success": False, "error": "缺少任务ID"}), 400
    
    # 查找任务
    task = None
    for t in _tasks:
        if t["id"] == task_id:
            task = t
            break
    
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    
    if task["status"] not in ["stopped", "failed"]:
        return jsonify({"success": False, "error": f"任务状态为 {task['status']}，无法恢复"}), 400
    
    # 加载待回测数据
    from web.utils.helpers import load_to_test_alphas, get_db
    alphas = load_to_test_alphas()
    db = get_db()
    tested_exprs = db.get_tested_expressions()
    untested = [a for a in alphas if a.split("|")[0].strip() not in tested_exprs]
    
    # 加载回测参数
    params = task.get("params", {})
    
    # 更新任务状态
    task["status"] = "running"
    task["started_at"] = datetime.now().isoformat()
    task["finished_at"] = None
    task["details"] = [{"time": datetime.now().strftime("%H:%M:%S"), "message": "从断点恢复..."}]
    save_tasks()
    
    # 启动子进程（带 resume 参数）
    _start_backtest_process(task_id, untested, params, resume=True)
    
    return jsonify({"success": True, "task_id": task_id, "message": "任务已恢复"})

# ========== 同步 API (后台线程执行) ==========

def _run_sync_incremental(task_id: str):
    """后台执行增量同步"""
    from core.api_client import BrainAPIClient
    from core.db_manager import get_database
    
    try:
        # 更新任务状态
        for task in _tasks:
            if task["id"] == task_id:
                task["details"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": "开始同步..."})
                break
        
        db = get_database()
        client = BrainAPIClient()
        
        if not client.ensure_session():
            for task in _tasks:
                if task["id"] == task_id:
                    task["status"] = "failed"
                    task["error"] = "认证失败"
                    break
            save_tasks()
            return
        
        last_sync = db.get_last_sync_time()
        
        if last_sync:
            alphas = client.get_updated_alphas(
                since=last_sync,
                min_sharpe=-999,
                min_fitness=-999,
                max_turnover=1e9
            )
        else:
            alphas = client.get_all_user_alphas(
                min_sharpe=-999,
                min_fitness=-999,
                max_turnover=1e9
            )
        
        if alphas:
            new_count, update_count = db.save_alphas(alphas, is_full_sync=not last_sync)
            db.update_candidate_pool()
        
        client.session.close()
        
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "completed"
                task["finished_at"] = datetime.now().isoformat()
                task["details"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": f"同步完成: 新增{new_count}个, 更新{update_count}个"})
                break
        save_tasks()
        
    except Exception as e:
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "failed"
                task["error"] = str(e)
                break
        save_tasks()


def _run_sync_full(task_id: str):
    """后台执行全量同步"""
    from core.api_client import BrainAPIClient
    from core.db_manager import get_database
    
    try:
        for task in _tasks:
            if task["id"] == task_id:
                task["details"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": "开始全量同步..."})
                break
        
        db = get_database()
        client = BrainAPIClient()
        
        if not client.ensure_session():
            for task in _tasks:
                if task["id"] == task_id:
                    task["status"] = "failed"
                    task["error"] = "认证失败"
                    break
            save_tasks()
            return
        
        alphas = client.get_all_user_alphas(
            min_sharpe=-999,
            min_fitness=-999,
            max_turnover=1e9
        )
        
        if alphas:
            new_count, update_count = db.save_alphas(alphas, is_full_sync=True)
            db.update_candidate_pool()
        
        client.session.close()
        
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "completed"
                task["finished_at"] = datetime.now().isoformat()
                task["details"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": f"全量同步完成: 共{len(alphas)}个Alpha"})
                break
        save_tasks()
        
    except Exception as e:
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "failed"
                task["error"] = str(e)
                break
        save_tasks()


@app.route('/api/sync/incremental', methods=['POST'])
def sync_incremental():
    """增量同步 - 立即返回，后台执行"""
    task_id = f"sync_inc_{int(time.time() * 1000)}"
    
    task = {
        "id": task_id,
        "type": "sync",
        "description": "增量同步",
        "status": "running",
        "progress": 0.0,
        "total": 1,
        "completed": 0,
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [{"time": datetime.now().strftime("%H:%M:%S"), "message": "任务已创建，后台同步中..."}]
    }
    
    _tasks.append(task)
    save_tasks()
    
    # 后台线程执行
    threading.Thread(target=_run_sync_incremental, args=(task_id,), daemon=True).start()
    
    return jsonify({"success": True, "task_id": task_id, "message": "同步任务已启动，请在任务列表查看进度"})


@app.route('/api/sync/full', methods=['POST'])
def sync_full():
    """全量同步 - 立即返回，后台执行"""
    task_id = f"sync_full_{int(time.time() * 1000)}"
    
    task = {
        "id": task_id,
        "type": "sync",
        "description": "全量同步",
        "status": "running",
        "progress": 0.0,
        "total": 1,
        "completed": 0,
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [{"time": datetime.now().strftime("%H:%M:%S"), "message": "任务已创建，后台同步中..."}]
    }
    
    _tasks.append(task)
    save_tasks()
    
    # 后台线程执行
    threading.Thread(target=_run_sync_full, args=(task_id,), daemon=True).start()
    
    return jsonify({"success": True, "task_id": task_id, "message": "同步任务已启动，请在任务列表查看进度"})


# ========== 提交 API (后台线程执行) ==========

def _run_submit(task_id: str, num_to_submit: int):
    """后台执行提交"""
    from core.api_client import BrainAPIClient
    from core.db_manager import get_database
    from core.submit import submit_alpha_ids
    import tempfile
    
    try:
        for task in _tasks:
            if task["id"] == task_id:
                task["details"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": "开始提交..."})
                break
        
        db = get_database()
        client = BrainAPIClient()
        
        if not client.ensure_session():
            for task in _tasks:
                if task["id"] == task_id:
                    task["status"] = "failed"
                    task["error"] = "认证失败"
                    break
            save_tasks()
            return
        
        db.update_candidate_pool()
        candidates = db.get_candidates()
        
        if not candidates:
            client.session.close()
            for task in _tasks:
                if task["id"] == task_id:
                    task["status"] = "completed"
                    task["details"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": "没有可提交的Alpha"})
                    break
            save_tasks()
            return
        
        submit_list = candidates[:num_to_submit]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            for c in submit_list:
                f.write(c['alpha_id'] + '\n')
            temp_path = f.name
        
        try:
            result = submit_alpha_ids(temp_path, num_to_submit=num_to_submit)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        client.session.close()
        
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "completed"
                task["finished_at"] = datetime.now().isoformat()
                task["details"].append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message": f"提交完成: 成功{result['success']}个, 失败{result['failed']}个"
                })
                break
        save_tasks()
        
    except Exception as e:
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "failed"
                task["error"] = str(e)
                break
        save_tasks()


@app.route('/api/submit', methods=['POST'])
def submit_candidates():
    """从候选池提交 Alpha - 立即返回，后台执行"""
    data = request.json
    num_to_submit = data.get('num_to_submit', 10)
    task_id = f"submit_{int(time.time() * 1000)}"
    
    task = {
        "id": task_id,
        "type": "submit",
        "description": f"提交 {num_to_submit} 个 Alpha",
        "status": "running",
        "progress": 0.0,
        "total": num_to_submit,
        "completed": 0,
        "failed": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "details": [{"time": datetime.now().strftime("%H:%M:%S"), "message": "任务已创建，后台提交中..."}]
    }
    
    _tasks.append(task)
    save_tasks()
    
    # 后台线程执行
    threading.Thread(target=_run_submit, args=(task_id, num_to_submit), daemon=True).start()
    
    return jsonify({"success": True, "task_id": task_id, "message": "提交任务已启动，请在任务列表查看进度"})


@app.route('/api/to_test_alphas/add', methods=['POST'])
def add_to_test_alphas():
    """添加表达式到待回测列表"""
    try:
        data = request.get_json()
        expressions = data.get('expressions', [])
        
        if not expressions:
            return jsonify({"success": False, "error": "没有提供表达式"}), 400
        
        to_test_file = project_root / "data" / "alphas" / "to_test.txt"
        to_test_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取现有表达式
        existing = set()
        if to_test_file.exists():
            with open(to_test_file, 'r', encoding='utf-8') as f:
                existing = {line.strip() for line in f if line.strip()}
        
        # 添加新表达式
        added = 0
        skipped = 0
        with open(to_test_file, 'a', encoding='utf-8') as f:
            for expr in expressions:
                expr = expr.strip()
                if expr and expr not in existing:
                    f.write(expr + "\n")
                    existing.add(expr)
                    added += 1
                else:
                    skipped += 1
        
        return jsonify({
            "success": True, 
            "added": added, 
            "skipped": skipped,
            "message": f"添加了 {added} 个表达式，跳过 {skipped} 个重复项"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/to_test_alphas/clear', methods=['POST'])
def clear_to_test_alphas():
    """清空待回测列表"""
    try:
        to_test_file = project_root / "data" / "alphas" / "to_test.txt"
        if to_test_file.exists():
            count = sum(1 for _ in open(to_test_file, 'r', encoding='utf-8') if _.strip())
            to_test_file.unlink()
            return jsonify({"success": True, "cleared": count})
        return jsonify({"success": True, "cleared": 0})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 数据库 API ==========

@app.route('/api/to_test_alphas/count', methods=['GET'])
def get_to_test_alphas_count():
    """获取待回测 Alpha 总数"""
    try:
        to_test_file = project_root / "data" / "alphas" / "to_test.txt"
        if not to_test_file.exists():
            return jsonify({"success": True, "count": 0})
        
        with open(to_test_file, 'r', encoding='utf-8') as f:
            count = sum(1 for line in f if line.strip())
        
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/to_test_alphas', methods=['GET'])
def get_to_test_alphas():
    """获取待回测的 Alpha 列表（支持分页）"""
    try:
        to_test_file = project_root / "data" / "alphas" / "to_test.txt"
        if not to_test_file.exists():
            return jsonify({"success": True, "alphas": [], "total": 0})
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 50, type=int)
        
        with open(to_test_file, 'r', encoding='utf-8') as f:
            all_alphas = [line.strip() for line in f if line.strip()]
        
        total = len(all_alphas)
        
        # 计算分页索引
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_alphas = all_alphas[start_idx:end_idx]
        
        return jsonify({
            "success": True, 
            "alphas": page_alphas, 
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/database/alphas', methods=['GET'])
def get_database_alphas():
    """获取数据库中的 Alpha 列表"""
    try:
        from core.db_manager import get_database
        db = get_database()
        
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        with db._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM alphas 
                ORDER BY updated_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            alphas = [dict(row) for row in cursor.fetchall()]
            
            cursor = conn.execute("SELECT COUNT(*) FROM alphas")
            total = cursor.fetchone()[0]
        
        return jsonify({"success": True, "alphas": alphas, "total": total})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/database/alpha/<alpha_id>', methods=['GET'])
def get_alpha(alpha_id):
    """获取单个 Alpha 详情"""
    try:
        from core.db_manager import get_database
        import sqlite3
        db = get_database()
        
        with db._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM alphas WHERE alpha_id = ?", (alpha_id,)
            )
            row = cursor.fetchone()
            if not row:
                return jsonify({"success": False, "error": "Alpha not found"}), 404
            alpha = dict(row)
        
        return jsonify({"success": True, "alpha": alpha})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/database/tested_expressions', methods=['GET'])
def get_tested_expressions():
    """获取已回测表达式列表"""
    try:
        import sqlite3
        from core.db_manager import get_database
        db = get_database()
        
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        with db._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM tested_expressions 
                ORDER BY test_time DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            expressions = [dict(row) for row in cursor.fetchall()]
            
            cursor = conn.execute("SELECT COUNT(*) FROM tested_expressions")
            total = cursor.fetchone()[0]
        
        return jsonify({"success": True, "expressions": expressions, "total": total})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/database/candidates', methods=['GET'])
def get_candidates():
    """获取候选池（支持分页）"""
    try:
        from core.db_manager import get_database
        db = get_database()
        
        # 分页参数
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 50, type=int)
        
        # 使用数据库层分页
        offset = (page - 1) * page_size
        candidates, total = db.get_candidates(limit=page_size, offset=offset)
        
        # 确保序列化安全
        result = {
            "success": True, 
            "candidates": candidates,
            "total": int(total),
            "page": page,
            "page_size": page_size
        }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/database/stats', methods=['GET'])
def get_database_stats():
    """获取数据库统计信息"""
    try:
        import sqlite3
        from core.db_manager import get_database
        db = get_database()
        
        with db._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM alphas").fetchone()[0]
            qualified = conn.execute("SELECT COUNT(*) FROM alphas WHERE checks_passed = 1").fetchone()[0]
            submitted = conn.execute("SELECT COUNT(*) FROM alphas WHERE submitted_at IS NOT NULL").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM alphas WHERE checks_passed = -1").fetchone()[0]
        
        # 待回测数量
        to_test_file = project_root / "data" / "alphas" / "to_test.txt"
        to_test = 0
        if to_test_file.exists():
            with open(to_test_file, 'r', encoding='utf-8') as f:
                to_test = len([l for l in f if l.strip()])
        
        return jsonify({
            "success": True,
            "stats": {
                "total": total,
                "qualified": qualified,
                "submitted": submitted,
                "pending": pending,
                "to_test": to_test
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/database/alphas/search', methods=['POST'])
def search_alphas():
    """搜索 Alpha"""
    try:
        import sqlite3
        from core.db_manager import get_database
        db = get_database()
        
        data = request.json or {}
        keyword = data.get('keyword', '')
        min_sharpe = data.get('minSharpe')
        max_sharpe = data.get('maxSharpe')
        min_fitness = data.get('minFitness')
        max_fitness = data.get('maxFitness')
        max_turnover = data.get('maxTurnover')
        checks_passed = data.get('checksPassed')
        
        conditions = []
        params = []
        
        if keyword:
            conditions.append("(alpha_id LIKE ? OR expression LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        
        if min_sharpe is not None:
            conditions.append("sharpe >= ?")
            params.append(min_sharpe)
        
        if max_sharpe is not None:
            conditions.append("sharpe <= ?")
            params.append(max_sharpe)
        
        if min_fitness is not None:
            conditions.append("fitness >= ?")
            params.append(min_fitness)
        
        if max_fitness is not None:
            conditions.append("fitness <= ?")
            params.append(max_fitness)
        
        if max_turnover is not None:
            conditions.append("turnover <= ?")
            params.append(max_turnover)
        
        if checks_passed is not None:
            conditions.append("checks_passed = ?")
            params.append(checks_passed)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        with db._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(f"""
                SELECT * FROM alphas 
                WHERE {where_clause}
                ORDER BY fitness DESC, sharpe DESC
                LIMIT 1000
            """, params)
            alphas = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({"success": True, "alphas": alphas})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 中性化组合测试 API ==========

@app.route('/api/neutralization/options', methods=['GET'])
def get_neutralization_options_api():
    """获取中性化选项"""
    from core.neutralization_tester import NEUTRALIZATION_OPTIONS, get_quality_conditions_description
    return jsonify({
        'success': True,
        'regions': NEUTRALIZATION_OPTIONS,
        'max_trade': ['ON', 'OFF'],
        'quality_conditions': get_quality_conditions_description()
    })


@app.route('/api/neutralization/test', methods=['POST'])
def test_neutralization_combinations_api():
    """
    测试中性化组合

    Request Body:
        {
            "alpha_id": "KPwOMNk1",  # Alpha ID
            "expression": "...",      # 可选，如果提供则直接使用
            "region": "USA",          # 可选
            "concurrency": 1          # 可选，默认1（同步）
        }
    """
    from core.neutralization_tester import NeutralizationTester
    from core.api_client import BrainAPIClient

    data = request.json or {}
    alpha_id = data.get('alpha_id')
    expression = data.get('expression')

    if not alpha_id and not expression:
        return jsonify({'success': False, 'error': '必须提供 alpha_id 或 expression'}), 400

    client = BrainAPIClient()

    # 如果提供了 alpha_id，获取表达式和设置
    if alpha_id and not expression:
        try:
            alpha_info = client.get_alpha(alpha_id)
            if not alpha_info:
                return jsonify({'success': False, 'error': f'无法获取Alpha {alpha_id}'}), 404

            expression = alpha_info.get('regular', {}).get('code', '')
            if not expression:
                return jsonify({'success': False, 'error': 'Alpha表达式为空'}), 400

            region = data.get('region', alpha_info.get('settings', {}).get('region', 'USA'))
            universe = data.get('universe', alpha_info.get('settings', {}).get('universe', 'TOP3000'))
            decay = data.get('decay', int(alpha_info.get('settings', {}).get('decay', 30)))
            truncation = data.get('truncation', float(alpha_info.get('settings', {}).get('truncation', 0.08)))
        except Exception as e:
            return jsonify({'success': False, 'error': f'获取Alpha信息失败: {str(e)}'}), 500
    else:
        region = data.get('region', 'USA')
        universe = data.get('universe', 'TOP3000')
        decay = data.get('decay', 30)
        truncation = data.get('truncation', 0.08)

    concurrency = data.get('concurrency', 1)

    try:
        tester = NeutralizationTester(
            expression=expression,
            region=region,
            universe=universe,
            decay=decay,
            truncation=truncation,
            base_alpha_id=alpha_id,
            progress_callback=None
        )

        results = tester.test_all_combinations(concurrency=concurrency)

        return jsonify({
            'success': True,
            'results': [r.to_dict() for r in results],
            'summary': tester.get_summary()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/neutralization/quality-check', methods=['POST'])
def check_neutralization_quality_api():
    """检查单个Alpha是否符合优质条件"""
    from core.neutralization_tester import is_quality_alpha

    data = request.json or {}

    result = {
        'sharpe': float(data.get('sharpe', 0)),
        'turnover': float(data.get('turnover', 1)),
        'margin': float(data.get('margin', 0))
    }

    quality = is_quality_alpha(result)

    # 确定匹配的条件
    matched = 0
    if quality:
        if result['turnover'] <= 0.4 and abs(result['sharpe']) >= 1.5 and abs(result['margin']) >= 0.001:
            matched = 2
        elif result['turnover'] <= 0.4 and abs(result['sharpe']) >= 1.2 and abs(result['margin']) >= 0.0009:
            matched = 1
        elif result['turnover'] <= 0.6 and abs(result['sharpe']) >= 2.0 and abs(result['margin']) >= 0.0015:
            matched = 3

    return jsonify({
        'success': True,
        'is_quality': quality,
        'matched_condition': matched
    })


@app.route('/api/neutralization/batch-test', methods=['POST'])
def batch_neutralization_test_api():
    """
    批量中性化测试

    Request Body:
        {
            "alphas": [
                {"alpha_id": "xxx", "expression": "..."},
                {"alpha_id": "yyy", "expression": "..."}
            ],
            "region": "USA",
            "concurrency": 1
        }
    """
    from core.neutralization_tester import NeutralizationTester

    data = request.json or {}
    alphas = data.get('alphas', [])
    region = data.get('region', 'USA')
    concurrency = data.get('concurrency', 1)

    if not alphas:
        return jsonify({'success': False, 'error': 'alphas 列表不能为空'}), 400

    results = []
    completed = 0

    for alpha_item in alphas:
        alpha_id = alpha_item.get('alpha_id')
        expression = alpha_item.get('expression')

        if not alpha_id and not expression:
            results.append({
                'alpha_id': alpha_id or 'unknown',
                'status': 'error',
                'error': 'alpha_id 和 expression 都为空'
            })
            continue

        try:
            tester = NeutralizationTester(
                expression=expression,
                region=region,
                base_alpha_id=alpha_id,
                progress_callback=None
            )

            test_results = tester.test_all_combinations(concurrency=concurrency)

            results.append({
                'alpha_id': alpha_id,
                'status': 'success',
                'results': [r.to_dict() for r in test_results],
                'summary': tester.get_summary()
            })
            completed += 1

        except Exception as e:
            results.append({
                'alpha_id': alpha_id,
                'status': 'error',
                'error': str(e)
            })

    return jsonify({
        'success': True,
        'total': len(alphas),
        'completed': completed,
        'failed': len(alphas) - completed,
        'results': results
    })


# ========== 启动函数 ==========

def run_api_server(host='0.0.0.0', port=None):
    """运行 API 服务器 (多线程模式)"""
    # 默认端口 5000，与前端 API_BASE 一致
    if port is None:
        port = int(os.environ.get('API_PORT', 5000))
    """运行 API 服务器 (多线程模式)"""
    # 使用 waitress 如果可用，否则用 Flask 内置服务器
    try:
        from waitress import serve
        print(f"[API Server] 使用 waitress 服务器")
        print(f"[API Server] 启动在 http://{host}:{port}")
        print(f"[API Server] 任务文件: {TASKS_FILE}")
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        print(f"[API Server] 使用 Flask 内置服务器 (threaded=True)")
        print(f"[API Server] 启动在 http://{host}:{port}")
        print(f"[API Server] 任务文件: {TASKS_FILE}")
        # threaded=True 避免单请求阻塞
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == '__main__':
    run_api_server()
