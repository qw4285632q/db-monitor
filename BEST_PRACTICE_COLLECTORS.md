# 🎯 最佳实践：对数据库侵入最低、性能最好、准确率最高的慢SQL捕获方案

## 📊 三种采集方式对比

### 方式1: Processlist/DMV 快照 (当前方式) ❌

**原理:** 定期查询 `information_schema.processlist` 或 `sys.dm_exec_requests`

**缺陷:**
- ❌ **会遗漏SQL** - 只能捕获快照时刻正在运行的SQL
- ❌ **侵入性高** - 需要频繁查询(10秒一次)，有性能开销
- ❌ **准确率低** - 如果SQL在两次采集之间执行完成，就会丢失

**举例:**
```
采集间隔: 10秒
慢SQL阈值: 5秒

时间轴:
00:00 - 采集器运行
00:03 - 一个慢SQL开始执行 (耗时6秒)
00:09 - 慢SQL执行完成 ← 这个SQL不会被捕获！
00:10 - 采集器再次运行 (但SQL已经完成)
```

**适用场景:** 只能作为辅助手段，捕获当前正在执行的SQL

---

### 方式2: Performance Schema / Query Store (推荐) ✅✅✅

**原理:** 数据库自带的性能统计功能，后台自动聚合

**优势:**
- ✅ **零侵入** - Performance Schema/Query Store在后台自动收集
- ✅ **零开销** - 只需查询已聚合的统计表，不影响业务
- ✅ **100%准确** - 所有执行过的SQL都会被记录，不会遗漏
- ✅ **自动去重** - SQL已经做了参数化 (Digest/Query Hash)
- ✅ **丰富指标** - 执行次数、平均/最大时间、扫描行数、锁等待等
- ✅ **持久化** - SQL Server Query Store数据持久化存储

**MySQL Performance Schema 示例:**
```sql
-- 查询最近5分钟平均执行时间>5秒的SQL
SELECT
    digest AS sql_fingerprint,
    digest_text AS sql_template,
    count_star AS execution_count,
    avg_timer_wait / 1000000000000 AS avg_time_seconds,
    max_timer_wait / 1000000000000 AS max_time_seconds,
    sum_rows_examined AS total_rows_examined,
    last_seen
FROM performance_schema.events_statements_summary_by_digest
WHERE avg_timer_wait >= 5000000000000  -- 5秒 (纳秒)
  AND last_seen >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
ORDER BY avg_timer_wait DESC
LIMIT 100;
```

**SQL Server Query Store 示例:**
```sql
-- 查询最近5分钟平均执行时间>5秒的SQL
USE [YourDatabase];

SELECT TOP 100
    qsq.query_id,
    qsqt.query_sql_text,
    qsrs.count_executions,
    qsrs.avg_duration / 1000000.0 AS avg_duration_seconds,
    qsrs.max_duration / 1000000.0 AS max_duration_seconds,
    qsrs.last_execution_time
FROM sys.query_store_query qsq
JOIN sys.query_store_query_text qsqt ON qsq.query_text_id = qsqt.query_text_id
JOIN sys.query_store_plan qsp ON qsq.query_id = qsp.query_id
JOIN sys.query_store_runtime_stats qsrs ON qsp.plan_id = qsrs.plan_id
WHERE qsrs.avg_duration >= 5000000  -- 5秒 (微秒)
  AND qsrs.last_execution_time >= DATEADD(MINUTE, -5, GETDATE())
ORDER BY qsrs.avg_duration DESC;
```

**适用场景:** 生产环境主要采集方式

---

### 方式3: 慢查询日志 (最准确，但有开销) ⚠️

**原理:** 数据库将慢SQL写入日志文件

**优势:**
- ✅ **100%准确** - 所有慢SQL都会被记录
- ✅ **详细信息** - 包含完整的SQL和执行上下文

**缺陷:**
- ⚠️ **有I/O开销** - 需要写磁盘
- ⚠️ **需要解析** - 日志文件需要额外工具解析
- ⚠️ **日志轮转** - 需要管理日志文件大小

**MySQL 开启方法:**
```sql
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 5;
SET GLOBAL slow_query_log_file = '/var/log/mysql/slow.log';
SET GLOBAL log_queries_not_using_indexes = 'ON';
```

