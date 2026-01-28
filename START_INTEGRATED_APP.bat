@echo off
chcp 65001
cls
echo.
echo ============================================================
echo    数据库监控系统 - 集成版启动脚本
echo ============================================================
echo.
echo 说明:
echo   - Flask Web应用 (端口5000)
echo   - MySQL Performance Schema 采集器 (60秒/次)
echo   - SQL Server Query Store 采集器 (60秒/次)
echo   - 已过滤SQL Server CDC作业
echo.
echo 所有功能集成在一个进程中，无需启动多个程序！
echo ============================================================
echo.

cd /d C:\运维工具类\database-monitor

REM 检查pyodbc是否安装
python -c "import pyodbc; print('[OK] pyodbc已安装')" 2>nul
if errorlevel 1 (
    echo [警告] pyodbc未安装，SQL Server监控将不可用
    echo 安装命令: pip install pyodbc
    echo.
    pause
    exit /b 1
)

REM 创建logs目录
if not exist logs mkdir logs

echo.
echo [启动] 正在启动数据库监控系统...
echo.

start "数据库监控系统" python app_new.py

timeout /t 3 /nobreak >nul

echo.
echo ============================================================
echo 启动完成！
echo ============================================================
echo.
echo Web界面地址:
echo   - http://localhost:5000
echo   - http://192.168.44.200:5000
echo.
echo 采集器状态:
echo   - MySQL采集: 每60秒自动运行
echo   - SQL Server采集: 每60秒自动运行 (已过滤CDC作业)
echo.
echo 查看日志:
echo   - type logs\app_running.log
echo.
echo 停止服务:
echo   - 关闭弹出的命令窗口，或
echo   - 任务管理器结束Python进程
echo.
echo ============================================================
echo.
pause
