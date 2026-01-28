# 数据库监控系统 - 部署和使用指南

## 功能特性

✅ **慢SQL实时监控** - 支持MySQL和SQL Server
✅ **死锁自动检测** - 实时捕获并告警
✅ **企业微信告警** - 支持钉钉、邮件多渠道
✅ **执行计划采集** - 自动分析SQL性能
✅ **SQL指纹去重** - 智能识别相同模式SQL
✅ **可视化展示** - 图表、统计、实时刷新
✅ **实例管理** - Web界面管理监控实例

---

## 快速部署

### 1. 环境准备

```bash
# Python 3.8+
python --version

# 安装依赖
cd C:\运维工具类\database-monitor
pip install -r requirements.txt

# SQL Server支持(可选)
# 需要先安装 ODBC Driver 17 for SQL Server
# 下载: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
```

### 2. 数据库初始化

```bash
# 方式1: 使用MySQL命令行
mysql -h 192.168.11.85 -u root -p < scripts/init_database.sql

# 方式2: 使用Web界面
# 1. 启动服务
# 2. 访问 http://localhost:5000
# 3. 进入"系统配置"页面
# 4. 填写数据库连接信息
# 5. 点击"测试连接"
# 6. 点击"初始化数据库"
```

### 3. 配置企业微信告警

```bash
# 复制配置模板
copy alert_config.example.json alert_config.json

# 编辑 alert_config.json
{
  "wecom": {
    "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY",
    "enabled": true
  },
  "alert_rules": {
    "slow_sql_threshold_minutes": 10,
    "deadlock_always_alert": true
  }
}
```

**获取企业微信Webhook地址:**
1. 企业微信PC端 → 群聊
2. 右键群聊 → 添加群机器人
3. 创建机器人 → 复制Webhook地址

### 4. 启动服务

```bash
# 方式1: Windows批处理
start.bat

# 方式2: 直接运行
python app_new.py

# 访问地址
http://localhost:5000
```

### 5. 启动采集器

```bash
# 进入scripts目录
cd scripts

# 增强版采集器(推荐)
python collector_enhanced.py --daemon --interval 10 --alert-config ../alert_config.json

# 参数说明
--daemon           # 守护进程模式
--interval 10      # 采集间隔10秒
--threshold 60     # 慢SQL阈值60秒
--alert-threshold 10  # 告警阈值10分钟
--alert-config alert_config.json  # 告警配置文件

# 后台运行(Windows)
start /B python collector_enhanced.py --daemon --interval 10

# 后台运行(Linux)
nohup python collector_enhanced.py --daemon --interval 10 > collector.log 2>&1 &
```

---

## 功能使用

### 监控面板

**访问:** http://localhost:5000

**功能:**
- 📊 实时统计 - 实例数、SQL总数、平均时长、死锁数
- 📈 趋势图表 - 实例分布、时间趋势
- 🔍 SQL列表 - 查询、过滤、分页
- ⚙️ 自动刷新 - 可配置刷新间隔

**查询筛选:**
- 时间范围: 1小时 ~ 7天
- 实例筛选: 按项目/IP筛选
- 最小执行时间: 自定义阈值
- 每页条数: 10 ~ 100条

### 死锁监控

**访问:** 导航栏 → 死锁监控

**功能:**
- 🔴 死锁列表 - 时间、实例、会话、资源
- 📝 详细信息 - 受害者SQL、阻塞者SQL
- 🔔 实时告警 - 检测到死锁立即推送企业微信

**死锁详情包含:**
- 死锁时间
- 受害者会话和SQL
- 阻塞者会话和SQL
- 等待资源
- 锁模式
- 解决动作

### 实例管理

**访问:** 导航栏 → 实例管理

**功能:**
- ➕ 添加实例 - 支持MySQL/SQL Server/Oracle/PostgreSQL
- ✏️ 编辑实例 - 修改连接信息
- 🧪 测试连接 - 验证配置正确性
- 🗑️ 删除实例 - 删除实例及关联数据

**添加MySQL实例示例:**
```
项目名称: 生产环境主库
数据库类型: MySQL
IP地址: 192.168.1.100
端口: 3306
实例名: prod-mysql-01
连接用户: monitor
连接密码: ******
环境: production
状态: 启用
```

**添加SQL Server实例示例:**
```
项目名称: 订单系统数据库
数据库类型: SQLServer
IP地址: 192.168.1.200
端口: 1433
连接用户: sa
连接密码: ******
环境: production
状态: 启用
```