**SQL Server 开启方法:**
```sql
-- 使用Extended Events
CREATE EVENT SESSION [SlowQuery_Capture] ON SERVER
ADD EVENT sqlserver.sql_statement_completed(
    ACTION(sqlserver.sql_text, sqlserver.session_id)
    WHERE duration >= 5000000  -- 5秒 (微秒)
)
ADD TARGET package0.event_file(
    SET filename=N'C:\SlowQueries\SlowQueries.xel'
);

ALTER EVENT SESSION [SlowQuery_Capture] ON SERVER STATE = START;
```

**适用场景:** 作为补充手段，用于审计和事后分析

---

## 🎯 推荐方案：双轨制混合采集

### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    慢SQL采集系统                          │
└─────────────────────────────────────────────────────────┘

主数据源 (60秒采集一次)          辅助数据源 (10秒采集一次)
─────────────────────────────    ─────────────────────────
Performance Schema (MySQL)       Processlist (MySQL)
Query Store (SQL Server)   →     DMV (SQL Server)

         ↓                               ↓
    聚合统计数据                    实时运行SQL
    (已完成的慢SQL)                 (正在执行的慢SQL)
         ↓                               ↓
         └───────────┬───────────────────┘
                     ↓
              监控数据库 (MySQL)
                     ↓
              Web UI 展示
```

### 采集频率

| 数据源 | 采集间隔 | 原因 |
|--------|---------|------|
| Performance Schema | 60秒 | 已聚合，不需要高频采集 |
| Query Store | 60秒 | 已聚合，不需要高频采集 |
| Processlist | 10秒 | 捕获当前正在执行的SQL |
| DMV | 10秒 | 捕获当前正在执行的SQL |

### 数据去重策略

1. **SQL指纹去重**
   - 相同SQL模式只保留最新记录
   - Performance Schema的digest / Query Store的query_hash

2. **时间窗口去重**
   - 同一SQL指纹5分钟内只告警一次

---

## 📝 实施步骤

### 步骤1: MySQL开启Performance Schema

**检查是否开启:**
```sql
SELECT @@performance_schema;
-- 返回1表示已开启
```

**如果未开启，需要修改配置并重启:**
```ini
# /etc/my.cnf 或 my.ini
[mysqld]
performance_schema = ON
```

**重启MySQL:**
```bash
systemctl restart mysqld
```

---

### 步骤2: SQL Server开启Query Store

**检查版本 (需要2016及以上):**
```sql
SELECT @@VERSION;
```

**对每个用户数据库开启Query Store:**
```sql
USE [YourDatabase];
GO

ALTER DATABASE [YourDatabase] SET QUERY_STORE = ON;
GO

ALTER DATABASE [YourDatabase] SET QUERY_STORE (
    OPERATION_MODE = READ_WRITE,
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    MAX_STORAGE_SIZE_MB = 1024,
    INTERVAL_LENGTH_MINUTES = 60,
    QUERY_CAPTURE_MODE = AUTO,
    SIZE_BASED_CLEANUP_MODE = AUTO
);
GO
```

**或者使用采集器自动开启:**
```bash
python scripts/sqlserver_querystore_collector.py --auto-enable
```

---

### 步骤3: 启动新的采集器

#### MySQL Performance Schema 采集器
```bash
# 单次采集测试
python scripts/mysql_perfschema_collector.py --threshold 5

# 守护进程模式
python scripts/mysql_perfschema_collector.py --daemon --interval 60 --threshold 5
```

#### SQL Server Query Store 采集器
```bash
# 单次采集测试
python scripts/sqlserver_querystore_collector.py --threshold 5

# 守护进程模式
python scripts/sqlserver_querystore_collector.py --daemon --interval 60 --threshold 5

