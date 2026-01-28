# SQL Server 慢SQL监控完整实现

## 完成时间
2026-01-26

## 问题描述
1. SQL Server慢SQL监控不显示数据
2. CDC系统作业被误识别为慢SQL
3. 数据库缺少SQL Server特有字段

## 解决方案

### 1. 添加数据库字段

**文件**: `fix_sqlserver_fields.sql`

为 `long_running_sql_log` 表添加了3个SQL Server特有字段:
- `wait_type` VARCHAR(100) - 等待类型（如WAITFOR、PAGEIOLATCH等）
- `wait_resource` VARCHAR(200) - 等待资源
- `query_cost` DECIMAL(15,4) - 查询成本

```sql
ALTER TABLE long_running_sql_log ADD COLUMN wait_type VARCHAR(100) COMMENT '等待类型';
ALTER TABLE long_running_sql_log ADD COLUMN wait_resource VARCHAR(200) COMMENT '等待资源';
ALTER TABLE long_running_sql_log ADD COLUMN query_cost DECIMAL(15,4) COMMENT '查询成本';
ALTER TABLE long_running_sql_log ADD INDEX idx_wait_type (wait_type);
```

### 2. 过滤CDC和系统作业

**文件**: `scripts/sqlserver_collector.py` (行93-95)
**文件**: `app_new.py` (行1442-1444)

在SQL Server慢SQL查询中添加了过滤条件:

```sql
WHERE r.session_id != @@SPID
  AND r.total_elapsed_time > ?
  AND t.text IS NOT NULL
  AND t.text NOT LIKE '%sp_server_diagnostics%'  -- 过滤诊断存储过程
  AND t.text NOT LIKE '%sp_cdc_%'                -- 过滤CDC作业
  AND (s.program_name NOT LIKE '%SQLAgent%' OR s.program_name IS NULL)  -- 过滤代理作业
```

这样可以过滤掉以下系统进程:
- SQL Server诊断进程 (sp_server_diagnostics)
- CDC变更数据捕获作业 (sp_cdc_scan, sp_cdc_cleanup等)
- SQL Server代理作业

### 3. 更新ODBC驱动

**修改文件**:
- `scripts/sqlserver_collector.py` (行40)
- `app_new.py` (行704, 1413, 1539)

从 "SQL Server" 驱动更新为 "ODBC Driver 18 for SQL Server":

```python
conn_str = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={db_ip},{db_port};"
    f"UID={db_user};"
    f"PWD={db_password};"
    f"Encrypt=no;"
    f"TrustServerCertificate=yes;"
    f"Timeout=5;"
)
```

### 4. 修复类型转换错误

**文件**: `scripts/sqlserver_collector.py` (行115-116)

SQL Server返回的elapsed_time是Decimal类型，需要显式转换:

```python
'elapsed_seconds': float(elapsed_seconds),
'elapsed_minutes': float(elapsed_seconds) / 60.0,
```

## 测试验证

### 测试1: 连接测试
**文件**: `test_sqlserver_connection.py`
- ✓ 成功连接SQL Server
- ✓ 查询版本信息
- ✓ 执行慢SQL查询

### 测试2: 采集和保存测试
**文件**: `test_sqlserver_collect_and_save.py`
- ✓ 采集慢SQL数据
- ✓ 保存到数据库
- ✓ 验证数据完整性

### 测试3: 慢查询实际测试
**文件**: `test_sqlserver_slow_query.py`
- ✓ 执行WAITFOR DELAY慢查询
- ✓ 成功采集到慢SQL（排除CDC作业）
- ✓ wait_type、wait_resource字段正确保存
- ✓ 数据库中可查询到记录

**测试结果**:
```
[OK] 采集到 1 条慢SQL
会话ID=222, 运行时长=0.03分钟
用户=sa, 主机=CHINAMI-QK93JK3
等待类型=WAITFOR, 等待资源=
SQL: WAITFOR DELAY '00:00:10'; SELECT 1 as result
```

## 功能特性

### SQL Server采集的指标

1. **基础信息**:
   - session_id: 会话ID
   - username: 登录用户
   - machine: 客户端主机名
   - program: 应用程序名称
   - database_name: 数据库名

