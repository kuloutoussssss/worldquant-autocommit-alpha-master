@echo off
echo ================================
echo WorldQuant Alpha Manager Docker
echo ================================

echo.
echo 1. 构建并启动容器
echo 2. 启动已有容器
echo 3. 停止容器
echo 4. 查看日志
echo 5. 重建并启动
echo 0. 退出
echo.

set /p choice="请选择操作: "

if "%choice%"=="1" goto build_start
if "%choice%"=="2" goto start
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto rebuild
if "%choice%"=="0" goto end

:build_start
docker-compose up -d --build
echo.
echo 服务已启动: http://localhost:8501
goto done

:start
docker-compose start
echo.
echo 服务已启动: http://localhost:8501
goto done

:stop
docker-compose stop
echo.
echo 服务已停止
goto done

:logs
docker-compose logs -f
goto done

:rebuild
docker-compose down
docker-compose up -d --build
echo.
echo 服务已重建并启动: http://localhost:8501
goto done

:done
echo.
pause

:end