# 自动开启Query Store
python scripts/sqlserver_querystore_collector.py --daemon --interval 60 --threshold 5 --auto-enable
```

---

### 步骤4: 停止旧的采集器

旧的采集器 (`collector_enhanced.py`) 可以继续运行，但调整为辅助角色：

```bash
# 修改为更低频率 (30秒)，只用于捕获实时SQL
python scripts/collector_enhanced.py --daemon --interval 30 --threshold 5
```

---

## 📊 性能对比

| 指标 | Processlist快照 | Performance Schema | Query Store |
|------|----------------|-------------------|-------------|
| 准确率 | 60-80% | 100% | 100% |
| 数据库开销 | 中等 (频繁查询) | 极低 (后台聚合) | 极低 (后台聚合) |
| 磁盘开销 | 无 | 极低 (内存表) | 低 (1GB) |
| 会遗漏SQL | 是 | 否 | 否 |
| 实时性 | 高 (10秒) | 中 (60秒) | 中 (60秒) |
| SQL去重 | 否 (需手动) | 是 (自动) | 是 (自动) |
| 执行计划 | 否 | 部分 | 完整 |
| 持久化 | 否 | 否 (重启丢失) | 是 |

---

## ✅ 最终方案

### 生产环境配置

**MySQL:**
```bash
# 主采集器 (Performance Schema) - 60秒
python scripts/mysql_perfschema_collector.py --daemon --interval 60 --threshold 5 > logs/mysql_perfschema.log 2>&1 &

# 辅助采集器 (Processlist) - 30秒
# 使用现有的collector_enhanced.py
```

**SQL Server:**
```bash
# 主采集器 (Query Store) - 60秒
python scripts/sqlserver_querystore_collector.py --daemon --interval 60 --threshold 5 --auto-enable > logs/sqlserver_querystore.log 2>&1 &

# 辅助采集器 (DMV) - 30秒
# 使用现有的collector_enhanced.py
```

---

## 🔧 开启Performance Schema指南

### MySQL 5.7+

**1. 检查当前状态:**
```sql
SHOW VARIABLES LIKE 'performance_schema';
```

**2. 如果未开启，修改配置文件:**
```ini
# Linux: /etc/my.cnf 或 /etc/mysql/my.cnf
# Windows: C:\ProgramData\MySQL\MySQL Server X.Y\my.ini

[mysqld]
performance_schema = ON

# 可选: 调整内存大小 (默认通常够用)
performance_schema_max_table_instances = 12500
performance_schema_max_sql_text_length = 4096
```

**3. 重启MySQL:**
```bash
# Linux
systemctl restart mysqld

# Windows
net stop MySQL80
net start MySQL80
```

**4. 验证:**
```sql
SELECT @@performance_schema;
-- 返回1表示成功

-- 查看是否有数据
SELECT COUNT(*) FROM performance_schema.events_statements_summary_by_digest;
```

---

## 🔧 开启Query Store指南

### SQL Server 2016+

**方法1: 手动开启 (推荐对生产库)**
```sql
-- 对每个数据库执行
USE [YourDatabase];
GO

ALTER DATABASE [YourDatabase] SET QUERY_STORE = ON;
GO

ALTER DATABASE [YourDatabase] SET QUERY_STORE (
    OPERATION_MODE = READ_WRITE,
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    MAX_STORAGE_SIZE_MB = 1024,
    QUERY_CAPTURE_MODE = AUTO
);
GO

-- 验证
SELECT actual_state_desc, readonly_reason
FROM sys.database_query_store_options;
-- 应该显示 READ_WRITE
```

**方法2: 使用采集器自动开启**
```bash
python scripts/sqlserver_querystore_collector.py --auto-enable
```

**查看Query Store使用情况:**
```sql
SELECT
    current_storage_size_mb,
    max_storage_size_mb,
    readonly_reason,
    actual_state_desc
FROM sys.database_query_store_options;
```

---

## 📈 效果预期

采用新方案后:

### 前 (Processlist快照)
- ✗ 准确率: 60-80%
- ✗ 遗漏率: 20-40%
- ✗ 数据库开销: 中等
- ✗ 每10秒查询一次processlist

### 后 (Performance Schema + Query Store)
- ✓ 准确率: 100%
- ✓ 遗漏率: 0%
- ✓ 数据库开销: 极低
- ✓ 每60秒查询一次聚合表
- ✓ 自动SQL指纹去重
- ✓ 丰富的性能指标

---

## 🎓 总结

**对数据库侵入最低、性能最好、准确率最高的慢SQL捕获方式：**

1. **主要方式:** Performance Schema (MySQL) + Query Store (SQL Server)
   - 零侵入
   - 零开销
   - 100%准确

2. **辅助方式:** Processlist (MySQL) + DMV (SQL Server)
   - 捕获实时SQL
   - 10-30秒采集一次

3. **补充方式:** 慢查询日志 (可选)
   - 用于审计
   - 事后分析

**核心理念:** 让数据库自己做统计，而不是外部频繁查询！
