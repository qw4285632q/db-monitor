# SQL Server 系统进程过滤规则

## 📋 说明

为确保慢SQL监控只关注真实的业务查询，采集器会自动过滤以下系统后台进程。这些进程虽然运行时间长，但不是需要优化的业务SQL。

---

## 🔴 已过滤的系统进程类型

### 1. CDC (Change Data Capture) - 变更数据捕获

**特征：**
- 存储过程：`sp_cdc_*`, `sp_MScdc_*`
- 用途：捕获数据库表的变更记录
- 运行模式：持续运行的后台作业

**为什么过滤：**
- CDC作业永久运行，会持续出现在慢SQL列表中
- 不是业务SQL，无需优化
- 运行时间长是正常的

**示例SQL：**
```sql
EXEC sp_cdc_scan @maxtrans = 500
EXEC sp_MScdc_capture_job
```

---

### 2. Replication - 数据复制

**特征：**
- 存储过程：`sp_replcmds`, `sp_MSrepl_*`, `sp_publication_*`
- 程序名：包含 `Repl-LogReader`, `REPLICATION`
- 数据库：`distribution`, `msdb`

**为什么过滤：**
- 复制作业需要持续读取事务日志
- 不是业务查询
- 性能取决于复制配置，非SQL优化问题

**示例SQL：**
```sql
EXEC sp_replcmds
EXEC sp_MSrepl_getdistributorinfo
```

---

### 3. sp_server_diagnostics - 系统健康检查

**特征：**
- 存储过程：`sp_server_diagnostics`
- 会话状态：`suspended`
- 运行时间：几小时到几天

**用途：**
- AlwaysOn 可用性组的健康检查
- 故障转移集群实例 (FCI) 的资源监控
- 每5秒输出一次服务器诊断数据

**为什么过滤：**
- 系统自动调用，非用户SQL
- 持续运行直到实例重启
- 运行时间长是正常行为
- **显示在列表中会造成误解**

**诊断数据包括：**
- CPU 使用率
- 内存状态
- IO 统计
- 查询统计
- 系统资源信息

**示例：**
```sql
-- 典型会话特征
session_id: 52
program_name: .Net SqlClient Data Provider
status: suspended
elapsed_time: 35791.39 分钟 (约24.8天)
username: NT AUTHORITY\SYSTEM
```

---

### 4. 事务管理代码 - 连接池清理 ⭐ 新增

**特征：**
- SQL模式：`IF @@TRANCOUNT > 0 COMMIT TRAN`
- 运行时间：可能很长（持续运行）
- 来源：应用程序连接池、ORM框架

**用途：**
- 应用程序连接池回收前的事务清理
- ORM框架（EF、Hibernate）的连接管理
- 防止未提交事务堆积

**为什么过滤：**
- 不是业务SQL
- 应用程序框架的管理代码
- 持续运行是正常行为
- 无需优化

**典型场景：**
1. **.NET应用连接池**
   ```sql
   IF @@TRANCOUNT > 0 COMMIT TRAN
   ```

2. **Entity Framework清理**
   ```sql
   IF @@TRANCOUNT > 0 COMMIT TRANSACTION
   ```

3. **JDBC连接回收**
   ```sql
   IF @@TRANCOUNT > 0 COMMIT
   ```

**示例采集记录：**
```
历史采集数量: 8次
最长执行时间: 7321.25 分钟 (约5天)
最后采集时间: 2026-01-28 08:49:27
```

**判断依据：**
- 包含 `@@TRANCOUNT` 和 `COMMIT` 关键字
- SQL通常很短（1-2行）
- 来自应用程序连接，非DBA手动执行

---

### 5. SQLAgent 系统作业

**特征：**
- 程序名：包含 `SQLAgent`
- 数据库：系统数据库 (`master`, `tempdb`, `model`, `msdb`)

**过滤策略：**
- ✅ **保留**：用户通过SQLAgent执行的业务SQL（如ETL作业）
- ❌ **过滤**：SQLAgent执行的系统维护作业（CDC、复制等）

**判断逻辑：**
```sql
-- 以下情况会被过滤
程序名 = 'SQLAgent'
  AND (SQL包含系统存储过程 OR 数据库为系统库)
```

---

## 🔧 技术实现

### Query Store 过滤 (聚合数据)

```sql
WHERE qsrs.avg_duration >= ?
  AND qsrs.last_execution_time >= DATEADD(MINUTE, -5, GETDATE())
  -- 过滤CDC
  AND qsqt.query_sql_text NOT LIKE '%sp_cdc_%'
  AND qsqt.query_sql_text NOT LIKE '%sp_MScdc_%'
  -- 过滤复制
  AND qsqt.query_sql_text NOT LIKE '%sp_replcmds%'
  AND qsqt.query_sql_text NOT LIKE '%sp_MSrepl_%'
  -- 过滤系统健康检查
  AND qsqt.query_sql_text NOT LIKE '%sp_server_diagnostics%'
  -- 过滤事务管理代码
  AND NOT (qsqt.query_sql_text LIKE '%@@TRANCOUNT%' AND qsqt.query_sql_text LIKE '%COMMIT%')
```

### DMV 过滤 (实时数据)

