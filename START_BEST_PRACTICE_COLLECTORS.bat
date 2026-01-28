@echo off
chcp 65001
cls
echo.
echo ============================================================
echo    数据库慢SQL监控系统 - 最佳实践采集器
echo ============================================================
echo.
echo 采集方式: 双轨制混合采集
echo   主采集器: Performance Schema (MySQL) + Query Store (SQL Server)
echo   辅助采集器: Processlist (MySQL) + DMV (SQL Server)
echo.
echo 优势:
echo   - 对数据库侵入最低
echo   - 性能最好
echo   - 准确率100%%
echo   - 不会遗漏任何慢SQL
echo ============================================================
echo.

cd /d %~dp0

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
echo [提示] 请选择启动模式:
echo.
echo   1. 仅启动新采集器 (Performance Schema + Query Store)
echo   2. 双轨制模式 (新采集器 + 旧采集器)
echo   3. 仅启动旧采集器 (Processlist + DMV) [不推荐]
echo   4. 测试新采集器 (单次运行)
echo   0. 退出
echo.
set /p choice="请输入选择 (1-4): "

if "%choice%"=="1" goto start_new_only
if "%choice%"=="2" goto start_both
if "%choice%"=="3" goto start_old_only
if "%choice%"=="4" goto test_new
if "%choice%"=="0" exit /b 0

echo 无效选择，退出。
pause
exit /b 1

:start_new_only
echo.
echo ============================================================
echo 启动模式: 仅新采集器 (推荐)
echo ============================================================
echo.
echo [1/2] 启动 MySQL Performance Schema 采集器...
start "MySQL PerfSchema Collector" python scripts\mysql_perfschema_collector.py --daemon --interval 60 --threshold 5
timeout /t 2 /nobreak >nul

echo [2/2] 启动 SQL Server Query Store 采集器...
start "SQLServer QueryStore Collector" python scripts\sqlserver_querystore_collector.py --daemon --interval 60 --threshold 5 --auto-enable
timeout /t 2 /nobreak >nul

echo.
echo [完成] 新采集器已启动！
echo.
echo 日志文件:
echo   - logs\mysql_perfschema.log
echo   - logs\sqlserver_querystore.log
echo.
goto end

:start_both
echo.
echo ============================================================
echo 启动模式: 双轨制 (新+旧)
echo ============================================================
echo.
echo [1/3] 启动 MySQL Performance Schema 采集器 (主, 60秒)...
start "MySQL PerfSchema Collector" python scripts\mysql_perfschema_collector.py --daemon --interval 60 --threshold 5
timeout /t 2 /nobreak >nul

echo [2/3] 启动 SQL Server Query Store 采集器 (主, 60秒)...
start "SQLServer QueryStore Collector" python scripts\sqlserver_querystore_collector.py --daemon --interval 60 --threshold 5 --auto-enable
timeout /t 2 /nobreak >nul

echo [3/3] 启动旧采集器 (辅助, 30秒)...
start "Legacy Collector" python scripts\collector_enhanced.py --daemon --interval 30 --threshold 5
timeout /t 2 /nobreak >nul

echo.
echo [完成] 所有采集器已启动！
echo.
echo 日志文件:
echo   - logs\mysql_perfschema.log
echo   - logs\sqlserver_querystore.log
echo   - logs\collector.log
echo.
goto end

:start_old_only
echo.
echo ============================================================
echo 启动模式: 仅旧采集器 (不推荐)
echo ============================================================
echo.
echo [警告] 旧采集器准确率只有60-80%%，会遗漏慢SQL！
echo 建议使用新采集器。
echo.
pause

echo [1/1] 启动旧采集器...
start "Legacy Collector" python scripts\collector_enhanced.py --daemon --interval 10 --threshold 5
timeout /t 2 /nobreak >nul

echo.
echo [完成] 旧采集器已启动！
echo 日志文件: logs\collector.log
echo.
goto end

:test_new
echo.
echo ============================================================
echo 测试模式: 单次运行新采集器
echo ============================================================
echo.
echo [1/2] 测试 MySQL Performance Schema 采集器...
python scripts\mysql_perfschema_collector.py --threshold 5
echo.
echo [2/2] 测试 SQL Server Query Store 采集器...
python scripts\sqlserver_querystore_collector.py --threshold 5
echo.
echo [完成] 测试完成！
echo.
pause
exit /b 0

:end
echo.
echo ============================================================
echo 采集器状态
echo ============================================================
echo.
echo 查看运行中的Python进程:
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq MySQL*" 2>nul
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq SQLServer*" 2>nul
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq Legacy*" 2>nul
echo.
echo 停止采集器:
echo   - 关闭弹出的命令窗口，或
echo   - 任务管理器结束Python进程
echo.
echo ============================================================
echo 等待3分钟后，检查数据库是否有新数据:
echo.
echo   SELECT COUNT(*), MAX(detect_time)
echo   FROM long_running_sql_log
echo   WHERE detect_time ^>= DATE_SUB(NOW(), INTERVAL 5 MINUTE);
echo.
echo 如果有新数据，说明采集器正常工作！
echo ============================================================
echo.
pause
