# 数据库监控系统 - 功能更新日志 v2.0

**更新日期**: 2026-01-26
**版本号**: v2.0.0
**更新类型**: 重大功能增强

---

## 🎉 本次更新概述

本次更新完成了数据库监控系统从v1.1到v2.0的重大升级，新增7大核心功能模块，大幅提升了系统的实用性和易用性。所有功能均已完成开发、测试和集成。

---

## ✅ 新增功能清单

### 1. SQL详情弹窗功能 ⭐⭐⭐⭐⭐

**功能描述**：点击SQL列表中的"详情"按钮，弹出完整的SQL详情信息窗口

**包含内容**：
- ✅ 完整SQL文本显示（不截断）
- ✅ 会话详细信息（会话ID、用户、客户端）
- ✅ 性能指标展示（扫描行数、返回行数、CPU时间、全表扫描标记）
- ✅ 索引使用情况
- ✅ 执行计划可视化展示
- ✅ Kill会话按钮（只有ACTIVE状态显示）

**实现文件**：
- `app_new.py`: 新增API `/api/long_sql/<int:sql_id>` (app_new.py:833-865)
- `static/index.html`: Modal组件 (index.html:506-601)，JavaScript函数 showSqlDetail() (index.html:1118-1182)

**使用场景**：运维人员快速查看慢SQL的完整信息，分析性能问题

---

### 2. 执行计划自动采集 ⭐⭐⭐⭐⭐

**功能描述**：在检测到慢SQL时，自动执行EXPLAIN获取执行计划并存储

**采集内容**：
- ✅ MySQL EXPLAIN分析结果
- ✅ 索引使用情况（key字段）
- ✅ 全表扫描检测（type=ALL）
- ✅ 预估扫描行数
- ✅ Extra信息（Using filesort, Using temporary等）

**实现文件**：
- `scripts/collector_enhanced.py`: get_explain() 方法 (collector_enhanced.py:265-303)
- 数据库字段：`execution_plan` (JSON), `index_used`, `full_table_scan`

**技术细节**：
- 只对SELECT语句执行EXPLAIN
- 自动切换到正确的数据库
- 执行计划以JSON格式存储
- 前端自动格式化为表格展示

**使用场景**：自动化性能分析，无需手动执行EXPLAIN

---

### 3. Kill会话功能 ⭐⭐⭐⭐

**功能描述**：直接从监控界面终止长时间运行的SQL会话

**功能特性**：
- ✅ 支持MySQL：`KILL <session_id>`
- ✅ 支持SQL Server：`KILL <spid>`
- ✅ 确认对话框（防止误操作）
- ✅ 操作日志记录
- ✅ 实时监控页面集成Kill按钮

**实现文件**：
- `app_new.py`: API `/api/kill_session` (app_new.py:983-1053)
- `static/index.html`: killSession()函数 (index.html:1214-1242)

**安全措施**：
- 二次确认对话框
- 显示SQL预览（前100字符）
- 操作日志记录到服务器

**使用场景**：紧急处理慢SQL，释放数据库资源

---

### 4. SQL指纹和去重 ⭐⭐⭐⭐

**功能描述**：自动生成SQL指纹（去参数化），方便识别相同模板的SQL

**去参数化规则**：
- ✅ 数字替换为 `?`
- ✅ 字符串替换为 `?`
- ✅ IN子句替换为 `IN (?)`
- ✅ MD5哈希生成指纹

**示例**：
```sql
原始SQL: SELECT * FROM users WHERE id = 123 AND name = 'John'
指纹SQL: select * from users where id = ? and name = ?
MD5:     a1b2c3d4e5f6...
```

**实现文件**：
- `scripts/collector_enhanced.py`: get_sql_fingerprint() 函数 (collector_enhanced.py:93-112)
- 数据库字段：`sql_fingerprint` (VARCHAR(64))

**应用场景**：
- 识别重复执行的SQL模板
- 告警去重（避免相同SQL重复告警）
- 性能趋势分析

---

### 5. 性能指标采集 ⭐⭐⭐

**功能描述**：从performance_schema采集详细的性能指标

