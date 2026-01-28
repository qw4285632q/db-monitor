# 📋 采集器配置管理功能使用指南

## 🎉 新功能特性

采集器配置现已支持通过Web界面实时管理，**无需重启应用**即可生效！

---

## 🚀 功能特点

### ✅ 实时生效
- 配置保存后立即更新调度器
- 无需重启Flask应用
- 无需停止采集器进程
- 零停机时间

### ⚙️ 可配置项

#### MySQL采集器
- ✅ 启用/禁用
- ✅ 采集间隔 (10-3600秒)
- ✅ 慢SQL阈值 (1-3600秒)

#### SQL Server采集器
- ✅ 启用/禁用
- ✅ 采集间隔 (10-3600秒)
- ✅ 慢SQL阈值 (1-3600秒)
- ✅ 自动开启Query Store

### 📊 实时状态
- 运行状态 (运行中/已停止)
- 下次运行时间
- 立即执行按钮

---

## 🖥️ 使用方法

### 1. 访问配置页面

1. 打开浏览器访问：`http://localhost:5000` 或 `http://你的IP:5000`
2. 点击顶部导航栏的 **"采集器配置"** 选项卡

### 2. 查看当前配置

页面会自动加载当前配置，显示：
- ✅ 启用状态
- ⏰ 采集间隔
- 🎯 慢SQL阈值
- 📊 运行状态
- ⏭️ 下次运行时间

### 3. 修改配置

#### MySQL采集器配置

```
启用状态:     [启用 ▼]
采集间隔:     [60] 秒
慢SQL阈值:    [5] 秒

运行状态:     ✅ 运行中
下次运行:     2026-01-27 20:45:30
```

#### SQL Server采集器配置

```
启用状态:           [启用 ▼]
采集间隔:           [60] 秒
慢SQL阈值:          [5] 秒
自动开启Query Store: [否 ▼]

运行状态:           ✅ 运行中
下次运行:           2026-01-27 20:45:35
```

### 4. 保存配置

点击页面底部的 **"💾 保存配置并实时生效"** 按钮

**效果：**
- ✅ 配置立即保存到 `config.json`
- ✅ 调度器立即更新，新配置生效
- ✅ 页面自动刷新显示最新状态
- ✅ 无需重启应用

### 5. 手动触发执行

在每个采集器下方有 **"立即执行一次"** 按钮，点击可以：
- 🚀 立即运行一次采集（不等待定时）
- 📊 快速验证配置是否正确
- 🔍 手动触发数据采集

---

## 📝 配置建议

### 采集间隔

| 场景 | 推荐间隔 | 说明 |
|------|---------|------|
| 生产环境 | 60秒 | 平衡数据实时性和数据库负载 |
| 测试环境 | 120秒 | 减少开销 |
| 高负载系统 | 90-120秒 | 避免频繁采集增加负载 |
| 调试模式 | 30秒 | 快速获取数据 |

**注意：**
- ⚠️ 最小值：10秒
- ⚠️ 最大值：3600秒（1小时）
- ⚠️ 不建议低于30秒

### 慢SQL阈值

| 业务类型 | 推荐阈值 | 说明 |
|---------|---------|------|
| OLTP在线交易 | 3-5秒 | 要求响应快 |
| OLAP分析查询 | 10-30秒 | 允许长时间查询 |
| 批处理作业 | 30-60秒 | 大数据处理 |
| 报表系统 | 10-20秒 | 复杂查询较多 |

**注意：**
- ⚠️ 最小值：1秒
- ⚠️ 最大值：3600秒（1小时）
- ⚠️ 建议：5秒是通用的合理值

### 自动开启Query Store

| 选项 | 说明 | 建议 |
|------|------|------|
| 否 (推荐) | 不自动修改数据库配置 | ✅ 推荐 |
| 是 | 自动为未开启的数据库启用Query Store | ⚠️ 需要DBA权限 |

**说明：**
- Query Store是SQL Server 2016+的查询性能洞察功能
- 未开启时，采集器仍可从DMV获取数据
- 复制库/快照隔离数据库可能无法开启

---

## 🔧 高级操作

### 临时禁用采集器

**场景：** 数据库维护、性能测试时暂停采集

**操作：**
1. 将对应采集器的"启用状态"改为"禁用"
2. 点击"保存配置"
3. 采集器立即停止，定时任务被移除

**效果：**
- 🛑 不再采集新数据
- 💾 历史数据保留
- 🔄 随时可重新启用

### 调整性能开销

**降低数据库负载：**
```
采集间隔: 60秒 → 120秒 (减少50%采集次数)
慢SQL阈值: 5秒 → 10秒 (减少采集量)
```

