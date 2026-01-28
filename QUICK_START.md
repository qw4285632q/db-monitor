# 快速启动指南

## 一、5分钟快速部署

### 1. 启动Web服务
```bash
cd C:\运维工具类\database-monitor
python app_new.py
```
访问: http://localhost:5000

### 2. 配置数据库
1. 打开浏览器 → 系统配置
2. 填写数据库连接信息
3. 点击"测试连接"
4. 点击"初始化数据库"

### 3. 添加监控实例
1. 导航栏 → 实例管理
2. 点击"添加实例"
3. 填写实例信息(IP、端口、用户名、密码)
4. 点击"测试" → "保存"

### 4. 启动采集器
```bash
cd scripts
python collector_enhanced.py --daemon --interval 10
```

### 5. 配置告警(可选)
```bash
# 复制配置
copy alert_config.example.json alert_config.json

# 编辑配置，填入企业微信Webhook
notepad alert_config.json

# 重启采集器
python collector_enhanced.py --daemon --interval 10 --alert-config ../alert_config.json
```

---

## 二、功能概览

| 功能 | 说明 | 入口 |
|------|------|------|
| 监控面板 | 查看慢SQL统计和列表 | 导航栏 → 监控面板 |
| 死锁监控 | 查看死锁历史记录 | 导航栏 → 死锁监控 |
| 实例管理 | 添加/编辑/删除监控实例 | 导航栏 → 实例管理 |
| 系统配置 | 配置数据库和应用参数 | 导航栏 → 系统配置 |

---

## 三、主要特性

### ✅ 已实现功能

1. **MySQL监控**
   - Performance Schema慢SQL分析
   - 正在运行SQL实时监控
   - 死锁自动检测
   - 执行计划采集
   - SQL指纹去重

2. **SQL Server监控**
   - DMV慢SQL查询
   - Extended Events死锁监控
   - 执行计划XML解析
   - 阻塞会话检测

3. **企业微信告警**
   - 慢SQL超时告警
   - 死锁实时告警
   - Markdown格式消息
   - 多渠道支持(钉钉、邮件)

4. **Web界面**
   - 实时统计图表
   - SQL详情查看
   - 实例管理
   - 系统配置
   - 死锁历史

---

## 四、采集器命令参数

```bash
# 基本使用
python collector_enhanced.py --daemon

# 完整参数
python collector_enhanced.py \
  --daemon \                          # 后台运行
  --interval 10 \                     # 采集间隔10秒
  --threshold 60 \                    # 慢SQL阈值60秒
  --alert-threshold 10 \              # 告警阈值10分钟
  --alert-config alert_config.json    # 告警配置文件

# 单次采集(测试用)
python collector_enhanced.py

# 自定义间隔
python collector_enhanced.py --daemon --interval 5   # 高频5秒
python collector_enhanced.py --daemon --interval 30  # 常规30秒
python collector_enhanced.py --daemon --interval 120 # 低频2分钟
```

---

## 五、企业微信告警配置

### 获取Webhook地址
1. 企业微信PC端
2. 选择群聊 → 右键 → 添加群机器人
3. 填写名称 → 创建 → 复制Webhook地址

### 配置文件 (alert_config.json)
```json
{
  "wecom": {
    "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE",
    "enabled": true
  },
  "alert_rules": {
    "slow_sql_threshold_minutes": 10,
    "deadlock_always_alert": true
  }
}
```

### 测试告警
```bash
cd utils
python
>>> from alert import WeComAlert
>>> alert = WeComAlert('YOUR_WEBHOOK_URL')
>>> alert.send('测试', '这是一条测试消息', 'INFO')
```

---

## 六、常用SQL

### 查看慢SQL
```sql
USE db_monitor;

-- 最近24小时慢SQL
SELECT * FROM long_running_sql_log
WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY elapsed_minutes DESC
LIMIT 20;

-- 按指纹分组统计
SELECT sql_fingerprint, COUNT(*) as count, AVG(elapsed_minutes) as avg_time
FROM long_running_sql_log
WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY sql_fingerprint
ORDER BY count DESC;
```

