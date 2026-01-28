# SQL Server Always On 可用性组监控

## 功能概述

为数据库监控系统添加了SQL Server Always On高可用性组的监控功能，可以实时查看：
- 可用性组状态
- 副本角色（PRIMARY/SECONDARY）
- 数据库同步状态
- 同步延迟
- 健康状态

## 实现时间
2026-01-26

## Always On 监控指标

### 1. 可用性组级别
- **AG名称**: 可用性组名称
- **副本服务器**: 服务器名称
- **同步模式**:
  - SYNCHRONOUS_COMMIT: 同步提交
  - ASYNCHRONOUS_COMMIT: 异步提交
- **故障转移模式**:
  - AUTOMATIC: 自动故障转移
  - MANUAL: 手动故障转移
- **角色**: PRIMARY（主副本）/ SECONDARY（辅助副本）
- **连接状态**: CONNECTED / DISCONNECTED
- **同步健康**: HEALTHY / PARTIALLY_HEALTHY / NOT_HEALTHY

### 2. 数据库级别
- **数据库名称**: 参与可用性组的数据库
- **同步状态**:
  - SYNCHRONIZED: 已同步（同步模式）
  - SYNCHRONIZING: 正在同步（异步模式）
  - NOT SYNCHRONIZING: 未同步
  - REVERTING: 正在还原
- **数据库同步健康**: HEALTHY / PARTIALLY_HEALTHY / NOT_HEALTHY
- **日志发送队列**: 待发送到辅助副本的日志大小（KB）
- **日志发送速率**: 日志发送速率（KB/秒）
- **重做队列**: 辅助副本待重做的日志大小（KB）
- **重做速率**: 重做速率（KB/秒）
- **延迟时间**: 辅助副本与主副本的延迟（秒）
- **暂停状态**: 是否暂停同步
- **暂停原因**: 暂停的原因说明

## 技术实现

### 1. 后端采集 (sqlserver_collector.py)

添加了 `get_alwayson_status()` 方法，查询以下DMV：

```python
def get_alwayson_status(self) -> List[Dict]:
    """获取Always On可用性组状态和延迟"""
```

**查询的DMV**:
- `sys.availability_groups`: 可用性组信息
- `sys.availability_replicas`: 副本配置
- `sys.dm_hadr_availability_replica_states`: 副本运行状态
- `sys.dm_hadr_database_replica_states`: 数据库副本状态

**关键SQL**:
```sql
SELECT
    ag.name as ag_name,
    ar.replica_server_name,
    ar.availability_mode_desc,
    ar.failover_mode_desc,
    ars.role_desc,
    ars.connected_state_desc,
    ars.synchronization_health_desc,
    DB_NAME(drs.database_id) as database_name,
    drs.synchronization_state_desc,
    drs.log_send_queue_size,
    drs.redo_queue_size,
    DATEDIFF(SECOND, drs.last_commit_time, GETDATE()) as secondary_lag_seconds
FROM sys.availability_groups ag
INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
LEFT JOIN sys.dm_hadr_database_replica_states drs ON ar.replica_id = drs.replica_id
WHERE ars.is_local = 1
```

### 2. API端点 (app_new.py)

添加了 `/api/alwayson_status` 端点：

```python
@app.route('/api/alwayson_status', methods=['GET'])
def get_alwayson_status():
    """获取SQL Server Always On可用性组状态"""
```

**请求参数**:
- `instance_id` (可选): 指定实例ID，不指定则查询所有SQL Server实例

**响应格式**:
```json
{
  "success": true,
  "data": [
    {
      "instance_id": 1,
      "db_project": "预生产主库-mssql",
      "ag_name": "yzc-cluster",
      "replica_server": "WIN-CS3DDQO9JE8",
      "availability_mode": "ASYNCHRONOUS_COMMIT",
      "failover_mode": "MANUAL",
      "role": "PRIMARY",
      "connected_state": "CONNECTED",
      "sync_health": "HEALTHY",
      "database_name": "YOUZC",
      "sync_state": "SYNCHRONIZED",
      "lag_seconds": 1,
      "log_send_queue_kb": 0.00,
      "redo_queue_kb": 0.00,
      "is_healthy": 1,
      "lag_warning": false
    }
  ],
  "total_count": 31
}
```

### 3. 前端界面 (static/index.html)

在"性能指标"页面添加了"Always On 可用性组状态"卡片。

**显示内容**:
- 按可用性组分组显示
- 每个AG显示实例名、AG名称、角色
- 数据库列表表格，包含：
  - 数据库名称
  - 副本服务器
  - 同步模式（带颜色标识）
  - 故障转移模式
  - 同步状态（已同步/正在同步）
  - 连接状态
  - 延迟时间（超过10秒红色告警）
  - 日志队列和重做队列大小
  - 健康状态

**JavaScript函数**:
```javascript
async function loadAlwaysOnStatus()
```

## 测试结果

### 测试环境
- 主库: 192.168.47.101:1433 (PRIMARY)
- 备库: 192.168.47.102:1433 (SECONDARY)
- 可用性组: yzc-cluster
- 数据库数量: 31个

### 测试输出

```
可用性组: yzc-cluster
副本服务器: WIN-CS3DDQO9JE8
角色: PRIMARY
同步模式: ASYNCHRONOUS_COMMIT
故障转移模式: MANUAL
连接状态: CONNECTED
同步健康: HEALTHY

数据库详情:
数据库                  同步状态            延迟(秒)      日志队列(KB)        重做队列(KB)        健康状态
----------------------------------------------------------------------------------------------------
YOUZC                SYNCHRONIZED    1          0.00            0.00            健康
YOUZCCommon          SYNCHRONIZED    1          0.00            0.00            健康
Expert               SYNCHRONIZED    1          0.00            0.00            健康
...（共31个数据库）
```

