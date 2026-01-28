@echo off
chcp 65001
cls
echo.
echo ============================================================
echo    配置数据库监控系统开机自启动 (集成版)
echo ============================================================
echo.
echo 本脚本将创建1个Windows任务计划:
echo   - 数据库监控系统 (Flask Web + MySQL采集器 + SQL Server采集器)
echo.
echo 集成版说明:
echo   - 所有功能集成在一个进程中
echo   - 管理更简单，资源占用更少
echo   - 已过滤SQL Server CDC作业
echo.
echo 这个任务将在系统启动时自动运行。
echo ============================================================
echo.
pause

cd /d C:\运维工具类\database-monitor

echo.
echo [1/1] 创建数据库监控系统自启动任务...
schtasks /create /tn "DB_Monitor_Integrated" /tr "python C:\运维工具类\database-monitor\app_new.py" /sc onstart /ru SYSTEM /rl HIGHEST /f
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
schtasks /query /tn "DB_Monitor_Integrated" 2>nul
echo.
echo 管理任务计划:
echo   - 查看: 运行 taskschd.msc
echo   - 删除: schtasks /delete /tn "DB_Monitor_Integrated" /f
echo   - 手动运行: schtasks /run /tn "DB_Monitor_Integrated"
echo.
echo 说明:
echo   - 此任务包含Web应用和所有采集器
echo   - 系统重启后会自动启动
echo   - Web界面: http://localhost:5000
echo   - 采集间隔: 60秒/次
echo.
echo ============================================================
pause
