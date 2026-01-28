# 数据库性能指标监控

## 📊 概述

性能指标监控页面提供实时的数据库性能数据，帮助DBA快速了解数据库运行状态。支持MySQL和SQL Server两种数据库类型。

## 🎯 功能特性

### MySQL 性能指标

#### 核心指标
- **QPS (Queries Per Second)** - 每秒查询数
  - 计算方式: `Questions / Uptime`
  - 反映数据库查询负载

- **TPS (Transactions Per Second)** - 每秒事务数
  - 计算方式: `(Com_commit + Com_rollback) / Uptime`
  - 反映事务处理能力

- **连接使用率** - 当前连接数占最大连接数的百分比
  - 计算方式: `Threads_connected / max_connections * 100`
  - 告警阈值: >80% (红色告警)
  - 正常范围: <80% (黄色/绿色)

- **缓存命中率** - InnoDB Buffer Pool命中率
  - 计算方式: `Innodb_buffer_pool_read_requests / (Innodb_buffer_pool_read_requests + Innodb_buffer_pool_reads) * 100`
  - 告警阈值: <95% (红色告警)
  - 理想值: >99%

- **慢查询累计** - 自MySQL启动以来的慢查询总数
  - 来源: `Slow_queries` 状态变量
  - 配合慢SQL监控页面使用

### SQL Server 性能指标

#### 核心性能指标

**第一层：数据库性能**

- **Batch Requests/sec** - 每秒批处理请求数
  - 类似MySQL的QPS
  - 反映SQL Server工作负载
  - 来源: `sys.dm_os_performance_counters`

- **TPS** - 每秒事务数
  - 计算方式: `Transactions/sec` 计数器
  - 反映事务处理能力

- **连接使用率** - 当前用户连接占最大连接数的百分比
  - 计算方式: `User Connections / @@MAX_CONNECTIONS * 100`
  - 告警阈值: >80% (红色告警)

- **Buffer Cache命中率** - Buffer Pool命中率
  - 计算方式: `Buffer cache hit ratio / Buffer cache hit ratio base * 100`
  - 告警阈值: <90% (红色告警)
  - 理想值: >95%

- **Page Life Expectancy (PLE)** - 页面在Buffer Pool中的平均生存时间
  - 单位: 秒
  - 告警阈值: <300秒 (5分钟)
  - 推荐值: >300秒
  - 说明: 过低表示内存压力大

- **SQL编译/sec** - 每秒SQL编译次数
  - 过高可能表示缺少参数化或计划缓存问题
  - 来源: `SQL Compilations/sec` 计数器

**第二层：系统资源**

- **SQL Server CPU使用率** - SQL Server进程的CPU占用
  - 来源: `sys.dm_os_ring_buffers` 环形缓冲区
  - 告警阈值: >80%
  - 同时显示服务器总CPU使用率

- **内存使用率** - 物理内存使用百分比
  - 来源: `sys.dm_os_sys_memory`
  - 显示: 可用内存 / 总内存
  - 告警阈值: >90%

- **阻塞会话数** - 当前被阻塞的会话数量
  - 来源: `sys.dm_exec_requests`
  - 告警: >0 (存在阻塞)
  - 配合实时监控页面诊断

**第三层：等待统计**

- **Top 5 等待事件** - 最常见的等待类型
  - 显示: 等待类型、累计等待时间(秒)、等待次数
  - 来源: `sys.dm_os_wait_stats`
  - 过滤了系统空闲等待（如SLEEP_TASK）
  - 帮助识别性能瓶颈：
    - `PAGEIOLATCH_*`: 磁盘I/O等待
    - `LCK_*`: 锁等待
    - `CXPACKET`: 并行查询等待
    - `SOS_SCHEDULER_YIELD`: CPU调度等待
    - `WRITELOG`: 日志写入等待

## 🎨 界面特性

