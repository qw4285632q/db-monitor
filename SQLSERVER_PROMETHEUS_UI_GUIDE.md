# SQL Server Prometheus监控界面使用指南

## 实施日期
2026-01-26

## 功能概述

在"性能指标"页面新增了 **SQL Server监控 (Prometheus)** 卡片，用于展示SQL Server实例的Prometheus监控指标。

---

## 界面位置

访问路径：**监控面板 → 性能指标 → SQL Server监控 (Prometheus)**

页面结构：
```
性能指标页面
├── 数据库性能指标 (原有)
├── 系统资源监控 (Prometheus) - MySQL实例
├── 【SQL Server监控 (Prometheus)】⭐ 新增
├── 阻塞查询检测
├── 主从复制状态 (MySQL)
└── Always On状态 (SQL Server)
```

---

## 使用步骤

### 步骤1: 配置SQL Server实例

编辑 `config.json`，添加SQL Server实例的Prometheus Exporter映射：

```json
{
  "sqlserver_exporter_mapping": {
    "192.168.44.200": "http://192.168.98.4:9399",
    "192.168.44.201": "http://192.168.98.4:9400"
  }
}
```

**配置说明**:
- **键**: SQL Server实例的IP地址
- **值**: 对应的SQL Server Exporter URL

### 步骤2: 重启Flask应用

```bash
# 停止当前运行的Flask应用 (Ctrl+C)
# 重新启动
python app_new.py
```

或者直接刷新浏览器（Flask会自动重载配置）。

### 步骤3: 访问监控界面

1. 打开浏览器访问: http://localhost:5000
2. 点击顶部 **"性能指标"** 标签
3. 滚动到 **"SQL Server监控 (Prometheus)"** 卡片
4. 在下拉框中选择SQL Server实例
5. 点击 **"刷新"** 按钮查看指标

---

## 监控指标说明

### 🔌 连接和性能 (4项)

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| 当前连接数 | SQL Server当前活动连接数 | - |
| 连接使用率 | 当前连接数/最大连接数 | >80%警告 |
| 批处理请求/秒 | Batch Requests/sec (类似MySQL的QPS) | - |
| SQL编译数/秒 | SQL Compilations/sec (编译开销) | - |

### 💾 Buffer Cache (4项)

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| Buffer Cache命中率 | 缓存命中率百分比 | <95%警告 |
| 页面生命期望值 | Page Life Expectancy (PLE，单位:秒) | <300秒警告 |
| 目标内存 | Target Server Memory (MB) | - |
| 内存压力 | Total Memory / Target Memory | >95%警告 |

**PLE说明**: 页面在Buffer Pool中停留的平均时间，越高越好。
- **正常**: >300秒
- **警告**: 150-300秒
- **危险**: <150秒（内存压力大，需要增加内存）

### 🔒 锁和死锁 (4项)

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| 锁等待/秒 | Lock Waits/sec | >10警告 |
| 死锁数/秒 | Deadlocks/sec | >0警告 |
| IO延迟 | IO Stall时间（秒） | >0.1秒警告 |
| 用户错误/秒 | User Errors/sec | >1警告 |

### 🔄 Always On可用性组 (2项，可选)

如果实例配置了Always On，会显示：

| 指标 | 说明 | 状态 |
|------|------|------|
| 同步健康状态 | Synchronization Health | Healthy/Unhealthy |
| 数据库状态 | Database State | Online/Other |

### 🖥️ 系统资源 (2项，可选)

如果配置了process_exporter，会显示：

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| CPU使用率 | 进程CPU使用率 | >50%警告, >80%危险 |
| 进程内存 | SQL Server进程内存使用（MB） | - |

---

## 颜色编码

界面使用颜色编码表示指标状态：

- 🟢 **绿色** (success): 指标正常
- 🟡 **黄色** (warning): 指标有警告，建议关注
- 🔴 **红色** (danger): 指标异常，需要立即处理
- 🔵 **蓝色** (primary): 一般信息，无需告警

---

## 界面示例

### 完整展示示例

