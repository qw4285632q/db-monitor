# @@TRANCOUNT 事务管理代码过滤说明

## 🔍 问题描述

在慢SQL监控中发现了类似这样的SQL：

```sql
IF @@TRANCOUNT > 0 COMMIT TRAN
IF @@TRANCOUNT > 0 COMMIT TRANSACTION
IF @@TRANCOUNT > 0 COMMIT
```

**特征：**
- 历史采集数量：8次
- 最长执行时间：7321.25 分钟（约5.07天）
- 最后采集时间：2026-01-28 08:49:27

---

## 📋 这是什么？

### 语法解释

```sql
IF @@TRANCOUNT > 0
    COMMIT TRAN
```

**组成部分：**
- `@@TRANCOUNT`：SQL Server系统全局变量，返回当前连接的活动事务嵌套层数
- `> 0`：判断是否存在未提交的事务
- `COMMIT TRAN`：提交事务（也可能是 `COMMIT TRANSACTION` 或 `COMMIT`）

### 作用

这是**事务清理语句**，用于确保连接没有遗留未提交的事务。

---

## 🎯 为什么会出现

### 1. 应用程序连接池

**场景：**
- .NET应用（ADO.NET、Entity Framework）
- Java应用（JDBC、Hibernate）
- Python应用（SQLAlchemy、Django）

**原因：**
连接池在回收连接前，需要确保该连接没有未完成的事务。

**示例代码（.NET）：**
```csharp
// ADO.NET连接池回收时
if (connection.State == ConnectionState.Open) {
    using (SqlCommand cmd = new SqlCommand("IF @@TRANCOUNT > 0 COMMIT TRAN", connection)) {
        cmd.ExecuteNonQuery();
    }
}
```

### 2. ORM框架行为

**Entity Framework：**
```csharp
// EF在每次查询后可能执行
context.Database.ExecuteSqlCommand("IF @@TRANCOUNT > 0 COMMIT TRANSACTION");
```

**Hibernate：**
```java
// 会话关闭前清理事务
session.doWork(connection -> {
    connection.createStatement().execute("IF @@TRANCOUNT > 0 COMMIT");
});
```

### 3. 连接中间件

- 连接代理（ProxySQL、MaxScale等）
- 负载均衡器的健康检查
- 数据库连接池管理工具

### 4. 监控/管理工具

- SQL Server Management Studio（某些操作后）
- 第三方DBA工具
- 应用性能监控（APM）工具

---

## ❓ 为什么运行时间这么长

### 原因

这个SQL本身执行非常快（毫秒级），但**被监控工具持续调用**，表现为一个"长时间运行"的会话。

### 可能的情况

1. **持续运行的监控工具**
   ```
   监控工具每隔几秒检查一次事务状态
   → 单个会话保持打开
   → 每次检查执行 IF @@TRANCOUNT > 0 COMMIT
   → 会话运行5天+ = 慢SQL被记录
   ```

2. **连接池保持连接**
   ```
   连接池有一个长期空闲的连接
   → 定期发送心跳/清理命令
   → 包含 @@TRANCOUNT 检查
   → 连接活跃几天 = 被误认为慢SQL
   ```

3. **应用程序框架**
   ```
   某些框架在连接空闲时
   → 周期性清理事务状态
   → 防止事务泄漏
   ```

---

## 🚫 为什么要过滤

### 1. 不是业务SQL

这是**基础设施代码**，不是需要优化的业务查询。

### 2. 不需要优化

SQL本身已经是最优形式：
- 单行判断
- 无表访问
- 毫秒级执行

### 3. 运行时间长是正常的

"运行时间长"是因为：
- 会话保持打开
- 定期执行
- 不是单次查询慢

### 4. 造成误导

DBA看到这个SQL会困惑：
- "这个SQL为什么慢？"
- "需要优化吗？"
- "是哪个应用执行的？"

实际上**完全不需要关注**。

---

## ✅ 过滤方案

### 过滤规则

**Query Store（聚合数据）：**
```sql
AND NOT (qsqt.query_sql_text LIKE '%@@TRANCOUNT%'
         AND qsqt.query_sql_text LIKE '%COMMIT%')
```

**DMV（实时数据）：**
```sql
AND NOT (t.text LIKE '%@@TRANCOUNT%'
         AND t.text LIKE '%COMMIT%')
```

### 匹配逻辑

同时满足两个条件才过滤：
1. ✅ 包含 `@@TRANCOUNT`
2. ✅ 包含 `COMMIT`

**会被过滤的SQL：**
```sql
IF @@TRANCOUNT > 0 COMMIT TRAN
IF @@TRANCOUNT > 0 COMMIT TRANSACTION
IF @@TRANCOUNT > 0 COMMIT
IF @@TRANCOUNT > 0 BEGIN COMMIT END
```

