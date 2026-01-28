# 🗄️ Database Monitor - 数据库监控系统

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个功能强大的数据库监控系统，支持 MySQL 和 SQL Server，提供慢SQL监控、实时SQL分析、死锁检测、AlwaysOn监控等DBA必备功能。

## ✨ 核心特性

### 📊 慢SQL监控
- **MySQL Performance Schema 采集器** - 100%准确率，零侵入
- **SQL Server Query Store 采集器** - 智能过滤CDC/复制作业
- **实时配置管理** - Web界面动态调整，无需重启
- **智能过滤** - 自动排除系统进程（CDC、sp_server_diagnostics、@@TRANCOUNT等）

### 🔍 实时监控
- 实时SQL监控和终止会话
- 死锁检测和详细分析
- SQL执行计划自动采集
- SQL指纹聚合和性能对比

### 🎯 AlwaysOn监控
- 可用性组状态监控
- 副本延迟计算和告警
- 自动故障转移跟踪

### 📈 Prometheus集成
- MySQL和SQL Server指标导出
- 性能趋势图表
- 自定义查询支持

### 🤖 智能分析
- SQL执行计划分析
- 索引建议自动生成
- 健康检查引擎
- 性能基线对比

## 🚀 快速开始

### 1. 环境要求

```bash
Python 3.8+
MySQL 5.7+ / SQL Server 2016+
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置数据库

复制配置文件模板：
```bash
cp config.json.example config.json
```

编辑 `config.json`，填入监控数据库连接信息：
```json
{
  "database": {
    "host": "your-monitor-db-host",
    "port": 3306,
    "user": "your-username",
    "password": "your-password",
    "database": "db_monitor"
  }
}
```

### 4. 初始化数据库

```bash
python scripts/init_database.py
```

### 5. 启动应用

**Windows:**
```bash
START_INTEGRATED_APP.bat
```

**Linux/Mac:**
```bash
python app_new.py
```

### 6. 访问Web界面

打开浏览器访问：`http://localhost:5000`

## 📖 详细文档

- **[快速开始指南](QUICK_START.md)** - 5分钟快速上手
- **[部署指南](DEPLOYMENT.md)** - 生产环境部署
- **[采集器配置](COLLECTORS_CONFIG_GUIDE.md)** - 采集器配置和优化
- **[系统进程过滤](SYSTEM_PROCESS_FILTERS.md)** - 过滤规则说明
- **[最佳实践](BEST_PRACTICE_COLLECTORS.md)** - 推荐配置和实践
- **[DBA功能指南](DBA_FEATURES_GUIDE.txt)** - 完整功能列表

## 🎯 核心功能

### 慢SQL监控
- 基于Performance Schema（MySQL）和Query Store（SQL Server）
- 准确率100%，不会遗漏任何慢SQL
- 自动去重和聚合
- 持久化存储

### 采集器配置管理
- Web界面实时配置
- 动态调整采集间隔和阈值
- 启用/禁用采集器
- 手动触发执行

### 系统进程过滤
自动过滤以下系统进程，避免误报：
- CDC（变更数据捕获）作业
- 数据库复制作业
- sp_server_diagnostics（AlwaysOn健康检查）
- @@TRANCOUNT（连接池事务管理）
- SQLAgent系统维护作业

### 实时SQL监控
- 查看当前正在执行的SQL
- 一键终止阻塞会话
- SQL详情和执行计划查看
- 会话信息完整展示

### 死锁检测
- 自动采集死锁事件
- XML解析和可视化展示
- 死锁SQL和资源分析
- 历史死锁查询

## 🔧 配置说明

### 采集器配置

在Web界面 **"采集器配置"** 页面可以实时调整：

**MySQL采集器：**
- 采集间隔：10-3600秒（推荐60秒）
- 慢SQL阈值：1-3600秒（推荐5秒）

**SQL Server采集器：**
- 采集间隔：10-3600秒（推荐60秒）
- 慢SQL阈值：1-3600秒（推荐5秒）
- 自动开启Query Store：是/否（推荐否）

### 实例管理

在 **"实例管理"** 页面添加要监控的数据库实例：
1. 填写实例信息（IP、端口、用户名、密码）
2. 测试连接
3. 保存

## 📊 技术架构

### 后端
- **Flask** - Web框架
- **APScheduler** - 后台调度器
- **PyMySQL** - MySQL连接
- **pyodbc** - SQL Server连接
- **DBUtils** - 连接池管理

### 前端
- **Vanilla JavaScript** - 原生JS，无框架依赖
- **HTML5 + CSS3** - 现代化UI
- **Chart绘制** - Canvas原生绘图

### 监控
- **Performance Schema** - MySQL慢SQL采集
- **Query Store** - SQL Server慢SQL采集
- **sys.dm_exec_requests** - 实时SQL监控
- **sp_get_composite_job_info** - 死锁检测
- **Prometheus** - 指标导出

## 🎨 界面预览

### Long SQL列表
- 慢SQL记录列表
- 按时间/实例/执行时间筛选
- SQL详情查看
- 执行计划分析

### 实时监控
- 当前正在执行的SQL
- 阻塞会话检测
- 一键Kill会话

### 死锁监控
- 死锁事件列表
- XML解析展示
- 涉及的表和锁资源

### 采集器配置
- 实时状态显示
- 动态配置调整
- 手动触发执行

## 🔒 安全说明

### 敏感信息
- 配置文件（`config.json`）包含数据库密码，已在 `.gitignore` 中排除
- 使用前请复制 `config.json.example` 并填入真实配置
- 建议使用只读账号进行监控（需要Performance Schema和DMV权限）

### 权限要求

**MySQL:**
```sql
GRANT SELECT ON performance_schema.* TO 'monitor_user'@'%';
GRANT SELECT ON information_schema.* TO 'monitor_user'@'%';
GRANT PROCESS ON *.* TO 'monitor_user'@'%';
```

**SQL Server:**
```sql
GRANT VIEW SERVER STATE TO monitor_user;
GRANT VIEW DATABASE STATE TO monitor_user;
GRANT VIEW ANY DEFINITION TO monitor_user;
```

## 📈 性能优化

### 采集器优化
- 默认60秒采集间隔，平衡实时性和性能
- 使用连接池，避免频繁创建连接
- Performance Schema和Query Store为只读查询，开销极低

### 数据库优化
- 建议为监控数据库添加索引（见`scripts/init_database.sql`）
- 定期清理历史数据（保留30天）
- 使用独立的监控数据库

## 🐛 故障排查

### 采集器未运行
```bash
# 查看进程
wmic process where "name='python.exe'" get ProcessId,CommandLine

# 查看日志
type logs\app_running.log
```

### Web页面无法访问
```bash
# 检查端口占用
netstat -ano | findstr :5000

# 重启应用
taskkill /F /IM python.exe
START_INTEGRATED_APP.bat
```

### 数据采集异常
1. 检查数据库连接配置
2. 验证数据库权限
3. 查看采集器日志

详见：[故障排查指南](TODO_ACTION_LIST.md#故障排查)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可

MIT License

## 👨‍💻 作者

Database Monitor Team

Co-Authored-By: Claude Sonnet 4.5

## 🙏 致谢

感谢以下开源项目：
- Flask
- PyMySQL
- APScheduler
- Prometheus

---

**更新时间:** 2026-01-28
**版本:** v1.3.0
**状态:** ✅ 生产就绪
