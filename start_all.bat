@echo off
chcp 65001 >nul
cd /d "d:\python_repo\worldquant-autocommit-alpha-master"

echo [1] Starting API Server (FastAPI)...
start "API Server" cmd /k "python web\run.py"

echo [2] Waiting for server...
timeout /t 4 /nobreak >nul

echo [3] Checking API health...
curl -s http://localhost:5000/api/health

echo.
echo [4] Starting Frontend (Streamlit)...
start "Frontend" cmd /k "python -m streamlit run web\app.py --server.port 8501 --server.headless true"

echo.
echo Done! Please visit:
echo   API: http://localhost:5000
echo   Frontend: http://localhost:8501
pause