### 系统配置

**访问:** 导航栏 → 系统配置

**数据库连接配置:**
- 数据库主机
- 端口
- 用户名/密码
- 数据库名
- 字符集

**应用配置:**
- 自动刷新间隔(秒): 页面刷新频率
- 警告阈值(分钟): SQL执行时间警告线
- 严重阈值(分钟): SQL执行时间严重告警
- 默认查询时间(小时): 默认查询范围

**操作:**
- 测试连接 - 验证数据库连接
- 保存配置 - 持久化到config.json
- 初始化数据库 - 创建表结构

---

## 告警配置

### 企业微信告警示例

**慢SQL告警消息:**
```
⚠️ 慢SQL告警

级别: CRITICAL
时间: 2026-01-26 12:00:00

数据库实例: 生产环境主库
实例地址: 192.168.1.100:3306
执行时长: 15.50 分钟
用户名: app_user
客户端: 192.168.1.200
程序: java-app

SQL语句:
SELECT * FROM big_table WHERE status = 1...

检测时间: 2026-01-26 12:00:00
扫描行数: 1000000
返回行数: 500
```

**死锁告警消息:**
```
🔴 数据库死锁告警

级别: CRITICAL
时间: 2026-01-26 12:00:00

数据库实例: 生产环境主库
实例地址: 192.168.1.100:3306
数据库类型: MySQL
死锁时间: 2026-01-26 12:00:00

受害者会话: 12345
受害者SQL:
UPDATE orders SET status = 1 WHERE id = 100

阻塞者会话: 67890
阻塞者SQL:
UPDATE products SET stock = stock - 1 WHERE id = 50

等待资源: orders:PRIMARY
锁模式: X

处理建议:
1. 检查SQL是否使用了合适的索引
2. 优化事务大小，减少持锁时间
3. 调整应用程序访问顺序
```

### 告警规则配置

编辑 `alert_config.json`:

```json
{
  "wecom": {
    "webhook": "YOUR_WEBHOOK_URL",
    "enabled": true
  },
  "dingtalk": {
    "webhook": "",
    "secret": "",
    "enabled": false
  },
  "email": {
    "host": "smtp.example.com",
    "port": 465,
    "user": "alert@example.com",
    "password": "password",
    "from": "alert@example.com",
    "to": ["admin@example.com"],
    "enabled": false
  },
  "alert_rules": {
    "slow_sql_threshold_minutes": 10,
    "deadlock_always_alert": true,
    "alert_interval_seconds": 300
  }
}
```

**规则说明:**
- `slow_sql_threshold_minutes`: SQL执行超过此时长才发送告警
- `deadlock_always_alert`: 死锁是否总是发送告警
- `alert_interval_seconds`: 同一问题的告警间隔

---

## 性能优化建议

### 采集间隔调整

```bash
# 高频监控(更实时，资源消耗大)
python collector_enhanced.py --daemon --interval 5 --threshold 30

# 常规监控(推荐)
python collector_enhanced.py --daemon --interval 10 --threshold 60

# 低频监控(节省资源)
python collector_enhanced.py --daemon --interval 60 --threshold 300
```

### 数据清理

```bash
# 登录MySQL
mysql -h 192.168.11.85 -u root -p db_monitor

# 清理30天前的数据
CALL cleanup_old_data(30);

# 定时任务清理(Linux crontab)
0 2 * * * mysql -h 192.168.11.85 -u root -pPassword -e "CALL db_monitor.cleanup_old_data(30);"

# 定时任务清理(Windows任务计划程序)
# 创建批处理文件 cleanup.bat:
mysql -h 192.168.11.85 -u root -pPassword -e "CALL db_monitor.cleanup_old_data(30);"
# 然后在任务计划程序中设置每天凌晨2点执行
```

### 分区优化(大数据量)

对于单表数据超过1000万条的场景，建议启用分区:

```sql
-- 按月分区long_running_sql_log表
ALTER TABLE long_running_sql_log
PARTITION BY RANGE (YEAR(detect_time)*100 + MONTH(detect_time)) (
    PARTITION p202601 VALUES LESS THAN (202602),
    PARTITION p202602 VALUES LESS THAN (202603),
    PARTITION p202603 VALUES LESS THAN (202604),
    PARTITION p202604 VALUES LESS THAN (202605),
    PARTITION p202605 VALUES LESS THAN (202606),
    PARTITION p202606 VALUES LESS THAN (202607),
    PARTITION p202607 VALUES LESS THAN (202608),
    PARTITION p202608 VALUES LESS THAN (202609),
    PARTITION p202609 VALUES LESS THAN (202610),
    PARTITION p202610 VALUES LESS THAN (202611),
    PARTITION p202611 VALUES LESS THAN (202612),
    PARTITION p202612 VALUES LESS THAN (202701),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
```