```
┌─────────────────────────────────────────────────────────────┐
│ SQL Server监控 (Prometheus)                                │
│ [SQL Server实例 ▼] [刷新]                                   │
├─────────────────────────────────────────────────────────────┤
│ 🗄️ 数据库类型: SQL Server | 📊 实例: 192.168.44.200      │
│ ⏱️ 采集时间: 2026-01-26 18:00:00                           │
│                                                             │
│ 🔌 连接和性能                                              │
│ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐                  │
│ │当前连接│ │连接使用│ │批处理请│ │SQL编译│                  │
│ │  25   │ │ 25.0% │ │150.5/秒│ │10.2/秒│                  │
│ │100最大│ │✓ 正常 │ │类似QPS │ │编译开销│                  │
│ └───────┘ └───────┘ └───────┘ └───────┘                  │
│                                                             │
│ 💾 Buffer Cache                                            │
│ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐                  │
│ │Buffer │ │页面生命│ │目标内存│ │内存压力│                  │
│ │ 99.5% │ │3600秒 │ │8192MB │ │ 96.3% │                  │
│ │✓ 正常 │ │✓ 正常 │ │Target │ │7890 MB│                  │
│ └───────┘ └───────┘ └───────┘ └───────┘                  │
│                                                             │
│ 🔒 锁和死锁                                                │
│ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐                  │
│ │锁等待/秒│ │死锁数/秒│ │IO延迟 │ │用户错误│                  │
│ │  0.5  │ │ 0.000 │ │0.050秒│ │ 0.0/秒│                  │
│ │✓ 正常 │ │✓ 正常 │ │✓ 正常 │ │✓ 正常 │                  │
│ └───────┘ └───────┘ └───────┘ └───────┘                  │
│                                                             │
│ 🔄 Always On可用性组                                       │
│ ┌───────────┐ ┌───────────┐                              │
│ │同步健康状态│ │数据库状态 │                              │
│ │  Healthy  │ │  Online   │                              │
│ │  ✓ 正常   │ │  ✓ 在线   │                              │
│ └───────────┘ └───────────┘                              │
│                                                             │
│ 🖥️ 系统资源                                               │
│ ┌───────────┐ ┌───────────┐                              │
│ │CPU使用率  │ │进程内存   │                              │
│ │  15.5%    │ │ 7890 MB   │                              │
│ │  ✓ 正常   │ │  已使用   │                              │
│ └───────────┘ └───────────┘                              │
│                                                             │
│ 💡 说明: 数据来源于Prometheus SQL Server Exporter。      │
└─────────────────────────────────────────────────────────────┘
```

---

## 配置示例

### 示例1: 单个SQL Server实例

```json
{
  "prometheus": {
    "enabled": true,
    "url": "http://192.168.98.4:20001",
    "timeout": 5
  },
  "sqlserver_exporter_mapping": {
    "192.168.44.200": "http://192.168.98.4:9399"
  }
}
```

### 示例2: 多个SQL Server实例

```json
{
  "sqlserver_exporter_mapping": {
    "192.168.44.200": "http://192.168.98.4:9399",
    "192.168.44.201": "http://192.168.98.4:9400",
    "192.168.44.202": "http://192.168.98.4:9401",
    "10.111.1.100": "http://192.168.98.4:9402"
  }
}
```

### 示例3: 暂无SQL Server实例

```json
{
  "sqlserver_exporter_mapping": {
    "_comment": "SQL Server实例的Prometheus Exporter映射，根据实际部署情况配置"
  }
}
```

界面会显示: "暂无SQL Server实例配置"

---

## API接口

### 获取SQL Server指标

**请求**:
```bash
GET /api/prometheus/sqlserver/metrics/<instance_ip>
```

**示例**:
```bash
curl http://localhost:5000/api/prometheus/sqlserver/metrics/192.168.44.200
```