```sql
WHERE r.session_id != @@SPID
  AND r.total_elapsed_time >= ?
  AND t.text IS NOT NULL
  -- 过滤CDC
  AND NOT (t.text LIKE '%sp_cdc_%' OR t.text LIKE '%sp_MScdc_%')
  -- 过滤复制
  AND NOT (t.text LIKE '%sp_replcmds%' OR t.text LIKE '%sp_MSrepl_%')
  -- 过滤系统健康检查
  AND NOT (t.text LIKE '%sp_server_diagnostics%')
  -- 过滤事务管理代码
  AND NOT (t.text LIKE '%@@TRANCOUNT%' AND t.text LIKE '%COMMIT%')
  -- 过滤日志读取器
  AND NOT (s.program_name LIKE '%Repl-LogReader%' OR s.program_name LIKE '%REPLICATION%')
  -- 过滤SQLAgent系统作业
  AND NOT (s.program_name LIKE '%SQLAgent%' AND (
      t.text LIKE '%sp_cdc_%'
      OR t.text LIKE '%sp_replcmds%'
      OR DB_NAME(r.database_id) IN ('distribution', 'msdb')
  ))
```

---

## 📊 过滤效果验证

### 验证Query Store过滤

```sql
-- 在SQL Server上执行
USE [YourDatabase];

-- 查询当前是否有系统进程
SELECT
    qsqt.query_sql_text,
    qsrs.count_executions,
    qsrs.avg_duration / 1000000.0 AS avg_duration_seconds
FROM sys.query_store_query qsq
JOIN sys.query_store_query_text qsqt ON qsq.query_text_id = qsqt.query_text_id
JOIN sys.query_store_plan qsp ON qsq.query_id = qsp.query_id
JOIN sys.query_store_runtime_stats qsrs ON qsp.plan_id = qsrs.plan_id
WHERE qsqt.query_sql_text LIKE '%sp_server_diagnostics%'
   OR qsqt.query_sql_text LIKE '%sp_cdc_%';
```

### 验证DMV过滤

```sql
-- 查询当前正在运行的系统进程
SELECT
    r.session_id,
    s.program_name,
    t.text AS sql_text,
    r.total_elapsed_time / 1000.0 AS elapsed_seconds,
    r.status
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE t.text LIKE '%sp_server_diagnostics%'
   OR t.text LIKE '%sp_cdc_%';
```

### 验证监控数据库

```sql
-- 在监控数据库执行
USE db_monitor;

-- 查询最近采集的系统进程数量（应该为0）
SELECT COUNT(*) AS system_process_count
FROM long_running_sql_log
WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
  AND (
    sql_text LIKE '%sp_server_diagnostics%'
    OR sql_text LIKE '%sp_cdc_%'
    OR sql_text LIKE '%sp_MScdc_%'
    OR sql_text LIKE '%sp_replcmds%'
    OR sql_text LIKE '%sp_MSrepl_%'
    OR (sql_text LIKE '%@@TRANCOUNT%' AND sql_text LIKE '%COMMIT%')
  );

-- 预期结果：0
```

---

## ⚙️ 配置说明

### 如何临时禁用过滤（调试用）

如果需要查看所有SQL（包括系统进程），可以：

1. **停止采集器**
   ```bash
   taskkill /F /IM python.exe
   ```

2. **修改过滤器代码**
   - 编辑 `scripts/sqlserver_querystore_collector.py`
   - 注释掉 WHERE 子句中的过滤条件

3. **重启采集器**
   ```bash
   START_INTEGRATED_APP.bat
   ```

### 如何添加新的过滤规则

编辑文件：`scripts/sqlserver_querystore_collector.py`

**Query Store采集（第263-270行）：**
```sql
-- 添加新的过滤规则
AND qsqt.query_sql_text NOT LIKE '%your_system_proc%'
```

**DMV采集（第345-362行）：**
```sql
-- 添加新的过滤规则
AND NOT (t.text LIKE '%your_system_proc%')
```

---

## 🎯 总结

### 当前过滤的系统进程

| 类型 | 关键字 | 说明 |
|------|--------|------|
| CDC | sp_cdc_*, sp_MScdc_* | 变更数据捕获 |
| 复制 | sp_replcmds, sp_MSrepl_* | 数据库复制 |
| 健康检查 | sp_server_diagnostics | AlwaysOn/FCI监控 |
| 事务管理 | @@TRANCOUNT + COMMIT | 连接池清理/ORM框架 |
| 日志读取器 | program_name包含Repl-LogReader | 复制日志读取 |
| SQLAgent系统作业 | 系统库+系统存储过程 | 系统维护作业 |

### 过滤原则

✅ **保留业务SQL**：
- 用户应用程序执行的查询
- ETL作业、报表查询
- 存储过程调用（业务逻辑）

❌ **过滤系统进程**：
- 持续运行的后台服务
- 系统自动调用的存储过程
- 不需要优化的系统任务

---

## 📚 参考链接

- [SQL Server CDC 官方文档](https://learn.microsoft.com/sql/relational-databases/track-changes/about-change-data-capture-sql-server)
- [sp_server_diagnostics 文档](https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/sp-server-diagnostics-transact-sql)
- [AlwaysOn 可用性组监控](https://learn.microsoft.com/sql/database-engine/availability-groups/windows/monitoring-of-availability-groups-sql-server)

---

**更新时间**: 2026-01-27 20:30
**最后更新**: 添加 sp_server_diagnostics 系统健康检查过滤
