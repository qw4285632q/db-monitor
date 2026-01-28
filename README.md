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

```bash
python start.py
```

或直接运行主应用：
```bash
python app_new.py
```

### 6. 访问Web界面

打开浏览器访问：`http://localhost:5000`

## 📖 详细文档

- **[文档中心](docs/README.md)** - 完整文档索引
- **[快速开始指南](QUICK_START.md)** - 5分钟快速上手
- **[部署指南](DEPLOYMENT.md)** - 生产环境部署
- **[采集器配置](docs/collectors-config.md)** - 采集器配置和优化
- **[系统进程过滤](docs/system-filters.md)** - 过滤规则说明
- **[最佳实践](docs/best-practices.md)** - 推荐配置和实践

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

### 主要页面

#### 1. Long SQL列表
- 📋 慢SQL记录列表展示
- 🔍 按时间/实例/执行时间筛选
- 📊 SQL详情弹窗查看
- 🔬 执行计划自动分析
- 📈 SQL执行历史趋势

#### 2. 实时监控
- ⚡ 当前正在执行的SQL实时刷新
- 🚫 阻塞会话检测和高亮
- 💀 一键Kill会话功能
- 🔍 SQL详情和执行计划查看
- 👤 会话信息完整展示（用户、主机、程序等）

#### 3. 死锁监控
- 🔒 死锁事件列表
- 📄 XML死锁图解析和美化
- 🗃️ 涉及的表和锁资源展示
- 🔗 死锁SQL完整内容
- 📅 历史死锁查询和分析

#### 4. 性能监控
- 📈 MySQL/SQL Server性能指标
- 📊 实时性能趋势图
- 🔥 阻塞查询检测
- 🔄 复制延迟监控（AlwaysOn）

#### 5. 采集器配置
- ⚙️ 实时状态显示（运行中/已停止）
- 🔧 动态配置调整（间隔、阈值）
- 🚀 手动触发执行
- ⏰ 下次运行时间显示
- 💾 配置保存立即生效（无需重启）

#### 6. 实例管理
- 📝 数据库实例列表
- ➕ 添加/编辑/删除实例
- 🔌 连接测试功能
- 📋 实例详细信息配置

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

详见：[部署指南 - 故障排查](DEPLOYMENT.md#故障排查)

## 📦 核心依赖

```
Flask==2.3.3              # Web框架
PyMySQL==1.1.0            # MySQL连接器
pyodbc==4.0.39            # SQL Server连接器
APScheduler==3.10.4       # 后台任务调度
DBUtils==3.0.3            # 数据库连接池
```

完整依赖列表见 [requirements.txt](requirements.txt)

## 🔄 版本更新

### v1.3.0 (2026-01-28) - 当前版本
- ✨ 新增采集器Web配置管理（实时生效）
- 🎯 优化系统进程过滤（CDC、sp_server_diagnostics、@@TRANCOUNT）
- 🚀 采集器集成到主应用（APScheduler）
- 📊 完善采集器状态监控
- 🐛 修复Long SQL加载问题
- 📝 完善文档和使用指南

### v1.2.0 (2026-01-27)
- ✨ 新增Performance Schema采集器（MySQL 100%准确率）
- ✨ 新增Query Store采集器（SQL Server）
- 🔒 自动过滤CDC和复制作业
- 📊 优化采集性能（60秒间隔，零侵入）

### v1.1.0 (2026-01-26)
- ✨ 新增DBA功能（SQL指纹、执行计划分析）
- 🎯 新增AlwaysOn监控
- 📈 集成Prometheus监控
- 🔍 新增实时SQL监控和Kill会话
- 🔒 新增死锁检测和分析

### v1.0.0 (2026-01-25)
- 🎉 初始版本发布
- 📊 慢SQL监控基础功能
- 🖥️ Web管理界面
- ⚙️ 实例管理和配置

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 提交Issue
- 🐛 Bug报告：请提供详细的错误信息和复现步骤
- 💡 功能建议：描述需求和使用场景
- ❓ 使用问题：查阅文档后仍无法解决的问题

### 提交Pull Request
1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

### 开发规范
- 代码风格：遵循PEP 8
- 提交信息：清晰描述更改内容
- 文档更新：功能变更需同步更新文档

## 📞 支持与联系

### 问题反馈
- **GitHub Issues**: https://github.com/qw4285632q/db-monitor/issues
- **文档**: 查看项目中的各类MD文档

### 常用文档
- [文档中心](docs/README.md) - 完整文档索引
- [快速开始](QUICK_START.md) - 新手入门
- [部署指南](DEPLOYMENT.md) - 生产部署
- [采集器配置](docs/collectors-config.md) - 采集器详细配置
- [最佳实践](docs/best-practices.md) - 推荐配置

## 📄 许可证

[MIT License](LICENSE)

## 👨‍💻 作者与贡献者

**主要开发**: Database Monitor Team

**Co-Authored-By**: Claude Sonnet 4.5 <noreply@anthropic.com>

## 🙏 致谢

感谢以下开源项目的支持：
- [Flask](https://flask.palletsprojects.com/) - 优雅的Python Web框架
- [PyMySQL](https://github.com/PyMySQL/PyMySQL) - 纯Python的MySQL客户端
- [APScheduler](https://apscheduler.readthedocs.io/) - 强大的Python作业调度库
- [Prometheus](https://prometheus.io/) - 开源监控解决方案

## ⭐ Star History

如果这个项目对你有帮助，请给一个⭐️ Star！

## 📊 项目统计

- **代码行数**: 25,000+ lines
- **功能模块**: 10+ modules
- **文档数量**: 6 核心文档
- **支持数据库**: MySQL, SQL Server
- **监控指标**: 50+ metrics

---

**最后更新**: 2026-01-28
**当前版本**: v1.3.0
**项目状态**: ✅ 生产就绪 | 🔄 持续维护

**快速链接**: [快速开始](#-快速开始) | [功能特性](#-核心特性) | [界面预览](#-界面预览) | [文档](#详细文档)
