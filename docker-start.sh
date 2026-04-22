#!/bin/bash
# WorldQuant Alpha Manager Docker 管理脚本

echo "================================"
echo "WorldQuant Alpha Manager Docker"
echo "================================"
echo ""
echo "1. 构建并启动容器"
echo "2. 启动已有容器"
echo "3. 停止容器"
echo "4. 查看日志"
echo "5. 重建并启动"
echo "0. 退出"
echo ""

read -p "请选择操作: " choice

case $choice in
    1)
        docker-compose up -d --build
        echo ""
        echo "服务已启动: http://localhost:8501"
        ;;
    2)
        docker-compose start
        echo ""
        echo "服务已启动: http://localhost:8501"
        ;;
    3)
        docker-compose stop
        echo ""
        echo "服务已停止"
        ;;
    4)
        docker-compose logs -f
        ;;
    5)
        docker-compose down
        docker-compose up -d --build
        echo ""
        echo "服务已重建并启动: http://localhost:8501"
        ;;
    0)
        exit 0
        ;;
esac