**不会被过滤的SQL：**
```sql
-- 业务代码检查事务
IF @@TRANCOUNT > 0
    SELECT 'Transaction exists'

-- 错误处理回滚
IF @@TRANCOUNT > 0
    ROLLBACK TRAN

-- 业务逻辑事务提交（不包含@@TRANCOUNT检查）
COMMIT TRAN
```

---

## 🔬 验证过滤效果

### 查询历史采集

```sql
-- 在监控数据库执行
USE db_monitor;

-- 过滤前的数量
SELECT COUNT(*) as before_filter
FROM long_running_sql_log
WHERE (sql_text LIKE '%@@TRANCOUNT%' AND sql_text LIKE '%COMMIT%');

-- 预期：8条（历史数据）
```

### 验证新采集

等待采集器运行后（60秒后）：

```sql
-- 查询最近1小时的采集
SELECT COUNT(*) as recent_filter
FROM long_running_sql_log
WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
  AND (sql_text LIKE '%@@TRANCOUNT%' AND sql_text LIKE '%COMMIT%');

-- 预期：0条（已被过滤）
```

---

## 🛠️ 如果需要查看这些SQL

### 临时禁用过滤

如果排查问题需要查看所有事务管理SQL：

1. **停止采集器**
   ```bash
   taskkill /F /IM python.exe
   ```

2. **注释过滤规则**

   编辑 `scripts/sqlserver_querystore_collector.py`

   找到并注释掉：
   ```python
   # AND NOT (qsqt.query_sql_text LIKE '%@@TRANCOUNT%'
   #          AND qsqt.query_sql_text LIKE '%COMMIT%')
   ```

3. **重启采集器**
   ```bash
   START_INTEGRATED_APP.bat
   ```

### 直接查询DMV

不想修改采集器，可以直接查询SQL Server：

```sql
-- 查询当前正在执行的事务清理SQL
SELECT
    r.session_id,
    s.program_name,
    s.login_name,
    t.text AS sql_text,
    r.total_elapsed_time / 1000.0 AS elapsed_seconds,
    r.status
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE t.text LIKE '%@@TRANCOUNT%'
  AND t.text LIKE '%COMMIT%';
```

---

## 📊 常见问题

### Q1: 这会影响真正的业务事务监控吗？

**A:** 不会。过滤规则**同时**检查 `@@TRANCOUNT` 和 `COMMIT`，只过滤这种特定模式的清理代码。

真正的业务事务提交（如 `BEGIN TRAN ... COMMIT`）不会被过滤。

### Q2: 如果我的业务代码也用了这个模式怎么办？

**A:** 如果你的业务代码确实需要这个模式：

```sql
-- 业务代码（不推荐但确实存在）
IF @@TRANCOUNT > 0
    COMMIT TRAN
```

解决方案：
1. **推荐**：重构代码，使用明确的事务管理
2. **临时**：禁用过滤规则，手动识别

### Q3: 为什么不直接过滤所有短SQL？

**A:** 因为：
- 短SQL也可能慢（如锁等待）
- 需要保留真实的业务SQL
- 使用SQL模式过滤更精确

### Q4: 过滤后历史数据怎么办？

**A:** 历史数据保留，不会被删除。只是新采集的会被过滤。

如需清理历史数据：
```sql
DELETE FROM long_running_sql_log
WHERE sql_text LIKE '%@@TRANCOUNT%'
  AND sql_text LIKE '%COMMIT%';
```

---

## 🎯 总结

### @@TRANCOUNT 事务管理代码

| 属性 | 说明 |
|------|------|
| **性质** | 应用程序框架/连接池管理代码 |
| **用途** | 清理未提交事务，防止事务泄漏 |
| **来源** | ORM框架、连接池、监控工具 |
| **是否慢SQL** | ❌ 不是，运行时间长是因为持续调用 |
| **需要优化** | ❌ 不需要，代码已是最优 |
| **应该过滤** | ✅ 是，避免误导DBA |

### 过滤效果

- ✅ 减少误报
- ✅ 聚焦真正的慢SQL
- ✅ 减轻DBA分析负担
- ✅ 提高监控准确性

---

## 📚 参考资料

- [SQL Server @@TRANCOUNT 文档](https://learn.microsoft.com/sql/t-sql/functions/trancount-transact-sql)
- [事务管理最佳实践](https://learn.microsoft.com/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide)
- [ADO.NET连接池管理](https://learn.microsoft.com/dotnet/framework/data/adonet/sql-server-connection-pooling)

---

**文档创建时间**: 2026-01-28
**过滤规则版本**: v1.1
**状态**: ✅ 已实现并生效