**采集指标**：
- ✅ CPU时间（`cpu_time`）
- ✅ 等待时间（`wait_time`）
- ✅ 逻辑读（`logical_reads`）
- ✅ 物理读（`physical_reads`）
- ✅ 扫描行数（`rows_examined`）
- ✅ 返回行数（`rows_sent`）
- ✅ 查询成本（`query_cost`）

**实现文件**：
- `scripts/collector_enhanced.py`: get_performance_metrics() 方法 (collector_enhanced.py:226-263)

**数据来源**：
- MySQL: `performance_schema.events_statements_current`
- SQL Server: `sys.dm_exec_requests`

**使用场景**：深度性能分析，识别资源消耗大户

---

### 6. 告警历史记录 ⭐⭐⭐

**功能描述**：记录所有告警历史，实现告警间隔控制，避免重复告警

**核心功能**：
- ✅ 告警历史记录表（`alert_history`）
- ✅ 告警间隔控制（默认30分钟）
- ✅ 告警类型标记（slow_sql/deadlock）
- ✅ 告警级别（WARNING/CRITICAL）
- ✅ 告警标识符（SQL指纹/死锁时间）

**实现文件**：
- `scripts/collector_enhanced.py`:
  - should_send_alert() 函数 (collector_enhanced.py:467-496)
  - save_alert_history() 函数 (collector_enhanced.py:499-525)
- `scripts/init_database.sql`: alert_history表 (init_database.sql:145-164)

**告警逻辑**：
1. 检测到需要告警的事件
2. 查询alert_history表，检查30分钟内是否已发送
3. 如果未发送过，则发送告警
4. 记录到alert_history表

**使用场景**：
- 避免告警风暴
- 告警审计追溯
- 告警统计分析

---

### 7. 实时监控仪表板 ⭐⭐⭐

**功能描述**：显示当前正在运行的SQL，支持实时刷新和Kill操作

**核心特性**：
- ✅ 实时查询当前活动SQL
- ✅ 5秒自动刷新（可开关）
- ✅ 统计信息（活动SQL数、最长执行时间、阻塞会话）
- ✅ 实例过滤
- ✅ 最小执行时间过滤
- ✅ 一键Kill会话

**实现文件**：
- `app_new.py`: API `/api/realtime_sql` (app_new.py:983-1090)
- `static/index.html`:
  - 实时监控页面 (index.html:253-309)
  - loadRealtimeSQL()函数 (index.html:1487-1550)
  - 自动刷新功能 (index.html:1575-1587)

**技术实现**：
- 直接连接目标数据库实例
- 查询`information_schema.processlist`
- 定时器每5秒刷新
- 支持多实例并发查询

**使用场景**：
- 实时监控数据库活动
- 快速定位当前慢SQL
- 紧急处理性能问题

---

## 📊 数据库表结构变更

### 修改表：`alert_history`

新增字段：
```sql
alert_type VARCHAR(50) NOT NULL COMMENT '告警类型(slow_sql/deadlock)'
alert_identifier VARCHAR(200) COMMENT '告警标识符(SQL指纹/死锁时间)'
```

新增索引：
```sql
INDEX idx_alert_type (alert_type)
INDEX idx_alert_identifier (alert_identifier)
```

### 已存在字段（本次利用）：
- `long_running_sql_log.sql_fingerprint` - SQL指纹
- `long_running_sql_log.sql_fulltext` - 完整SQL文本
- `long_running_sql_log.execution_plan` - 执行计划JSON
- `long_running_sql_log.index_used` - 使用的索引
- `long_running_sql_log.full_table_scan` - 全表扫描标记
- `long_running_sql_log.cpu_time` - CPU时间
- `long_running_sql_log.rows_examined` - 扫描行数
- `long_running_sql_log.rows_sent` - 返回行数
- `long_running_sql_log.alert_sent` - 告警已发送标记

---

## 🔧 核心代码改动

### 后端改动（app_new.py）

新增API接口：
1. `GET /api/long_sql/<int:sql_id>` - 获取SQL详情
2. `GET /api/realtime_sql` - 获取实时运行SQL
3. `POST /api/kill_session` - 终止会话

### 采集器改动（collector_enhanced.py）

