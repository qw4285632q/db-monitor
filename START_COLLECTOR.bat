@echo off
chcp 65001
echo ========================================
echo SQL监控采集器
echo ========================================
echo 当前配置:
echo - 慢SQL阈值: 5秒
echo - 采集间隔: 10秒
echo - 告警阈值: 1分钟
echo ========================================
echo.

cd /d %~dp0

REM 检查pyodbc是否安装 (SQL Server支持)
python -c "import pyodbc; print('[OK] pyodbc已安装')" 2>nul
if errorlevel 1 (
    echo [警告] pyodbc未安装，SQL Server监控将不可用
    echo 安装命令: pip install pyodbc
    echo.
)

REM 创建logs目录
if not exist logs mkdir logs

REM 启动采集器 (daemon守护进程模式)
echo 启动采集器...
echo 日志文件: logs\collector.log
echo 按 Ctrl+C 停止采集器
echo.
python scripts\collector_enhanced.py --daemon --interval 10 --threshold 5

pause
