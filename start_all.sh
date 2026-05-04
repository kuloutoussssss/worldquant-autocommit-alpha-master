#!/bin/bash
# 一键启动脚本 - Linux/macOS

cd "$(dirname "$0")"

echo "[1] Starting API Server (FastAPI)..."
python web/run.py &
API_PID=$!

echo "[2] Waiting for server..."
sleep 4

echo "[3] Checking API health..."
curl -s http://localhost:5000/api/health

echo ""
echo "[4] Starting Frontend (Streamlit)..."
python -m streamlit run web/app.py --server.port 8501 --server.headless true &

echo ""
echo "Done! Please visit:"
echo "  API: http://localhost:5000"
echo "  Frontend: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop all services"

# 等待信号
wait
