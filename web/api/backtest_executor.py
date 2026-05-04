# -*- coding: utf-8 -*-
"""
回测任务执行器
功能：封装回测逻辑，支持断点续传
支持同步/异步两种模式
"""
import json
import time
import sys
import os
import asyncio
import traceback
import logging
from datetime import datetime
from pathlib import Path

# 进度保存间隔（每处理N个保存一次）
PROGRESS_SAVE_INTERVAL = 5

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
sys_path = str(PROJECT_ROOT)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

# 设置日志
log_dir = PROJECT_ROOT / "logs"
log_dir.mkdir(exist_ok=True)
# 使用 UTF-8 编码避免 emoji 字符编码问题
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f"backtest_executor_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 导入引擎（优先异步）
try:
    from core.async_backtest_engine import AsyncBacktestEngine
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    logger.warning("异步引擎不可用，将使用同步引擎")

if not ASYNC_AVAILABLE:
    from core.backtest_engine import BacktestEngine


def main():
    """从参数文件启动的主函数"""
    if len(sys.argv) < 2:
        print("用法: python backtest_executor.py <参数文件路径>")
        sys.exit(1)
    
    param_file = sys.argv[1]
    
    # 读取参数
    with open(param_file, 'r', encoding='utf-8') as f:
        args = json.load(f)
    
    task_id = args['task_id']
    untested_data = args['data']
    params = args['params']
    resume = args.get('resume', False)
    input_file = args.get('input_file')  # 待回测文件路径，成功时删除
    
    # 删除临时文件
    try:
        os.remove(param_file)
    except:
        pass
    
    # 执行回测
    run_backtest_task(task_id, untested_data, params, resume=resume, input_file=input_file)


def run_backtest_task(task_id: str, untested_data: list, params: dict, resume: bool = False, input_file: str = None):
    """
    执行回测任务（支持断点续传）
    使用异步回测引擎
    
    Args:
        task_id: 任务ID
        untested_data: 待回测数据 [(index, expression), ...]
        params: 回测参数
        resume: 是否从断点恢复
        input_file: 待回测文件路径，成功时从该文件删除
    """
    logger.info(f"[{task_id}] 任务进程启动 (异步引擎: {ASYNC_AVAILABLE})")
    logger.info(f"[{task_id}] 待回测数量: {len(untested_data)}")
    logger.info(f"[{task_id}] 参数: {params}")
    logger.info(f"[{task_id}] 断点续传: {resume}")
    logger.info(f"[{task_id}] 待回测文件: {input_file}")
    
    # 任务文件路径
    tasks_file = PROJECT_ROOT / "data" / "tasks.json"
    
    def load_tasks():
        if tasks_file.exists():
            try:
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[{task_id}] 加载任务失败: {e}")
                return []
        return []
    
    def save_tasks(tasks):
        try:
            with open(tasks_file, 'w', encoding='utf-8') as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[{task_id}] 保存任务失败: {e}")
    
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
    
    # 进度计数器
    _success_count = 0
    _fail_count = 0
    _total_count = len(untested_data)
    _last_update_time = time.time()
    _lock = __import__('threading').Lock()
    
    def result_callback(result):
        """结果回调"""
        nonlocal _success_count, _fail_count, _last_update_time
        from core.async_backtest_engine import BacktestResult
        
        if isinstance(result, BacktestResult):
            if result.status == "OK":
                append_detail(task_id, f"✅ 成功: {result.expression[:30]}...")
                _success_count += 1
            else:
                append_detail(task_id, f"❌ 失败: {result.error}")
                _fail_count += 1
        else:
            # 旧格式兼容
            if result.get('status') == 'OK':
                append_detail(task_id, f"✅ 成功")
                _success_count += 1
            else:
                append_detail(task_id, f"❌ 失败: {result.get('error', '未知错误')}")
                _fail_count += 1
        
        # 每 5 秒或处理 10 个更新一次任务状态
        current_time = time.time()
        _processed_count = _success_count + _fail_count
        if current_time - _last_update_time >= 5 or _processed_count % 10 == 0:
            progress = _processed_count / _total_count if _total_count > 0 else 0
            update_task(task_id, progress=progress, completed=_success_count, failed=_fail_count)
            _last_update_time = current_time
    
    def progress_callback(progress_data):
        """进度回调 - 同时更新官方进度"""
        from web.utils.task_progress import get_progress_manager
        progress_mgr = get_progress_manager()
        
        # 更新进度（标记有活动）
        progress_mgr.mark_processed(task_id, "", True)
        
        # 如果有官方进度，更新任务详情
        if isinstance(progress_data, dict):
            official_progress = progress_data.get('official_progress')
            if official_progress is not None:
                # 更新任务文件中的官方进度
                tasks = load_tasks()
                for t in tasks:
                    if t["id"] == task_id:
                        t["official_progress"] = official_progress
                        break
                save_tasks(tasks)
    
    try:
        if ASYNC_AVAILABLE:
            # 使用异步引擎
            asyncio.run(_run_async_backtest(task_id, untested_data, params, input_file, 
                                           result_callback, progress_callback,
                                           _success_count, _fail_count, _total_count,
                                           update_task, append_detail))
        else:
            # 降级到同步引擎
            from core.backtest_engine import BacktestEngine
            engine = BacktestEngine(result_callback=result_callback)
            engine.run_with_progress(
                task_id=task_id,
                untested_data=untested_data,
                params=params,
                resume=resume,
                input_file=input_file
            )
        
        # 任务完成
        logger.info(f"[{task_id}] 回测完成: {_success_count} 成功, {_fail_count} 失败")
        update_task(task_id, status="completed", progress=1.0, completed=_success_count, failed=_fail_count)
        append_detail(task_id, f"回测完成: {_success_count} 成功, {_fail_count} 失败")
    
    except Exception as e:
        logger.error(f"[{task_id}] 回测引擎异常: {e}")
        traceback.print_exc()
        update_task(task_id, status="failed", error=f"回测引擎异常: {str(e)}")
    
    logger.info(f"[{task_id}] 任务进程结束")