## 使用方法

### 1. 在监控面板查看

1. 浏览器访问监控面板
2. 点击顶部导航的"**性能指标**"标签
3. 滚动到"**Always On 可用性组状态 (SQL Server)**"区域
4. 点击"**刷新**"按钮

### 2. 通过API查询

```bash
# 查询所有SQL Server实例的Always On状态
curl http://localhost:5001/api/alwayson_status

# 查询指定实例
curl http://localhost:5001/api/alwayson_status?instance_id=1
```

### 3. 命令行测试

```bash
# 运行测试脚本
python test_alwayson_status.py
```

## 健康检查规则

系统自动判断健康状态（`is_healthy`），满足以下条件视为健康：

1. ✓ 同步健康度为 HEALTHY
2. ✓ 连接状态为 CONNECTED
3. ✓ 未暂停同步（is_suspended = 0）

## 延迟告警规则

- **正常**: 延迟 ≤ 10秒（绿色）
- **告警**: 延迟 > 10秒（红色）

**注意**:
- 同步模式（SYNCHRONOUS_COMMIT）通常延迟很小（0-1秒）
- 异步模式（ASYNCHRONOUS_COMMIT）允许较大延迟
- 延迟计算基于 `last_commit_time`，表示最后一次提交事务的时间差

## Always On 同步状态说明

### SYNCHRONIZED（已同步）
- 主副本和辅助副本完全同步
- 仅在同步提交模式下出现
- 事务在主副本和辅助副本都提交后才返回成功

### SYNCHRONIZING（正在同步）
- 辅助副本正在追赶主副本
- 在异步提交模式下的正常状态
- 主副本事务立即提交，后台异步发送到辅助副本

### NOT SYNCHRONIZING（未同步）
- 同步已停止或失败
- 需要检查网络连接和日志传输

## 监控建议

### 1. 同步健康监控
- 确保 `sync_health` 始终为 HEALTHY
- 如果出现 PARTIALLY_HEALTHY 或 NOT_HEALTHY，立即检查

### 2. 连接状态监控
- 确保 `connected_state` 为 CONNECTED
- DISCONNECTED 表示副本间网络断开

### 3. 延迟监控
- 同步模式: 延迟应 < 1秒
- 异步模式: 建议 < 60秒，超过5分钟需要告警

### 4. 队列监控
- **日志发送队列过大**: 表示网络带宽不足或辅助副本处理慢
- **重做队列过大**: 表示辅助副本磁盘IO瓶颈

### 5. 暂停状态监控
- 正常情况下 `is_suspended` 应为 0
- 如果暂停，检查 `suspend_reason` 了解原因

## 常见问题

### Q1: 为什么我的实例显示"未配置Always On"？

**可能原因**:
1. SQL Server版本不支持（需要2012+企业版或标准版）
2. 未启用Always On功能
3. 实例未加入任何可用性组
4. 当前实例不是可用性组的副本

### Q2: 延迟时间很大是否正常？

**取决于同步模式**:
- **同步提交**: 延迟应该非常小（0-1秒），大延迟不正常
- **异步提交**: 允许较大延迟，但建议 < 5分钟

如果延迟过大，检查：
- 网络带宽和延迟
- 辅助副本服务器性能
- 主副本事务量

### Q3: SYNCHRONIZING vs SYNCHRONIZED 的区别？

- **SYNCHRONIZED**: 同步模式下，主辅完全同步
- **SYNCHRONIZING**: 异步模式下，辅助副本正在追赶主副本（正常状态）

### Q4: 如何启用Always On？

1. 在SQL Server配置管理器中启用Always On功能
2. 重启SQL Server服务
3. 创建可用性组
4. 添加数据库到可用性组
5. 配置副本和故障转移模式

## 技术参考

### SQL Server DMV文档
- [sys.availability_groups](https://docs.microsoft.com/sql/relational-databases/system-catalog-views/sys-availability-groups-transact-sql)
- [sys.dm_hadr_availability_replica_states](https://docs.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-hadr-availability-replica-states-transact-sql)
- [sys.dm_hadr_database_replica_states](https://docs.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-hadr-database-replica-states-transact-sql)

### Always On 最佳实践
- 主副本和辅助副本硬件配置应相近
- 使用专用网络连接副本
- 定期测试故障转移
- 监控同步延迟和队列大小

## 文件清单

- `scripts/sqlserver_collector.py`: 添加 `get_alwayson_status()` 方法
- `app_new.py`: 添加 `/api/alwayson_status` API端点
- `static/index.html`: 添加Always On状态显示界面和 `loadAlwaysOnStatus()` 函数
- `test_alwayson_status.py`: Always On状态测试脚本
- `ALWAYSON_MONITORING.md`: 本文档

## 总结

SQL Server Always On 可用性组监控功能已完整实现，可以：

✅ 实时监控可用性组状态
✅ 查看主副本和辅助副本角色
✅ 监控数据库同步状态和延迟
✅ 检测健康状态和连接状态
✅ 显示日志队列和重做队列大小
✅ 告警延迟超过10秒的数据库

配合MySQL主从复制监控，系统现在支持完整的高可用性监控！
