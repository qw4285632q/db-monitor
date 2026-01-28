# 数据库监控系统 - 技术原理说明

## 目录
- [1. 慢SQL检测原理](#1-慢sql检测原理)
- [2. 死锁检测原理](#2-死锁检测原理)
- [3. 执行计划采集](#3-执行计划采集)
- [4. 告警机制](#4-告警机制)

---

## 1. 慢SQL检测原理

### 1.1 MySQL慢SQL检测

#### 数据源
使用MySQL的系统表 `information_schema.processlist` 和 `information_schema.innodb_trx`

#### 检测逻辑
```sql
SELECT
    p.id as session_id,              -- 会话ID
    p.user as username,               -- 执行用户
    p.host as machine,                -- 客户端机器
    p.db as database_name,            -- 数据库名
    p.time as elapsed_seconds,        -- 已运行时间(秒)
    p.info as sql_text,               -- SQL文本
    t.trx_id,                         -- 事务ID
    t.trx_isolation_level             -- 隔离级别
FROM information_schema.processlist p
LEFT JOIN information_schema.innodb_trx t
    ON t.trx_mysql_thread_id = p.id
WHERE p.command != 'Sleep'            -- 排除休眠连接
  AND p.time >= 60                    -- 阈值: 60秒
  AND p.info IS NOT NULL              -- 有SQL文本
  AND p.id != CONNECTION_ID()         -- 排除自己
ORDER BY p.time DESC
```

#### 工作原理
1. **实时扫描**: 每10秒（可配置）扫描一次processlist
2. **时间过滤**: 只捕获运行时间 >= 阈值的SQL
3. **会话关联**: 关联事务表获取事务ID、隔离级别等信息
4. **SQL指纹**: 对SQL进行去参数化，生成MD5指纹，用于聚合统计

**SQL指纹示例:**
```python
原始SQL: SELECT * FROM users WHERE id = 123 AND name = 'Alice'
指纹SQL: SELECT * FROM users WHERE id = ? AND name = ?
指纹值: MD5("select * from users where id = ? and name = ?")
```

#### 优点
- ✅ 实时性高：捕获正在运行的慢SQL
- ✅ 无需开启慢查询日志
- ✅ 可获取事务上下文信息
- ✅ 不依赖文件解析

#### 局限性
- ⚠️ 只能捕获运行时被采样到的SQL
- ⚠️ 对于运行时间短于采集间隔的SQL可能漏采

---

### 1.2 SQL Server慢SQL检测

#### 数据源
使用SQL Server的动态管理视图(DMV):
- `sys.dm_exec_requests` - 当前请求信息
- `sys.dm_exec_sql_text()` - SQL文本
- `sys.dm_exec_query_plan()` - 执行计划
- `sys.dm_exec_sessions` - 会话信息

#### 检测逻辑
```sql
SELECT
    r.session_id,
    s.login_name as username,
    s.host_name as machine,
    s.program_name as program,
    r.total_elapsed_time / 1000.0 as elapsed_seconds,  -- 毫秒转秒
    t.text as sql_text,                                 -- SQL文本
    r.cpu_time / 1000.0 as cpu_time_sec,               -- CPU时间
    r.wait_type,                                        -- 等待类型
    r.wait_resource,                                    -- 等待资源
    r.logical_reads,                                    -- 逻辑读
    r.row_count as rows_sent,                          -- 影响行数
    qp.query_plan                                       -- 执行计划(XML)
FROM sys.dm_exec_requests r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
LEFT JOIN sys.dm_exec_sessions s
    ON r.session_id = s.session_id
OUTER APPLY sys.dm_exec_query_plan(r.plan_handle) qp
WHERE r.session_id != @@SPID                           -- 排除自己
  AND r.total_elapsed_time > 60000                     -- 阈值: 60秒(毫秒)
  AND t.text IS NOT NULL
ORDER BY r.total_elapsed_time DESC
```

#### 工作原理
1. **DMV查询**: 查询sys.dm_exec_requests获取当前活跃请求
2. **文本提取**: 使用CROSS APPLY获取完整SQL文本
3. **计划提取**: 获取XML格式的查询执行计划
4. **等待分析**: 记录wait_type和wait_resource，便于性能诊断

#### 优点
- ✅ 信息丰富：CPU时间、等待类型、IO统计等
- ✅ 执行计划完整：XML格式包含所有算子信息
- ✅ 阻塞检测：可识别blocking_session_id

---

## 2. 死锁检测原理

### 2.1 MySQL死锁检测

#### 数据源
`SHOW ENGINE INNODB STATUS` 命令输出

#### 检测逻辑
```python
# 执行命令
cursor.execute("SHOW ENGINE INNODB STATUS")
result = cursor.fetchone()
status_text = result['Status']

# 从输出中查找死锁部分
deadlock_section = extract_section(status_text,
    start="LATEST DETECTED DEADLOCK",
    end="----"
)
```

#### 死锁信息示例
```
------------------------
LATEST DETECTED DEADLOCK
------------------------
2026-01-26 13:45:30 0x7f1234567890
*** (1) TRANSACTION:
TRANSACTION 12345, ACTIVE 5 sec starting index read
mysql tables in use 1, locked 1
LOCK WAIT 2 lock struct(s), heap size 1136, 1 row lock(s)
MySQL thread id 123, OS thread handle 0x7f123, query id 456 localhost root updating
UPDATE orders SET status = 1 WHERE id = 100

*** (2) TRANSACTION:
TRANSACTION 12346, ACTIVE 3 sec starting index read
mysql tables in use 1, locked 1
3 lock struct(s), heap size 1136, 2 row lock(s)
MySQL thread id 124, OS thread handle 0x7f124, query id 457 localhost root updating
UPDATE products SET stock = stock - 1 WHERE id = 50

*** WE ROLL BACK TRANSACTION (1)
```

#### 解析步骤
1. **正则匹配**: 使用正则表达式提取死锁区域
2. **时间提取**: 提取死锁发生时间 `\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}`
3. **事务解析**: 分别提取两个事务的信息
   - 事务ID: `TRANSACTION (\d+)`
   - SQL文本: `query:\s*(.+?)(?=\*\*\*)`
4. **资源解析**: 提取锁等待资源和锁模式

```python
def parse_deadlock_from_status(status_text: str) -> List[Dict]:
    # 1. 找到LATEST DETECTED DEADLOCK区域
    deadlock_match = re.search(
        r'LATEST DETECTED DEADLOCK\s*\n-+\s*\n(.*?)(?=\n-{5,}|\Z)',
        status_text,
        re.DOTALL | re.IGNORECASE
    )

    # 2. 提取时间
    time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', deadlock_section)

    # 3. 提取事务信息(受害者和阻塞者)
    transactions = re.findall(
        r'TRANSACTION\s+(\d+).*?query:\s*(.+?)(?=\*\*\*|\Z)',
        deadlock_section,
        re.DOTALL | re.IGNORECASE
    )

    return {
        'victim_trx_id': transactions[0][0],
        'victim_sql': transactions[0][1],
        'blocker_trx_id': transactions[1][0],
        'blocker_sql': transactions[1][1],
        'deadlock_time': deadlock_time
    }
```

#### 工作原理
1. **InnoDB维护**: InnoDB引擎自动记录最近一次死锁
2. **主动拉取**: 监控程序定期执行SHOW ENGINE INNODB STATUS
3. **增量检测**: 通过比对死锁时间判断是否为新死锁
4. **自动告警**: 检测到新死锁立即触发告警

#### 优点
- ✅ 无需额外配置
- ✅ 包含完整的锁等待图
- ✅ 有事务回滚信息

#### 局限性
- ⚠️ 只保留最近一次死锁
- ⚠️ 多个死锁可能只记录最后一个
- ⚠️ 需要定期轮询，可能延迟

---

### 2.2 SQL Server死锁检测

#### 数据源
SQL Server Extended Events (系统健康会话)

#### 检测逻辑
```sql
SELECT TOP 10
    CAST(event_data AS XML) as event_xml
FROM sys.fn_xe_file_target_read_file(
    'system_health*.xel',              -- 系统健康事件文件
    NULL, NULL, NULL
)
WHERE object_name = 'xml_deadlock_report'  -- 死锁报告事件
ORDER BY file_name DESC, file_offset DESC
```

#### 死锁XML格式示例
```xml
<deadlock>
  <victim-list>
    <victimProcess id="process123"/>
  </victim-list>
  <process-list>
    <process id="process123" taskpriority="0" logused="1000"
             waittime="5000" xactid="12345">
      <executionStack>
        <frame procname="dbo.UpdateOrder" line="42">
          UPDATE Orders SET Status = 1 WHERE OrderId = @Id
        </frame>
      </executionStack>
      <inputbuf>
        UPDATE Orders SET Status = 1 WHERE OrderId = 100
      </inputbuf>
    </process>
    <process id="process124" ...>
      <inputbuf>
        UPDATE Products SET Stock = Stock - 1 WHERE ProductId = 50
      </inputbuf>
    </process>
  </process-list>
  <resource-list>
    <objectlock lockPartition="0" objid="245575913"
                mode="X" objectname="Orders">
      <owner-list>
        <owner id="process124"/>
      </owner-list>
      <waiter-list>
        <waiter id="process123" mode="X"/>
      </waiter-list>
    </objectlock>
  </resource-list>
</deadlock>
```

#### 解析步骤
```python
def parse_deadlock_xml(xml_str: str) -> Dict:
    root = ET.fromstring(xml_str)

    # 1. 提取时间戳
    timestamp = root.find('.//timestamp').text

    # 2. 提取进程列表
    processes = root.findall('.//process-list/process')
    victim = processes[0]
    blocker = processes[1]

    # 3. 提取SQL文本
    victim_sql = victim.find('.//inputbuf').text
    blocker_sql = blocker.find('.//inputbuf').text

    # 4. 提取资源信息
    resource = root.find('.//resource-list/*')
    wait_resource = resource.get('objectname')
    lock_mode = resource.get('mode')

    return {
        'deadlock_time': timestamp,
        'victim_session_id': victim.get('id'),
        'victim_sql': victim_sql,
        'blocker_session_id': blocker.get('id'),
        'blocker_sql': blocker_sql,
        'wait_resource': wait_resource,
        'lock_mode': lock_mode
    }
```

#### 工作原理
1. **Extended Events**: SQL Server自动记录死锁到system_health会话
2. **XEL文件**: 死锁信息持久化到.xel文件
3. **XML解析**: 使用fn_xe_file_target_read_file读取事件文件
4. **结构化数据**: 解析XML获取完整死锁图

#### 优点
- ✅ 自动记录所有死锁
- ✅ 信息完整：包含锁等待链、存储过程调用栈
- ✅ 持久化存储：不会丢失历史死锁
- ✅ 详细的资源信息：对象名、锁模式、分区ID等

---

## 3. 执行计划采集

### 3.1 MySQL执行计划

#### 采集方法
```sql
EXPLAIN SELECT * FROM users WHERE age > 30 AND city = 'Beijing'
```

#### 解析逻辑
```python
def get_explain(cursor, sql: str) -> Dict:
    # 只对SELECT执行EXPLAIN
    if not sql.strip().upper().startswith('SELECT'):
        return {}

    cursor.execute(f"EXPLAIN {sql}")
    explain_rows = cursor.fetchall()

    total_rows = 0
    indexes = []
    has_full_scan = False

    for row in explain_rows:
        # 累计扫描行数
        total_rows += row.get('rows', 0)

        # 收集使用的索引
        if row.get('key'):
            indexes.append(row['key'])

        # 检测全表扫描
        if row.get('type') in ('ALL', 'index'):
            has_full_scan = True

    return {
        'rows_examined': total_rows,     # 预估扫描行数
        'indexes_used': ','.join(indexes),  # 使用的索引
        'has_full_scan': has_full_scan      # 是否全表扫描
    }
```

#### EXPLAIN输出示例
```
+----+-------------+-------+------+---------------+---------+---------+------+------+-------------+
| id | select_type | table | type | possible_keys | key     | rows    | Extra                 |
+----+-------------+-------+------+---------------+---------+---------+------+------+-------------+
|  1 | SIMPLE      | users | ref  | idx_age_city  | idx_age | 1000    | Using where; Using index |
+----+-------------+-------+------+---------------+---------+---------+------+------+-------------+
```

#### 关键指标
- **type**: 访问类型
  - `ALL` = 全表扫描 ⚠️
  - `index` = 索引全扫描 ⚠️
  - `range` = 索引范围扫描 ✅
  - `ref` = 索引等值查询 ✅
  - `const` = 常量查询 ✅
- **rows**: 预估扫描行数
- **key**: 实际使用的索引
- **Extra**: 额外信息
  - `Using filesort` = 需要文件排序 ⚠️
  - `Using temporary` = 使用临时表 ⚠️

---

### 3.2 SQL Server执行计划

#### 采集方法
通过DMV自动获取XML格式执行计划

```sql
SELECT qp.query_plan
FROM sys.dm_exec_requests r
OUTER APPLY sys.dm_exec_query_plan(r.plan_handle) qp
```

#### XML解析逻辑
```python
def parse_query_plan(query_plan_xml: str) -> Dict:
    root = ET.fromstring(query_plan_xml)

    cost = 0
    estimated_rows = 0
    indexes = []
    has_scan = False

    # 遍历所有RelOp节点(关系运算符)
    for relop in root.findall('.//{*}RelOp'):
        # 提取成本
        estimated_cost = float(relop.get('EstimatedTotalSubtreeCost', 0))
        cost = max(cost, estimated_cost)

        # 提取行数
        rows = float(relop.get('EstimateRows', 0))
        estimated_rows += rows

        # 检测扫描类型
        physical_op = relop.get('PhysicalOp', '')
        if 'Scan' in physical_op:
            has_scan = True
            if 'Index' in physical_op:
                # 提取索引名
                index_scan = relop.find('.//{*}IndexScan')
                if index_scan is not None:
                    index_name = index_scan.get('Index', '')
                    if index_name:
                        indexes.append(index_name)

    return {
        'cost': cost,                      # 查询成本
        'estimated_rows': estimated_rows,  # 预估行数
        'indexes_used': ','.join(indexes), # 使用的索引
        'has_scan': has_scan               # 是否有扫描操作
    }
```

#### 关键算子
- **Table Scan**: 全表扫描 ⚠️
- **Clustered Index Scan**: 聚集索引扫描 ⚠️
- **Index Seek**: 索引查找 ✅
- **Nested Loops**: 嵌套循环连接
- **Hash Match**: 哈希匹配

---

## 4. 告警机制

### 4.1 告警触发条件

#### 慢SQL告警
```python
# 条件1: 运行时间超过阈值
if elapsed_minutes > ALERT_THRESHOLD_MINUTES:
    send_alert()

# 条件2: 去重机制(避免重复告警)
if alert_sent == 0:  # 未发送过告警
    send_alert()
    mark_alert_sent(sql_fingerprint)
```

#### 死锁告警
```python
# 死锁始终告警
if new_deadlock_detected():
    send_alert(level='CRITICAL')
```

### 4.2 告警格式

#### 企业微信告警示例
```markdown
🔴 数据库死锁告警

**实例信息**
- 项目: 生产环境MySQL主库
- 地址: 192.168.1.100:3306
- 时间: 2026-01-26 13:45:30

**死锁详情**
- 受害者事务: 12345
- 受害者SQL: UPDATE orders SET status = 1 WHERE id = 100
- 阻塞者事务: 12346
- 阻塞者SQL: UPDATE products SET stock = stock - 1 WHERE id = 50

**等待资源**
- 资源: orders表, PRIMARY KEY
- 锁模式: X (排他锁)

**建议**
检查应用程序事务逻辑，避免锁顺序不一致
```

### 4.3 告警通道

#### 1. 企业微信
```python
webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
payload = {
    "msgtype": "markdown",
    "markdown": {
        "content": alert_content
    }
}
requests.post(webhook, json=payload)
```

#### 2. 钉钉
```python
webhook = "https://oapi.dingtalk.com/robot/send?access_token=xxx"
# 加签验证
timestamp = str(round(time.time() * 1000))
sign = compute_signature(timestamp, secret)

payload = {
    "msgtype": "markdown",
    "markdown": {
        "title": "数据库告警",
        "text": alert_content
    }
}
```

#### 3. 邮件
```python
smtp.sendmail(
    from_addr="monitor@company.com",
    to_addrs=["dba@company.com"],
    msg=MIMEText(alert_content, 'html', 'utf-8')
)
```

---

## 5. 采集架构

### 5.1 采集流程

```
┌─────────────────────────────────────────────────────┐
│              Collector Enhanced (主进程)             │
└─────────────────────────────────────────────────────┘
                      │
                      │ 每10秒
                      ▼
         ┌────────────────────────┐
         │  加载实例列表           │
         │  (从db_monitor数据库)   │
         └────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │  并发采集(线程池)       │
         │  max_workers=5         │
         └────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
   [实例1]        [实例2]        [实例3]
   MySQL         SQL Server     MySQL
        │             │             │
        ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │慢SQL采集│  │慢SQL采集│  │慢SQL采集│
   └─────────┘  └─────────┘  └─────────┘
        │             │             │
        ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │死锁检测 │  │死锁检测 │  │死锁检测 │
   └─────────┘  └─────────┘  └─────────┘
        │             │             │
        └─────────────┼─────────────┘
                      ▼
         ┌────────────────────────┐
         │  保存到监控数据库       │
         │  long_running_sql_log  │
         │  deadlock_log          │
         └────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │  检查告警条件           │
         └────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │  发送告警               │
         │  企业微信/钉钉/邮件     │
         └────────────────────────┘
```

### 5.2 关键代码

#### 主循环
```python
def daemon_collect():
    """后台采集主循环"""
    while True:
        try:
            # 1. 加载实例列表
            instances = load_instances_from_db()

            # 2. 并发采集
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for instance in instances:
                    future = executor.submit(collect_from_instance, instance)
                    futures.append(future)

                # 3. 等待所有采集完成
                for future in as_completed(futures):
                    result = future.result()
                    logger.info(f"采集完成: {result}")

            # 4. 休眠到下一个周期
            time.sleep(COLLECT_INTERVAL)

        except KeyboardInterrupt:
            logger.info("采集程序退出")
            break
        except Exception as e:
            logger.error(f"采集异常: {e}")
            time.sleep(5)
```

#### 单实例采集
```python
def collect_from_instance(instance: Dict) -> Dict:
    """采集单个实例"""
    db_type = instance.get('db_type', 'MySQL')

    # 1. 创建采集器
    if db_type == 'MySQL':
        collector = MySQLCollector(instance, alert_manager)
    elif db_type == 'SQLServer':
        collector = SQLServerCollector(instance)
    else:
        return {'error': f'不支持的数据库类型: {db_type}'}

    # 2. 采集慢SQL
    slow_sqls = collector.collect_running_queries()
    saved_sql_count = save_slow_sqls(slow_sqls, monitor_conn)

    # 3. 检测死锁
    deadlocks = collector.check_deadlocks()
    saved_deadlock_count = save_deadlocks(deadlocks, monitor_conn)

    # 4. 发送告警
    if alert_manager:
        for sql in slow_sqls:
            if sql['elapsed_minutes'] > ALERT_THRESHOLD_MINUTES:
                alert_manager.send_slow_sql_alert(sql)

        for deadlock in deadlocks:
            alert_manager.send_deadlock_alert(deadlock)

    return {
        'instance': instance['db_project'],
        'slow_sqls': saved_sql_count,
        'deadlocks': saved_deadlock_count
    }
```

---

## 6. 性能优化

### 6.1 SQL指纹去重

**问题**: 相同模式的SQL产生大量重复记录
```sql
SELECT * FROM users WHERE id = 1
SELECT * FROM users WHERE id = 2
SELECT * FROM users WHERE id = 3
...
```

**解决**: SQL指纹
```python
fingerprint = MD5("select * from users where id = ?")
```

所有相同模式的SQL共享一个指纹，便于:
- 聚合统计
- 避免重复告警
- 性能分析

### 6.2 并发采集

使用线程池并发采集多个实例:
```python
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(collect, inst) for inst in instances]
```

**效果**:
- 单线程: 10个实例 × 2秒 = 20秒
- 5线程: 10个实例 ÷ 5 × 2秒 = 4秒

### 6.3 自适应间隔

```python
# 负载低时增加间隔
if slow_sql_count == 0:
    sleep_time = COLLECT_INTERVAL * 2

# 负载高时减少间隔
if slow_sql_count > 10:
    sleep_time = COLLECT_INTERVAL / 2
```

---

## 7. 常见问题

### Q1: 为什么不用慢查询日志?
**A**:
- 慢查询日志是事后分析，需要解析文件
- processlist是实时监控，可以立即告警
- processlist可以获取正在运行的SQL的上下文(事务、锁等)

### Q2: 采集间隔10秒会漏掉快速SQL吗?
**A**:
- 是的，运行时间<10秒的SQL可能被漏掉
- 可以调整间隔到5秒或3秒
- 也可以配合慢查询日志做补充分析

### Q3: EXPLAIN会影响生产环境吗?
**A**:
- EXPLAIN只是分析执行计划，不实际执行SQL
- 对于复杂SQL，EXPLAIN本身也可能耗时
- 建议只对SELECT语句执行EXPLAIN
- UPDATE/DELETE等DML不执行EXPLAIN

### Q4: 死锁检测有延迟吗?
**A**:
- MySQL: 有延迟，最多10秒(采集间隔)
- SQL Server: 几乎实时，Extended Events自动记录
- 可以通过减小采集间隔降低延迟

---

## 8. 总结

| 特性 | MySQL | SQL Server |
|-----|-------|-----------|
| **慢SQL数据源** | information_schema.processlist | sys.dm_exec_requests |
| **死锁数据源** | SHOW ENGINE INNODB STATUS | Extended Events (XEL) |
| **执行计划格式** | 表格(EXPLAIN) | XML |
| **实时性** | 依赖采集间隔 | 依赖采集间隔 |
| **信息完整性** | 基本信息 | 非常详细(wait_type, IO等) |
| **死锁历史** | 仅最近一次 | 持久化所有死锁 |

**核心优势**:
- ✅ 无需修改数据库配置
- ✅ 实时监控，快速告警
- ✅ 统一平台管理多种数据库
- ✅ 自动采集执行计划，便于优化
- ✅ 企业微信/钉钉/邮件多通道告警

---

**文档版本**: v1.0
**更新日期**: 2026-01-26
**作者**: Claude Code