### 视觉设计
- **MySQL卡片**: 绿色渐变边框 (#4CAF50)，森林绿主题
- **SQL Server卡片**: 蓝色渐变边框 (#0078D4)，微软蓝主题
- **图标**: 使用emoji增强视觉识别
  - 💫 QPS / ⚡ Batch Requests
  - 🔄 TPS
  - 🔌 连接
  - 💾 缓存
  - 🖥️ CPU
  - 🧠 内存
  - 🚫 阻塞

### 告警状态
- **红色 (danger)**: 严重告警，需要立即处理
  - 连接使用率 >80%
  - MySQL缓存命中率 <95%
  - SQL Server缓存命中率 <90%
  - PLE <300秒
  - CPU >80%
  - 内存使用 >90%
  - 存在阻塞会话

- **黄色 (warning)**: 警告状态，需要关注
  - 连接使用率 60-80%
  - 正常运行但接近阈值

- **绿色 (success)**: 健康状态
  - 所有指标正常

## 💡 使用建议

### 查看频率
- **日常巡检**: 每小时查看一次
- **性能问题**: 每5-10分钟刷新
- **变更后验证**: 立即查看并持续监控15分钟

### 分析思路

#### MySQL性能分析
1. **QPS突然升高**
   - 检查慢SQL列表
   - 查看实时监控页面
   - 分析是否有突发业务

2. **连接数接近上限**
   - 检查连接池配置
   - 查找长连接未释放
   - 考虑增加max_connections

3. **缓存命中率下降**
   - 检查Buffer Pool大小
   - 分析是否有大表扫描
   - 查看内存使用情况

#### SQL Server性能分析
1. **Batch Requests/sec 异常高**
   - 检查是否有密集查询
   - 查看慢SQL和实时SQL
   - 分析编译频率

2. **PLE过低 (<300秒)**
   - 内存不足信号
   - 检查内存配置
   - 分析大查询和索引扫描
   - 考虑增加max server memory

3. **等待事件分析**
   - **PAGEIOLATCH**: 磁盘I/O瓶颈，考虑SSD或增加内存
   - **LCK_M_***: 锁争用，优化事务和索引
   - **CXPACKET**: 并行度问题，调整MAXDOP
   - **WRITELOG**: 日志写入慢，检查磁盘和日志配置

4. **阻塞会话存在**
   - 前往"实时监控"页面
   - 查看阻塞链
   - 必要时Kill阻塞源会话

### 告警响应

#### 连接使用率 >80%
```sql
-- MySQL: 查看当前连接
SHOW PROCESSLIST;

-- SQL Server: 查看当前会话
SELECT * FROM sys.dm_exec_sessions WHERE is_user_process = 1;
```

#### 缓存命中率下降
```sql
-- MySQL: 查看Buffer Pool使用
SHOW ENGINE INNODB STATUS;

-- SQL Server: 查看Buffer Pool详情
SELECT * FROM sys.dm_os_buffer_descriptors;
```

#### CPU使用率过高
- 查看慢SQL页面，找出高CPU查询
- 检查索引覆盖情况
- 分析是否有全表扫描

## 🔧 API接口

### MySQL性能指标
```
GET /api/performance_metrics
Response: {
  "success": true,
  "data": [{
    "instance_id": 1,
    "db_project": "生产数据库",
    "db_ip": "192.168.1.100",
    "db_port": 3306,
    "instance_name": "prod-mysql-01",
    "qps": 1250.32,
    "tps": 89.15,
    "current_connections": 156,
    "max_connections": 500,
    "connection_usage": 31.2,
    "connection_warning": false,
    "cache_hit_rate": 99.87,
    "cache_warning": false,
    "slow_queries": 423
  }]
}
```

### SQL Server性能指标
```
GET /api/sqlserver/performance_metrics?instance_id=5
Response: {
  "success": true,
  "data": [{
    "instance_id": 5,
    "db_project": "预生产备库",
    "db_ip": "192.168.47.102",
    "db_port": 1433,
    "instance_name": "preprod-sqlserver-02",
    "batch_requests_per_sec": 342.56,
    "tps": 78.23,
    "current_connections": 89,
    "max_connections": 32767,
    "connection_usage": 0.27,
    "connection_warning": false,
    "cache_hit_rate": 98.45,
    "cache_warning": false,
    "page_life_expectancy": 1250,
    "ple_warning": false,
    "sql_compilations_per_sec": 15.32,
    "sql_cpu_percent": 45,
    "total_cpu_percent": 52,
    "cpu_warning": false,
    "total_memory_mb": 32768,
    "available_memory_mb": 8192,
    "memory_usage_percent": 75.0,
    "memory_warning": false,
    "blocked_sessions": 0,
    "blocking_warning": false,
    "top_waits": [
      {"wait_type": "PAGEIOLATCH_SH", "wait_time_sec": 1234.56, "waiting_tasks": 5678},
      {"wait_type": "WRITELOG", "wait_time_sec": 890.12, "waiting_tasks": 3456}
    ]
  }]
}
```

## 📚 相关文档

- [采集器配置](collectors-config.md) - 配置慢SQL采集
- [最佳实践](best-practices.md) - 监控最佳实践
- [系统进程过滤](system-filters.md) - 系统SQL过滤规则

## 🔗 相关功能

- **慢SQL监控** - 历史慢SQL分析
- **实时监控** - 当前运行SQL和Kill会话
- **AlwaysOn监控** - SQL Server高可用监控
- **Prometheus集成** - 长期趋势监控

---

**版本**: v1.4.0
**更新时间**: 2026-01-28
**适用范围**: MySQL 5.7+, SQL Server 2016+
