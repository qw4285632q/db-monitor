# 更新日志

## 2026-01-26 - 重大更新

### ✅ 问题修复

#### 1. 数据库初始化脚本更新
**问题:** Web界面的"初始化数据库"功能未包含最新的表结构

**修复内容:**
- ✅ 更新 `app_new.py` 的 `init_database()` 函数
- ✅ 包含 `long_running_sql_log` 表的所有新增字段:
  - `sql_fingerprint` - SQL指纹
  - `rows_examined` - 扫描行数
  - `rows_sent` - 返回行数
  - `execution_plan` - 执行计划(JSON)
  - `index_used` - 使用的索引
  - `full_table_scan` - 是否全表扫描
  - `wait_type`, `wait_resource` - 等待信息
  - `alert_sent` - 告警状态
- ✅ 完整创建 `deadlock_log` 表
- ✅ 创建 `monitor_alert_config` 和 `alert_history` 表
- ✅ 插入默认告警配置

**使用方法:**
1. 访问 http://localhost:5000
2. 导航栏 → 系统配置
3. 点击"初始化数据库"按钮

---

### ✨ 新增功能

#### 2. 企业微信告警Web配置界面

**问题:** 之前只能手动编辑 `alert_config.json` 文件配置告警

**新增内容:**
- ✅ Web界面配置企业微信告警
  - Webhook地址输入框
  - 启用/禁用开关
  - 测试按钮（发送测试消息）

- ✅ 钉钉告警配置（可选）
  - Webhook地址
  - 加签密钥
  - 启用/禁用开关
  - 测试按钮

- ✅ 告警规则配置
  - 慢SQL告警阈值（分钟）
  - 死锁始终告警
  - 告警间隔（秒）

- ✅ 新增后端API
  - `GET /api/alert-config` - 获取告警配置
  - `POST /api/alert-config` - 保存告警配置
  - `POST /api/alert-config/test` - 测试告警

**使用方法:**
1. 访问 http://localhost:5000
2. 导航栏 → 系统配置
3. 滚动到"告警配置"部分
4. 填写企业微信Webhook地址
5. 选择"启用"
6. 点击"测试企业微信"验证配置
7. 点击"保存告警配置"

**获取企业微信Webhook:**
1. 企业微信PC端
2. 选择群聊 → 右键菜单
3. 添加群机器人
4. 填写机器人名称 → 创建
5. 复制Webhook地址（格式: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...）

---

## 更新后的功能清单

### 数据库监控
- ✅ MySQL慢SQL实时监控
- ✅ SQL Server慢SQL监控
- ✅ 死锁自动检测
- ✅ 执行计划采集
- ✅ SQL指纹去重
- ✅ 全表扫描检测
- ✅ 索引使用分析

### 告警功能
- ✅ 企业微信告警（Web界面配置）
- ✅ 钉钉告警（Web界面配置）
- ✅ 邮件告警（配置支持）
- ✅ 慢SQL超时告警
- ✅ 死锁实时告警
- ✅ 告警规则可配置
- ✅ 测试功能

### Web界面
- ✅ 监控面板（慢SQL列表、统计图表）
- ✅ 死锁监控（死锁历史记录）
- ✅ 实例管理（添加/编辑/删除/测试）
- ✅ 系统配置
  - 数据库连接配置
  - 应用配置
  - **告警配置（新增）**
  - 测试连接
  - 初始化数据库

### 数据采集
- ✅ 10秒实时采集（默认）
- ✅ 自适应采集间隔
- ✅ 并发采集多实例
- ✅ MySQL + SQL Server支持

---

## 使用指南

### 1. 首次部署

```bash
# 启动Web服务
cd C:\运维工具类\database-monitor
python app_new.py

# 访问 http://localhost:5000
# 进入"系统配置" → 填写数据库配置 → 测试连接 → 初始化数据库
```

### 2. 配置告警

```bash
# 方式1: Web界面（推荐）
# 访问 http://localhost:5000 → 系统配置 → 告警配置
# 填写Webhook → 测试 → 保存

# 方式2: 手动编辑
copy alert_config.example.json alert_config.json
notepad alert_config.json
```

### 3. 添加监控实例

```bash
# 访问 http://localhost:5000 → 实例管理 → 添加实例
# 填写实例信息 → 测试连接 → 保存
```

### 4. 启动采集器

