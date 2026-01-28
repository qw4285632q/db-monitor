# 📚 Database Monitor 文档中心

## 📖 用户文档

### 入门指南
- **[快速开始](../QUICK_START.md)** - 5分钟快速上手，新手必读
- **[部署指南](../DEPLOYMENT.md)** - 生产环境部署完整指南

### 功能配置
- **[采集器配置指南](collectors-config.md)** - 慢SQL采集器配置和优化
- **[系统进程过滤](system-filters.md)** - 系统进程过滤规则说明
- **[最佳实践](best-practices.md)** - 推荐配置和使用建议

## 🎯 核心功能

### 慢SQL监控
- 基于 Performance Schema (MySQL) 和 Query Store (SQL Server)
- 100% 准确率，零侵入式监控
- 自动过滤系统进程（CDC、复制、AlwaysOn等）
- Web界面实时配置，无需重启

### 实时监控
- 实时SQL查看和会话管理
- 死锁检测和分析
- SQL执行计划自动采集
- 阻塞会话检测和终止

### AlwaysOn监控
- 可用性组状态监控
- 副本延迟计算
- 自动故障转移跟踪

### Prometheus集成
- MySQL/SQL Server 性能指标导出
- 自定义查询支持
- Grafana 集成

## 🚀 快速链接

### 常见任务
- [添加监控实例](../QUICK_START.md#添加监控实例)
- [配置慢SQL采集](collectors-config.md#采集器配置)
- [查看慢SQL](../README.md#long-sql列表)
- [实时监控SQL](../README.md#实时监控)
- [死锁分析](../README.md#死锁监控)

### 故障排查
- [采集器未运行](../DEPLOYMENT.md#故障排查)
- [数据库连接失败](collectors-config.md#常见问题)
- [Web页面无法访问](../DEPLOYMENT.md#故障排查)

## 📊 系统架构

### 技术栈
- **后端**: Flask + APScheduler + PyMySQL + pyodbc
- **前端**: Vanilla JavaScript (无框架依赖)
- **监控**: Performance Schema + Query Store + DMV
- **指标**: Prometheus + Grafana

### 数据流
```
监控实例 → 采集器 → 监控数据库 → Web API → 前端展示
           ↓
      Prometheus Exporter → Grafana
```

## 🔒 权限要求

### MySQL
```sql
GRANT SELECT ON performance_schema.* TO 'monitor_user'@'%';
GRANT SELECT ON information_schema.* TO 'monitor_user'@'%';
GRANT PROCESS ON *.* TO 'monitor_user'@'%';
```

### SQL Server
```sql
GRANT VIEW SERVER STATE TO monitor_user;
GRANT VIEW DATABASE STATE TO monitor_user;
GRANT VIEW ANY DEFINITION TO monitor_user;
```

## 💡 使用提示

### 性能优化
- 推荐采集间隔: 60秒（平衡实时性和性能）
- 慢SQL阈值: 5秒（根据业务调整）
- 定期清理历史数据（保留30天）

### 安全建议
- 使用只读监控账号
- 不要将 `config.json` 提交到版本控制
- 定期更新监控账号密码

### 最佳实践
- 为每个业务系统创建独立监控实例
- 启用自动过滤系统进程
- 配置告警规则（可选）
- 定期导出慢SQL报告

## 📞 获取帮助

- **GitHub Issues**: https://github.com/qw4285632q/db-monitor/issues
- **主文档**: [README.md](../README.md)
- **快速开始**: [QUICK_START.md](../QUICK_START.md)

## 📝 版本信息

当前版本: **v1.3.0** (2026-01-28)

主要更新:
- ✨ Web界面采集器配置管理
- 🎯 优化系统进程过滤
- 🚀 采集器集成到主应用
- 📊 完善状态监控

详见: [主文档 - 版本更新](../README.md#版本更新)
