# 数据库Long SQL监控系统

实时监控数据库中长时间运行的SQL语句，帮助DBA快速定位性能问题。

## 功能特性

- **多数据库支持**: 支持 Oracle、MySQL、PostgreSQL 数据库
- **实时监控**: 自动采集长时间运行的SQL语句
- **Web界面**: 直观的数据展示和查询界面
- **告警分级**: 自动根据运行时间分级(正常/警告/严重)
- **统计分析**: 提供各维度的统计图表
- **分页查询**: 支持大数据量的分页浏览
- **配置管理**: Web界面配置数据库连接和应用参数
- **实例管理**: 可视化管理被监控的数据库实例

## 项目结构

```
database-monitor/
├── app.py                    # Flask后端应用
├── index.html                # 前端页面(开发)
├── requirements.txt          # Python依赖
├── start.bat                 # Windows启动脚本
├── README.md                 # 项目说明
├── static/
│   └── index.html           # 前端页面(生产)
├── scripts/
│   ├── init_database.sql    # 数据库初始化脚本
│   ├── generate_test_data.py # 测试数据生成
│   └── collect_long_sql.py  # SQL采集脚本
└── logs/                     # 日志目录
```

## 快速开始

### 1. 环境要求

- Python 3.8+
- MySQL 5.7+ (用于存储监控数据)
- 被监控的数据库(Oracle/MySQL/PostgreSQL)

### 2. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# Oracle支持(可选)
pip install cx_Oracle

# PostgreSQL支持(可选)
pip install psycopg2-binary
```

### 3. 初始化数据库

```bash
# 登录MySQL执行初始化脚本
mysql -u root -p < scripts/init_database.sql
```

### 4. 配置数据库连接

编辑 `app.py` 中的数据库配置:

```python
DB_CONFIG = {
    'host': '192.168.11.85',      # 数据库服务器
    'user': 'root',                # 用户名
    'password': 'your_password',   # 密码
    'database': 'db_monitor',      # 数据库名
    'charset': 'utf8mb4'
}
```

或使用环境变量:

```bash
export DB_HOST=192.168.11.85
export DB_USER=root
export DB_PASSWORD=your_password
export DB_NAME=db_monitor
```

### 5. 生成测试数据(可选)

```bash
python scripts/generate_test_data.py
```

### 6. 启动应用

```bash
# Windows
start.bat

# Linux/Mac
python app.py
```

访问 http://localhost:5000 查看监控界面。

## API接口

### 监控数据接口

| 接口 | 方法 | 说明 | 参数 |
|------|------|------|------|
| `/api/health` | GET | 健康检查 | - |
| `/api/long_sql` | GET | 获取长时间SQL | hours, instance_id, min_minutes, page, page_size |
| `/api/statistics` | GET | 获取统计数据 | hours |

### 配置管理接口

| 接口 | 方法 | 说明 | 参数 |
|------|------|------|------|
| `/api/config` | GET | 获取当前配置 | - |
| `/api/config` | POST | 更新配置 | database, app (JSON) |
| `/api/config/test` | POST | 测试数据库连接 | host, port, user, password, database |
| `/api/config/init-db` | POST | 初始化数据库表 | - |

### 实例管理接口

| 接口 | 方法 | 说明 | 参数 |
|------|------|------|------|
| `/api/instances` | GET | 获取实例列表 | - |
| `/api/instances` | POST | 添加实例 | db_project, db_ip, db_port, ... (JSON) |
| `/api/instances/<id>` | PUT | 更新实例 | db_project, db_ip, ... (JSON) |
| `/api/instances/<id>` | DELETE | 删除实例 | - |

### 示例请求

```bash
# 获取最近24小时运行超过5分钟的SQL
curl "http://localhost:5000/api/long_sql?hours=24&min_minutes=5&page=1&page_size=20"

# 获取统计信息
curl "http://localhost:5000/api/statistics?hours=24"
```

## 数据采集

### 手动采集

```bash
python scripts/collect_long_sql.py
```

### 持续采集(守护进程)

```bash
# 每60秒采集一次
python scripts/collect_long_sql.py --daemon --interval 60

# 设置长时间SQL阈值为120秒
python scripts/collect_long_sql.py --daemon --threshold 120
```

### 定时任务(cron)

```bash
# 每分钟采集一次
* * * * * /path/to/venv/bin/python /path/to/scripts/collect_long_sql.py >> /path/to/logs/collect.log 2>&1
```

## 告警级别

| 级别 | 运行时间 | 颜色 |
|------|----------|------|
| 正常 | ≤5分钟 | 绿色 |
| 警告 | 5-10分钟 | 橙色 |
| 严重 | >10分钟 | 红色 |

## 数据库表结构

### db_instance_info - 数据库实例信息

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| db_project | VARCHAR(100) | 项目名称 |
| db_ip | VARCHAR(50) | 数据库IP |
| db_port | INT | 数据库端口 |
| db_type | VARCHAR(20) | 数据库类型 |
| status | TINYINT | 状态(1启用/0禁用) |

### long_running_sql_log - 长时间SQL日志

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| db_instance_id | INT | 实例ID |
| session_id | VARCHAR(50) | 会话ID |
| sql_text | VARCHAR(4000) | SQL文本 |
| username | VARCHAR(100) | 执行用户 |
| elapsed_minutes | DECIMAL | 运行分钟数 |
| detect_time | DATETIME | 检测时间 |

## 生产部署

### 使用Gunicorn (Linux)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 使用Waitress (Windows)

```bash
pip install waitress
waitress-serve --port=5000 app:app
```

### 使用Nginx反向代理

```nginx
server {
    listen 80;
    server_name monitor.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 常见问题

### Q: 页面显示"暂无数据"?

A: 检查以下几点:
1. 数据库连接是否正确
2. 是否已运行数据采集脚本
3. 查询时间范围是否正确

### Q: Oracle采集报错?

A: 确保已安装cx_Oracle并配置Oracle客户端:
```bash
pip install cx_Oracle
# 配置ORACLE_HOME和LD_LIBRARY_PATH
```

### Q: 如何清理历史数据?

A: 调用存储过程:
```sql
CALL cleanup_old_data(30);  -- 保留最近30天数据
```

## 更新日志

### v1.0.0 (2025-01)
- 初始版本发布
- 支持Oracle/MySQL/PostgreSQL
- Web监控界面
- 数据采集脚本

## License

MIT License