**响应**:
```json
{
  "success": true,
  "data": {
    "instance_ip": "192.168.44.200",
    "timestamp": "2026-01-26T18:00:00",
    "db_type": "SQL Server",
    "connections": 25.0,
    "max_connections": 100.0,
    "connection_usage": 25.0,
    "batch_requests": 150.5,
    "sql_compilations": 10.2,
    "buffer_cache_hit_ratio": 99.5,
    "page_life_expectancy": 3600.0,
    "lock_waits_rate": 0.5,
    "deadlocks_rate": 0.0,
    "io_stall_seconds": 0.05,
    "user_errors_rate": 0.0,
    "ao_sync_health": 1.0,
    "database_state": 0.0,
    "target_memory_mb": 8192.0,
    "total_memory_mb": 7890.5,
    "memory_pressure": 96.32,
    "cpu_usage": 15.5,
    "memory_usage_mb": 7890.5
  }
}
```

---

## 故障排查

### 问题1: 下拉框显示"暂无SQL Server实例配置"

**原因**: config.json中没有配置SQL Server实例

**解决**:
1. 编辑config.json
2. 添加sqlserver_exporter_mapping配置
3. 重启Flask应用或刷新页面

### 问题2: 所有指标显示"-"

**原因**: Prometheus中没有SQL Server的metrics

**检查步骤**:

1. 检查SQL Server Exporter是否运行
```bash
curl http://192.168.98.4:9399/metrics | grep mssql
```

2. 检查Prometheus是否采集到数据
```bash
# 访问Prometheus界面
http://192.168.98.4:20001

# 查询
mssql_connections{ip="192.168.44.200"}
```

3. 检查Prometheus配置
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'sqlserver'
    static_configs:
      - targets:
        - '192.168.44.200:9399'
        labels:
          ip: '192.168.44.200'
```

### 问题3: 部分指标显示"-"

**原因**: SQL Server Exporter版本不同，metric名称可能不同

**解决**: 查看实际的metric名称
```bash
curl http://192.168.98.4:9399/metrics | grep -i "buffer\|connection\|lock"
```

根据实际名称修改 `scripts/prometheus_client.py` 中的PromQL查询。

### 问题4: 界面不显示Always On或系统资源

**原因**:
- Always On: 实例未配置可用性组，或Exporter未采集该指标
- 系统资源: 未配置process_exporter

**解决**: 正常现象，这些是可选指标。

---

## 与MySQL监控的区别

| 项目 | MySQL监控 | SQL Server监控 |
|------|----------|---------------|
| 性能指标 | QPS, TPS | Batch Requests, SQL Compilations |
| 缓存指标 | Buffer Pool命中率 | Buffer Cache命中率, PLE |
| 复制监控 | 主从复制延迟 | Always On同步健康 |
| 特有指标 | 临时表统计 | 页面生命期望值, 内存压力 |
| Exporter | MySQL Exporter | SQL Server Exporter |
| Metric前缀 | mysql_* | mssql_* |

---

## 告警阈值建议

根据生产经验，建议的告警阈值：

### 连接数
- 警告: >80%
- 危险: >90%

### Buffer Cache命中率
- 警告: <95%
- 危险: <90%

### 页面生命期望值 (PLE)
- 警告: <300秒
- 危险: <150秒
- **建议**: 对于有8GB Buffer Pool的服务器，PLE应该>300秒

### 锁等待
- 警告: >10/秒
- 危险: >50/秒

### 死锁
- 警告: >0/秒
- 危险: >1/秒

### IO延迟
- 警告: >0.05秒
- 危险: >0.1秒

### 内存压力
- 警告: >95%
- 危险: >98%

---

## 下一步优化

1. **趋势图表**: 显示指标的历史趋势（24小时）
2. **自定义阈值**: 允许用户配置告警阈值
3. **自动刷新**: 支持定时自动刷新（类似实时监控）
4. **告警通知**: 基于阈值自动发送告警
5. **数据库级指标**: 支持查看单个数据库的指标
6. **对比功能**: 多个SQL Server实例的指标对比

---

## 相关文档

- `DATABASE_INIT_AND_SQLSERVER_PROMETHEUS.md` - SQL Server Prometheus集成完整文档
- `PROMETHEUS_USAGE_GUIDE.md` - MySQL Prometheus监控使用指南
- `scripts/prometheus_client.py` - Prometheus客户端源码

---

**文档版本**: v1.0
**最后更新**: 2026-01-26
**状态**: ✅ 已完成并可用
