# -*- coding: utf-8 -*-
"""
一键启动脚本 - 启动 API Server 和 Frontend
"""
import subprocess
import time
import sys
import os

def get_venv_python():
    """获取虚拟环境中的 Python 解释器路径"""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    venv_paths = []
    
    if sys.platform == "win32":
        venv_paths = [
            os.path.join(root_dir, ".venv", "Scripts", "python.exe"),
        ]
    else:
        # Linux/macOS 可能的虚拟环境路径
        venv_paths = [
            os.path.join(root_dir, ".venv", "bin", "python"),
            os.path.join(root_dir, "data", ".venv", "bin", "python"),
        ]
    
    for venv_path in venv_paths:
        if os.path.exists(venv_path):
            return venv_path
    
    # 返回第一个路径（用于显示警告）
    return venv_paths[0] if venv_paths else sys.executable

def main():
    # 获取项目根目录
    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)

    # 使用虚拟环境中的 Python
    venv_python = get_venv_python()
    if not os.path.exists(venv_python):
        print(f"Warning: {venv_python} not found, using system Python")
        venv_python = sys.executable

    print("[1] Starting API Server (FastAPI)...")
    api_process = subprocess.Popen(
        [venv_python, "web/run.py"],
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    )

    print("[2] Waiting for server...")
    time.sleep(4)

    print("[3] Checking API health...")
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:5000/api/health"],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(result.stdout or result.stderr)
    except Exception as e:
        print(f"Health check failed: {e}")

    print("\n[4] Starting Frontend (Streamlit)...")
    frontend_process = subprocess.Popen(
        [venv_python, "-m", "streamlit", "run", "web/app.py",
         "--server.port", "8501", "--server.headless", "true"],
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    )

    print("\n" + "="*50)
    print("Done! Please visit:")
    print("  API: http://localhost:5000")
    print("  Frontend: http://localhost:8501")
    print("="*50)
    print("\nPress Ctrl+C to stop all services")

    try:
        api_process.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        api_process.terminate()
        frontend_process.terminate()

if __name__ == "__main__":
    main()