### 查看死锁
```sql
-- 最近24小时死锁
SELECT * FROM deadlock_log
WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY detect_time DESC;

-- 死锁统计
SELECT
    DATE(detect_time) as date,
    COUNT(*) as deadlock_count,
    COUNT(DISTINCT db_instance_id) as affected_instances
FROM deadlock_log
WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(detect_time);
```

### 清理历史数据
```sql
-- 清理30天前的数据
CALL cleanup_old_data(30);

-- 手动清理
DELETE FROM long_running_sql_log WHERE detect_time < DATE_SUB(NOW(), INTERVAL 30 DAY);
DELETE FROM deadlock_log WHERE detect_time < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

---

## 七、目录结构

```
database-monitor/
├── app_new.py                    # Web服务主程序
├── config.json                   # 数据库配置(自动生成)
├── alert_config.json            # 告警配置
├── requirements.txt             # Python依赖
├── start.bat                    # 启动脚本
├── README.md                    # 项目说明
├── DEPLOYMENT.md                # 部署指南
├── QUICK_START.md               # 快速开始(本文件)
├── static/
│   └── index.html              # 前端页面
├── scripts/
│   ├── collector_enhanced.py   # 增强版采集器★
│   ├── sqlserver_collector.py  # SQL Server采集器
│   ├── init_database.sql       # 数据库初始化脚本
│   ├── generate_test_data.py   # 测试数据生成
│   └── collect_long_sql.py     # 旧版采集器
└── utils/
    ├── alert.py                # 告警模块★
    └── __init__.py
```

**★ 标记为核心文件**

---

## 八、故障排查

### 问题1: 采集器启动后没有数据

**检查步骤:**
```bash
# 1. 测试数据库连接
mysql -h 192.168.11.85 -u root -p db_monitor

# 2. 检查实例配置
SELECT * FROM db_instance_info WHERE status = 1;

# 3. 手动执行采集
cd scripts
python collector_enhanced.py

# 4. 查看采集器日志
# (如果有日志文件)
```

### 问题2: 企业微信收不到告警

**测试Webhook:**
```bash
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"测试消息\"}}"
```

### 问题3: Web界面打不开

**检查端口:**
```bash
# Windows
netstat -ano | findstr :5000

# 如果端口被占用，修改 app_new.py 最后一行:
app.run(host='0.0.0.0', port=5001, debug=True)
```

### 问题4: SQL Server监控不工作

**安装驱动:**
1. 下载ODBC Driver 17: https://go.microsoft.com/fwlink/?linkid=2249006
2. 安装pyodbc: `pip install pyodbc`
3. 测试: `python scripts/sqlserver_collector.py`

---

## 九、性能建议

### 采集间隔建议

| 环境 | 间隔 | 阈值 | 说明 |
|------|------|------|------|
| 生产(高负载) | 5秒 | 30秒 | 实时性要求高 |
| 生产(常规) | 10秒 | 60秒 | 推荐配置 |
| 测试/开发 | 30秒 | 60秒 | 降低开销 |
| 归档/低频 | 300秒 | 300秒 | 最小开销 |

### 数据清理

```bash
# 建议保留时长
长SQL日志: 30天
死锁日志: 90天(死锁相对少见，建议保留更久)
告警历史: 90天
```

### 资源消耗

| 组件 | CPU | 内存 | 磁盘IO |
|------|-----|------|--------|
| Web服务 | < 5% | 100MB | 极低 |
| 采集器(10秒) | < 5% | 50MB | 低 |
| 数据库(1年数据) | - | - | ~5GB |

---

## 十、下一步

### 扩展功能建议
1. ✅ WebSocket实时推送
2. ✅ SQL执行计划对比
3. ✅ 历史趋势分析
4. ✅ Oracle数据库支持
5. ✅ PostgreSQL数据库支持

### 学习资源
- MySQL Performance Schema: https://dev.mysql.com/doc/refman/8.0/en/performance-schema.html
- SQL Server DMV: https://docs.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/
- 企业微信机器人: https://work.weixin.qq.com/api/doc/90000/90136/91770

---

## 联系支持

- 部署问题: 查看 DEPLOYMENT.md
- 功能说明: 查看 README.md
- API文档: http://localhost:5000/api/health

**快速启动完成！访问 http://localhost:5000 开始使用。**