async def _run_async_backtest(task_id, untested_data, params, input_file,
                              result_callback, progress_callback,
                              success_count, fail_count, total_count,
                              update_task, append_detail):
    """异步执行回测"""
    from core.async_backtest_engine import AsyncBacktestEngine
    from core.backtest_engine import BacktestResult
    
    # 准备 alphas 列表
    alphas = []
    for i, item in enumerate(untested_data):
        if isinstance(item, dict):
            # 已经是字典格式
            alpha = item
            alphas.append(alpha)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            # (index, expression) 元组格式
            idx, expr = item[0], item[1]
            alpha = {
                'expression': expr,
                'universe': params.get('universe', 'TOP3000'),
                'decay': params.get('decay', 30),
                'neutralization': params.get('neutralization', 'SECTOR'),
                'truncation': params.get('truncation', 0.08),
                'region': params.get('region', 'USA'),
                'test_period': params.get('test_period', 'P2Y0M'),
                'index': idx
            }
            alphas.append(alpha)
        elif isinstance(item, str):
            # 完整的行字符串格式 "expression|universe|decay|neutralization|truncation"
            # 提取表达式和参数
            parts = item.split('|')
            expr = parts[0].strip()
            
            alpha = {
                'expression': expr,
                'universe': parts[1].strip() if len(parts) > 1 else params.get('universe', 'TOP3000'),
                'decay': int(parts[2].strip()) if len(parts) > 2 else params.get('decay', 30),
                'neutralization': parts[3].strip().upper() if len(parts) > 3 else params.get('neutralization', 'SECTOR'),
                'truncation': float(parts[4].strip()) if len(parts) > 4 else params.get('truncation', 0.08),
                'region': params.get('region', 'USA'),
                'test_period': params.get('test_period', 'P2Y0M'),
                'index': i + 1
            }
            alphas.append(alpha)
        else:
            logger.warning(f"[{task_id}] Unknown item format: {type(item)}")
    
    # 并发数 - 默认使用2提升效率
    concurrency = params.get('concurrency', 3)  # 默认并发数：3（与命令行一致）
    request_delay = params.get('request_delay', 3.0)  # 安全间隔：3秒
    logger.info(f"[{task_id}] 启动异步回测，并发数: {concurrency}, 间隔: {request_delay}s")
    
    engine = AsyncBacktestEngine(
        progress_callback=progress_callback,
        result_callback=result_callback,
        concurrency=concurrency,
        remove_tested=True,
        input_file=str(input_file) if input_file else ""
    )
    
    # 异步执行
    results = await engine.run_batch_async(alphas, input_file=str(input_file) if input_file else "")
    
    return results


if __name__ == "__main__":
    main()