---

## 常见问题

### Q1: 采集器启动后没有数据?

**检查清单:**
1. 数据库连接是否正常
2. 实例管理中是否添加了实例
3. 实例状态是否为"启用"
4. 目标数据库是否有慢SQL
5. 采集阈值是否设置过高

### Q2: 企业微信告警收不到消息?

**排查步骤:**
1. 检查Webhook地址是否正确
2. 检查alert_config.json中enabled是否为true
3. 手动测试Webhook:
```bash
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"测试消息"}}'
```
4. 查看采集器日志是否有错误

### Q3: SQL Server监控不工作?

**解决方案:**
1. 安装ODBC Driver 17:
   - 下载: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
2. 安装pyodbc:
```bash
pip install pyodbc
```
3. 测试连接:
```bash
cd scripts
python sqlserver_collector.py
```

### Q4: 性能开销有多大?

**资源消耗:**
- MySQL: 每次查询约0.1-0.5秒
- SQL Server: 每次查询约0.2-1秒
- 内存: 约50-200MB
- CPU: 几乎可忽略

**建议:**
- 生产环境: 间隔10-30秒
- 开发/测试: 间隔5-10秒
- 归档环境: 间隔60-300秒

### Q5: 如何监控Oracle数据库?

**当前状态:** Oracle采集器待完善

**临时方案:**
可以参考MySQL采集器实现，主要SQL:
```sql
-- Oracle慢SQL查询
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.machine,
    s.program,
    t.sql_id,
    t.sql_text,
    (SYSDATE - s.sql_exec_start) * 86400 as elapsed_seconds
FROM v$session s
JOIN v$sqltext t ON s.sql_id = t.sql_id
WHERE s.status = 'ACTIVE'
  AND s.username IS NOT NULL
  AND (SYSDATE - s.sql_exec_start) * 86400 >= 60
```

---

## 生产环境部署建议

### 服务化部署

**Linux Systemd服务:**

创建 `/etc/systemd/system/db-monitor.service`:
```ini
[Unit]
Description=Database Monitor Web Service
After=network.target

[Service]
Type=simple
User=monitor
WorkingDirectory=/opt/database-monitor
ExecStart=/usr/bin/python3 /opt/database-monitor/app_new.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

创建 `/etc/systemd/system/db-collector.service`:
```ini
[Unit]
Description=Database Monitor Collector
After=network.target

[Service]
Type=simple
User=monitor
WorkingDirectory=/opt/database-monitor/scripts
ExecStart=/usr/bin/python3 collector_enhanced.py --daemon --interval 10 --alert-config ../alert_config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务:
```bash
sudo systemctl daemon-reload
sudo systemctl enable db-monitor
sudo systemctl enable db-collector
sudo systemctl start db-monitor
sudo systemctl start db-collector
```

**Windows服务(使用NSSM):**

1. 下载NSSM: https://nssm.cc/download
2. 安装Web服务:
```cmd
nssm install DBMonitorWeb "C:\Python39\python.exe" "C:\运维工具类\database-monitor\app_new.py"
nssm set DBMonitorWeb AppDirectory "C:\运维工具类\database-monitor"
nssm start DBMonitorWeb
```
3. 安装采集服务:
```cmd
nssm install DBMonitorCollector "C:\Python39\python.exe" "collector_enhanced.py --daemon --interval 10"
nssm set DBMonitorCollector AppDirectory "C:\运维工具类\database-monitor\scripts"
nssm start DBMonitorCollector
```

### 反向代理(Nginx)

```nginx
server {
    listen 80;
    server_name db-monitor.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 监控建议

1. **监控采集器进程** - 确保持续运行
2. **监控告警延迟** - 确保实时性
3. **监控磁盘空间** - 避免数据库爆满
4. **定期备份配置** - config.json, alert_config.json
5. **日志轮转** - 避免日志文件过大

---

## 技术支持

- 项目地址: C:\运维工具类\database-monitor
- 文档: README.md
- 配置示例: alert_config.example.json, config.example.py

**联系方式:**
- 问题反馈: 企业微信群
- 功能建议: 提交Issue