**增加数据准确性：**
```
采集间隔: 60秒 → 30秒 (更频繁采集)
慢SQL阈值: 5秒 → 3秒 (捕获更多慢SQL)
```

---

## 📊 配置文件

### 位置
```
C:\运维工具类\database-monitor\config.json
```

### 格式

```json
{
  "collectors": {
    "mysql": {
      "enabled": true,
      "interval": 60,
      "threshold": 5,
      "description": "MySQL Performance Schema采集器"
    },
    "sqlserver": {
      "enabled": true,
      "interval": 60,
      "threshold": 5,
      "auto_enable_querystore": false,
      "description": "SQL Server Query Store采集器"
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | boolean | 是否启用 |
| `interval` | integer | 采集间隔（秒） |
| `threshold` | integer | 慢SQL阈值（秒） |
| `auto_enable_querystore` | boolean | 自动开启Query Store |
| `description` | string | 描述信息 |

---

## 🔍 故障排查

### 问题1: 保存配置后没有生效

**检查：**
```bash
# 查看Flask应用日志
type logs\app_running.log

# 查看配置文件
type config.json
```

**原因：**
- 配置文件权限问题
- JSON格式错误
- 应用异常

**解决：**
1. 检查配置文件是否正确更新
2. 重启Flask应用
3. 查看日志排查错误

### 问题2: 采集器状态显示"已停止"

**检查：**
```bash
# 查看调度器状态
curl http://localhost:5000/api/collectors/status
```

**原因：**
- 采集器被禁用
- 调度器未正常启动

**解决：**
1. 检查"启用状态"是否为"启用"
2. 重启应用
3. 手动触发执行测试

### 问题3: 手动触发执行失败

**检查：**
- 数据库连接是否正常
- 实例配置是否正确
- 数据库权限是否足够

**解决：**
1. 在"实例管理"页面测试连接
2. 查看采集器日志
3. 检查数据库权限

---

## 🎯 API接口

### 获取配置
```bash
GET /api/collectors/config

Response:
{
  "success": true,
  "data": {
    "mysql": {
      "enabled": true,
      "interval": 60,
      "threshold": 5,
      "status": "running",
      "next_run": "2026-01-27 20:45:30"
    },
    "sqlserver": {...}
  }
}
```

### 更新配置
```bash
POST /api/collectors/config
Content-Type: application/json

{
  "mysql": {
    "enabled": true,
    "interval": 90,
    "threshold": 10
  }
}

Response:
{
  "success": true,
  "message": "采集器配置已更新并实时生效"
}
```

### 手动触发
```bash
POST /api/collectors/mysql/trigger
POST /api/collectors/sqlserver/trigger

Response:
{
  "success": true,
  "message": "mysql采集器已手动触发执行"
}
```

### 查看状态
```bash
GET /api/collectors/status

Response:
{
  "success": true,
  "data": {
    "mysql": {
      "running": true,
      "next_run": "2026-01-27 20:45:30",
      "trigger": "interval[0:01:00]"
    },
    "sqlserver": {...}
  }
}
```

---

## 💡 最佳实践

### 1. 分环境配置

**生产环境：**
```
MySQL:    间隔60秒, 阈值5秒
SQLServer: 间隔60秒, 阈值5秒
```

**测试环境：**
```
MySQL:    间隔120秒, 阈值3秒
SQLServer: 间隔120秒, 阈值3秒
```

### 2. 性能调优期间

临时降低阈值，增加采集频率：
```
阈值: 5秒 → 2秒
间隔: 60秒 → 30秒
```

### 3. 维护窗口

临时禁用采集器：
```
启用状态: 启用 → 禁用
```

### 4. 定期检查

每周检查一次：
- 📊 采集数据量是否正常
- ⏰ 下次运行时间是否正确
- 💾 数据库存储空间是否充足

---

## 📚 相关文档

- **SYSTEM_PROCESS_FILTERS.md** - 系统进程过滤规则
- **BEST_PRACTICE_COLLECTORS.md** - 采集器最佳实践
- **INTEGRATION_COMPLETE.md** - 采集器集成报告
- **TODO_ACTION_LIST.md** - 后续行动清单

---

## ⚡ 快速命令

```bash
# 启动应用
START_INTEGRATED_APP.bat

# 查看进程
wmic process where "name='python.exe'" get ProcessId,CommandLine | findstr "app_new"

# 查看日志
type logs\app_running.log

# 停止应用
taskkill /F /IM python.exe

# 测试API
curl http://localhost:5000/api/collectors/config
```

---

**更新时间**: 2026-01-27 21:00
**版本**: v1.0
**状态**: ✅ 已实现并测试通过
