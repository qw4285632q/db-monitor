@echo off
chcp 65001 >nul
title 数据库Long SQL监控系统

echo ============================================
echo   数据库Long SQL监控系统
echo ============================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python未安装或未添加到PATH
    echo 请先安装Python 3.8+
    pause
    exit /b 1
)

:: 检查虚拟环境
if not exist "venv" (
    echo [信息] 创建虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境
echo [信息] 激活虚拟环境...
call venv\Scripts\activate.bat

:: 安装依赖
echo [信息] 检查依赖包...
pip install -r requirements.txt -q

:: 创建必要目录
if not exist "static" mkdir static
if not exist "templates" mkdir templates
if not exist "logs" mkdir logs

:: 检查静态文件
if not exist "static\index.html" (
    if exist "index.html" (
        echo [信息] 复制前端文件到static目录...
        copy index.html static\index.html >nul
    )
)

echo.
echo ============================================
echo   启动Web服务器
echo ============================================
echo.
echo   访问地址: http://localhost:5000
echo   API文档:
echo     - 健康检查: http://localhost:5000/api/health
echo     - 实例列表: http://localhost:5000/api/instances
echo     - 长时SQL:  http://localhost:5000/api/long_sql
echo     - 统计数据: http://localhost:5000/api/statistics
echo     - 系统配置: http://localhost:5000/api/config
echo.
echo   按 Ctrl+C 停止服务
echo ============================================
echo.

:: 启动Flask应用 (使用app_new.py包含配置管理功能)
if exist "app_new.py" (
    python app_new.py
) else (
    python app.py
)

pause