新增函数：
1. `get_sql_fingerprint()` - 生成SQL指纹
2. `get_explain()` - 获取执行计划
3. `get_performance_metrics()` - 获取性能指标
4. `should_send_alert()` - 告警间隔控制
5. `save_alert_history()` - 保存告警历史

### 前端改动（static/index.html）

新增页面：
1. 实时监控页面（page-realtime）

新增Modal：
1. 增强的SQL详情弹窗（sqlModal）

新增JavaScript函数：
1. `showSqlDetail()` - 显示SQL详情
2. `killSession()` - 终止会话
3. `loadRealtimeSQL()` - 加载实时SQL
4. `killRealtimeSession()` - 实时监控Kill会话
5. `toggleRealtimeRefresh()` - 切换自动刷新
6. `formatExecutionPlan()` - 格式化执行计划
7. `formatNumber()` - 数字格式化

---

## 🚀 部署说明

### 1. 数据库升级

执行以下SQL更新alert_history表结构：

```sql
ALTER TABLE alert_history
ADD COLUMN alert_type VARCHAR(50) NOT NULL COMMENT '告警类型(slow_sql/deadlock)' AFTER db_instance_id,
ADD COLUMN alert_identifier VARCHAR(200) COMMENT '告警标识符' AFTER alert_type,
ADD INDEX idx_alert_type (alert_type),
ADD INDEX idx_alert_identifier (alert_identifier);
```

或重新运行完整初始化脚本：
```bash
mysql -u root -p db_monitor < scripts/init_database.sql
```

### 2. 重启采集器

```bash
# 停止旧采集器
pkill -f collector_enhanced.py

# 启动新采集器
cd /c/运维工具类/database-monitor
python scripts/collector_enhanced.py
```

### 3. 重启Web服务

```bash
# 停止旧服务
pkill -f app_new.py

# 启动新服务
python app_new.py
```

### 4. 清除浏览器缓存

强制刷新页面：`Ctrl + F5` 或 `Cmd + Shift + R`

---

## 📝 使用指南

### SQL详情弹窗
1. 进入"监控面板"
2. 点击任意SQL记录的"详情"按钮
3. 查看完整SQL、执行计划、性能指标
4. 如果SQL仍在运行，点击"终止会话"按钮

### 实时监控
1. 点击顶部导航"实时监控"
2. 查看当前所有运行中的SQL
3. 点击"自动刷新(5秒)"开启实时更新
4. 点击"Kill"按钮终止慢SQL

### 告警历史
- 告警会自动记录到`alert_history`表
- 同一SQL指纹在30分钟内不会重复告警
- 可通过SQL查询告警历史：
  ```sql
  SELECT * FROM alert_history
  ORDER BY created_at DESC
  LIMIT 100;
  ```

---

## 🎯 性能优化建议

### MySQL Performance Schema
确保performance_schema已启用：
```sql
SHOW VARIABLES LIKE 'performance_schema';
```

如果未启用，需在my.cnf中添加：
```ini
[mysqld]
performance_schema = ON
```

### 索引优化
系统会自动检测全表扫描，建议根据执行计划添加索引：
```sql
-- 查看最常见的全表扫描SQL
SELECT sql_fingerprint, COUNT(*) as count,
       MAX(elapsed_minutes) as max_time
FROM long_running_sql_log
WHERE full_table_scan = 1
GROUP BY sql_fingerprint
ORDER BY count DESC
LIMIT 10;
```

---

## ⚠️ 注意事项

1. **Kill会话操作不可撤销**，请谨慎使用
2. **实时监控**会直接连接业务数据库，确保监控账号有足够权限
3. **告警间隔**默认30分钟，可在代码中调整
4. **执行计划**只对SELECT语句有效
5. **Performance Schema**可能对性能有轻微影响

---

## 📈 后续计划

- [ ] SQL优化建议（基于执行计划自动生成）
- [ ] SQL执行趋势分析（同一指纹的历史趋势）
- [ ] 报表导出（Excel/PDF）
- [ ] WebSocket实时推送（替代轮询）
- [ ] 更多数据库支持（PostgreSQL, Oracle）

---

## 🙏 致谢

感谢所有使用和反馈的用户！

**文档生成时间**: 2026-01-26
**系统版本**: v2.0.0
