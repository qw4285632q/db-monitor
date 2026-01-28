@echo off
chcp 65001
cls
echo.
echo ============================================================
echo    配置数据库监控系统开机自启动
echo ============================================================
echo.
echo 本脚本将创建3个Windows任务计划:
echo   1. Flask Web应用 (端口5000)
echo   2. MySQL Performance Schema 采集器 (60秒/次)
echo   3. SQL Server Query Store 采集器 (60秒/次)
echo.
echo 这些任务将在系统启动时自动运行。
echo ============================================================
echo.
pause

cd /d C:\运维工具类\database-monitor

echo.
echo [1/3] 创建Flask Web应用自启动任务...
schtasks /create /tn "DB_Monitor_Web" /tr "python C:\运维工具类\database-monitor\app_new.py" /sc onstart /ru SYSTEM /rl HIGHEST /f
if errorlevel 1 (
    echo [错误] 创建任务失败
) else (
    echo [OK] 任务创建成功
)

echo.
echo [2/3] 创建MySQL采集器自启动任务...
schtasks /create /tn "DB_Monitor_MySQL_Collector" /tr "python C:\运维工具类\database-monitor\scripts\mysql_perfschema_collector.py --daemon --interval 60 --threshold 5" /sc onstart /ru SYSTEM /rl HIGHEST /f
if errorlevel 1 (
    echo [错误] 创建任务失败
) else (
    echo [OK] 任务创建成功
)

echo.
echo [3/3] 创建SQL Server采集器自启动任务...
schtasks /create /tn "DB_Monitor_SQLServer_Collector" /tr "python C:\运维工具类\database-monitor\scripts\sqlserver_querystore_collector.py --daemon --interval 60 --threshold 5 --auto-enable" /sc onstart /ru SYSTEM /rl HIGHEST /f
if errorlevel 1 (
    echo [错误] 创建任务失败
) else (
    echo [OK] 任务创建成功
)

echo.
echo ============================================================
echo 配置完成！
echo ============================================================
echo.
echo 已创建的任务计划:
schtasks /query /tn "DB_Monitor_Web" 2>nul
schtasks /query /tn "DB_Monitor_MySQL_Collector" 2>nul
schtasks /query /tn "DB_Monitor_SQLServer_Collector" 2>nul
echo.
echo 管理任务计划:
echo   - 查看: 运行 taskschd.msc
echo   - 删除: schtasks /delete /tn "任务名称" /f
echo   - 手动运行: schtasks /run /tn "任务名称"
echo.
echo ============================================================
pause