```bash
cd scripts

# 带告警功能
python collector_enhanced.py --daemon --interval 10 --alert-config ../alert_config.json

# 不带告警
python collector_enhanced.py --daemon --interval 10
```

---

## 测试告警

### Web界面测试
1. 访问 http://localhost:5000
2. 系统配置 → 告警配置
3. 点击"测试企业微信"按钮
4. 检查企业微信群是否收到测试消息

### 命令行测试
```bash
python test_alert.py
```

---

## 文件变更清单

### 后端更新
- ✅ `app_new.py` - 新增告警配置API、更新数据库初始化函数
- ✅ `utils/alert.py` - 企业微信/钉钉/邮件告警模块（已有）
- ✅ `scripts/collector_enhanced.py` - 增强版采集器（已有）
- ✅ `scripts/sqlserver_collector.py` - SQL Server采集器（已有）

### 前端更新
- ✅ `static/index.html` - 新增告警配置界面

### 数据库更新
- ✅ `scripts/init_database.sql` - 完整表结构（已有）
- ✅ Web初始化功能 - 已同步最新结构

### 文档更新
- ✅ `DEPLOYMENT.md` - 完整部署指南
- ✅ `QUICK_START.md` - 快速启动指南
- ✅ `UPDATE_LOG.md` - 更新日志（本文件）

---

## API文档

### 新增API

#### 获取告警配置
```http
GET /api/alert-config
```

**响应示例:**
```json
{
  "success": true,
  "data": {
    "wecom": {
      "webhook": "https://qyapi.weixin.qq.com/...",
      "enabled": true
    },
    "dingtalk": {
      "webhook": "",
      "secret": "",
      "enabled": false
    },
    "alert_rules": {
      "slow_sql_threshold_minutes": 10,
      "deadlock_always_alert": true,
      "alert_interval_seconds": 300
    }
  }
}
```

#### 保存告警配置
```http
POST /api/alert-config
Content-Type: application/json

{
  "wecom": {
    "webhook": "https://qyapi.weixin.qq.com/...",
    "enabled": true
  },
  "alert_rules": {
    "slow_sql_threshold_minutes": 10,
    "deadlock_always_alert": true
  }
}
```

#### 测试告警
```http
POST /api/alert-config/test
Content-Type: application/json

{
  "channel": "wecom"
}
```

**支持的channel:**
- `wecom` - 企业微信
- `dingtalk` - 钉钉
- `email` - 邮件

---

## 兼容性说明

### 向后兼容
- ✅ 已有的 `alert_config.json` 文件仍然有效
- ✅ Web配置会自动读取和更新现有文件
- ✅ 旧的采集器 `collect_long_sql.py` 仍可使用
- ✅ 现有数据库表结构可通过"初始化数据库"升级

### 升级建议
1. **数据库:** 建议重新运行"初始化数据库"以添加新字段
2. **采集器:** 建议切换到 `collector_enhanced.py`
3. **告警配置:** 建议通过Web界面配置，更直观安全

---

## 常见问题

### Q1: 告警配置保存后不生效？
**A:** 需要重启采集器让配置生效
```bash
# 停止旧的采集器进程
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *collector*"

# 启动新的采集器
cd scripts
python collector_enhanced.py --daemon --interval 10 --alert-config ../alert_config.json
```

### Q2: 测试告警失败？
**A:** 检查以下几点：
1. Webhook地址是否正确
2. 网络是否可以访问企业微信API
3. 机器人是否被禁用
4. 查看浏览器控制台是否有错误

### Q3: 数据库初始化提示字段已存在？
**A:** 这是正常的，`CREATE TABLE IF NOT EXISTS` 不会覆盖现有表。如需完全重建：
```sql
DROP TABLE IF EXISTS deadlock_log;
DROP TABLE IF EXISTS long_running_sql_log;
-- 然后重新初始化
```

### Q4: 旧数据会丢失吗？
**A:** 不会。新增字段允许NULL，不影响现有数据。

---

## 下一步计划

### 即将推出
- [ ] WebSocket实时推送
- [ ] 告警历史查看
- [ ] Oracle数据库支持完善
- [ ] PostgreSQL数据库支持
- [ ] SQL分析报告
- [ ] 性能趋势预测

### 欢迎建议
如有功能建议或问题反馈，请联系管理员。

---

**更新日期:** 2026-01-26
**版本:** v1.2.0
**服务地址:** http://localhost:5000