2. **执行信息**:
   - elapsed_seconds: 运行时长（秒）
   - elapsed_minutes: 运行时长（分钟）
   - cpu_time: CPU时间
   - status: 状态（ACTIVE/SUSPENDED等）

3. **等待信息** (SQL Server特有):
   - wait_type: 等待类型（WAITFOR/PAGEIOLATCH/CXPACKET等）
   - wait_time: 等待时间
   - wait_resource: 等待资源

4. **性能信息**:
   - logical_reads: 逻辑读取
   - physical_reads: 物理读取
   - rows_sent: 返回行数
   - query_cost: 查询成本
   - execution_plan: 执行计划（XML格式）

5. **阻塞信息**:
   - blocking_session: 阻塞会话ID

6. **索引分析**:
   - index_used: 使用的索引
   - full_table_scan: 是否全表扫描

## API端点支持

### /api/realtime_sql
现在支持SQL Server实例的实时慢SQL查询:
- 自动识别SQL Server实例
- 使用pyodbc连接
- 过滤系统作业
- 返回格式与MySQL统一

### /api/longsql
可以查询历史SQL Server慢SQL记录:
- 支持按实例过滤
- 支持按时长过滤（min_minutes参数）
- 显示SQL Server特有的wait_type等信息

## 使用方法

### 1. 配置SQL Server实例
在数据库 `db_instance_info` 表中添加SQL Server实例:
```sql
INSERT INTO db_instance_info (db_project, db_ip, db_port, db_user, db_password, db_type, status)
VALUES ('测试SQL Server', '192.168.1.100', 1433, 'sa', 'password', 'SQLServer', 1);
```

### 2. 启动采集器
```bash
python scripts/collector_enhanced.py --interval 10
```

### 3. 查看监控数据
- 浏览器访问监控面板
- 点击"Long SQL"标签
- 选择SQL Server实例
- 查看慢SQL列表

## 已修复的问题

1. ✓ SQL Server慢SQL不显示 - 已修复ODBC驱动和API支持
2. ✓ CDC作业误报 - 已添加系统作业过滤
3. ✓ 字段缺失错误 - 已添加wait_type、wait_resource、query_cost字段
4. ✓ 类型转换错误 - 已修复Decimal类型处理
5. ✓ 无法保存数据 - 数据库schema已更新

## 技术要点

### SQL Server特有的监控机制

1. **DMV (Dynamic Management Views)**:
   - `sys.dm_exec_requests`: 当前执行的请求
   - `sys.dm_exec_sessions`: 会话信息
   - `sys.dm_exec_sql_text`: SQL文本
   - `sys.dm_exec_query_plan`: 执行计划

2. **等待类型 (Wait Types)**:
   SQL Server特有的性能诊断指标，常见类型:
   - WAITFOR: 显式等待
   - PAGEIOLATCH_*: 页面I/O等待
   - CXPACKET: 并行查询等待
   - LCK_*: 锁等待

3. **执行计划解析**:
   解析XML格式的查询计划，提取:
   - 成本 (StatementSubTreeCost)
   - 预估行数 (StatementEstRows)
   - 索引使用情况
   - 是否全表扫描

### 系统作业识别

SQL Server的系统作业通常包括:
- `sp_server_diagnostics`: 健康检查
- `sp_cdc_scan`: CDC扫描作业
- `sp_cdc_cleanup`: CDC清理作业
- SQLAgent作业: program_name包含"SQLAgent"

这些作业长期运行是正常的，不应该被识别为慢SQL。

## 后续优化建议

1. **增强过滤规则**:
   - 添加白名单机制，允许用户自定义排除规则
   - 按database_name过滤系统数据库

2. **性能优化**:
   - 限制返回TOP N条记录
   - 缓存执行计划解析结果

3. **监控增强**:
   - 添加死锁监控 (已实现check_deadlocks方法)
   - 添加阻塞监控 (已实现get_current_blocks方法)

4. **UI改进**:
   - 在前端显示wait_type等SQL Server特有字段
   - 添加执行计划可视化

## 完成状态

✅ SQL Server慢SQL监控已完全实现并测试通过
✅ CDC系统作业过滤正常工作
✅ 所有字段完整保存
✅ 可在监控面板查看SQL Server慢SQL
