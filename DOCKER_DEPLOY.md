# Docker 部署指南

## 📦 快速开始

### 1. 构建和推送镜像到Harbor

**Linux/Mac:**
```bash
chmod +x build.sh
./build.sh v1.4.0
```

**Windows PowerShell:**
```powershell
.\build.ps1 v1.4.0
```

**不指定版本（使用latest）:**
```bash
./build.sh
# 或
.\build.ps1
```

### 2. 服务器部署

#### 方式一：使用docker run

```bash
# 1. 拉取镜像
docker pull harbor.uzhicai.com/midtool/db-monitor:latest

# 2. 准备配置文件
mkdir -p /data/db-monitor
cp config.json.example /data/db-monitor/config.json
vim /data/db-monitor/config.json  # 编辑配置

# 3. 运行容器
docker run -d \
  --name db-monitor \
  --restart unless-stopped \
  -p 5000:5000 \
  -v /data/db-monitor/config.json:/app/config.json:ro \
  -v /data/db-monitor/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  harbor.uzhicai.com/midtool/db-monitor:latest
```

#### 方式二：使用docker-compose（推荐）

```bash
# 1. 创建部署目录
mkdir -p /data/db-monitor
cd /data/db-monitor

# 2. 下载docker-compose.yml
wget https://raw.githubusercontent.com/qw4285632q/db-monitor/main/docker-compose.yml

# 3. 准备配置文件
cp config.json.example config.json
vim config.json  # 编辑配置

# 4. 启动服务
docker-compose up -d

# 5. 查看日志
docker-compose logs -f

# 6. 停止服务
docker-compose down
```

## 🔧 配置说明

### 必需配置文件

**config.json** - 数据库连接和应用配置

```json
{
  "database": {
    "host": "your-monitor-db-host",
    "port": 3306,
    "user": "db_monitor_user",
    "password": "your-password",
    "database": "db_monitor",
    "charset": "utf8mb4"
  },
  "app": {
    "auto_refresh_interval": 30,
    "warning_threshold": 5,
    "critical_threshold": 10,
    "default_hours": 24,
    "default_page_size": 20
  },
  "collectors": {
    "mysql": {
      "enabled": true,
      "interval": 60,
      "threshold": 2
    },
    "sqlserver": {
      "enabled": true,
      "interval": 60,
      "threshold": 2,
      "auto_enable_querystore": false
    }
  },
  "prometheus": {
    "enabled": true,
    "url": "http://prometheus-server:9090",
    "timeout": 5
  }
}
```

### 目录映射说明

| 容器路径 | 宿主机路径 | 说明 | 必需 |
|---------|-----------|------|------|
| /app/config.json | /data/db-monitor/config.json | 配置文件 | ✅ 是 |
| /app/logs | /data/db-monitor/logs | 日志目录 | ❌ 否 |
| /app/alert_config.json | /data/db-monitor/alert_config.json | 告警配置 | ❌ 否 |

### 环境变量

| 变量 | 默认值 | 说明 |
|-----|-------|------|
| TZ | Asia/Shanghai | 时区设置 |
| PYTHONUNBUFFERED | 1 | Python输出不缓冲 |

## 🚀 镜像信息

### 镜像仓库
- **Harbor地址**: harbor.uzhicai.com
- **项目**: midtool
- **镜像名**: db-monitor

### 镜像标签
- `latest` - 最新版本
- `v1.4.0` - 指定版本号
- `v1.3.0` - 历史版本

### 镜像大小
- 约 400-500 MB（含ODBC驱动）

## 📊 健康检查

容器内置健康检查：
- **检查间隔**: 30秒
- **超时时间**: 10秒
- **启动等待**: 40秒
- **重试次数**: 3次
- **检查命令**: `curl -f http://localhost:5000/`

查看健康状态：
```bash
docker ps
# 查看HEALTH列状态
```

## 🔍 故障排查

### 查看容器日志
```bash
docker logs -f db-monitor
# 或使用docker-compose
docker-compose logs -f
```

### 进入容器调试
```bash
docker exec -it db-monitor /bin/bash

# 检查配置文件
cat /app/config.json

# 检查Python进程
ps aux | grep python

# 测试数据库连接
python -c "import pymysql; print('PyMySQL OK')"
python -c "import pyodbc; print('pyodbc OK')"
```

### 常见问题

**1. 容器无法启动**
```bash
# 检查日志
docker logs db-monitor

# 常见原因：
# - config.json不存在或格式错误
# - 数据库连接失败
# - 端口5000被占用
```

**2. 无法访问Web界面**
```bash
# 检查端口映射
docker port db-monitor

# 检查防火墙
firewall-cmd --list-ports
firewall-cmd --add-port=5000/tcp --permanent
firewall-cmd --reload
```

**3. 数据库连接失败**
```bash
# 进入容器测试连接
docker exec -it db-monitor bash
python -c "
import pymysql
conn = pymysql.connect(host='your-host', user='user', password='pwd')
print('MySQL连接成功')
"
```

## 🔄 升级更新

### 更新镜像
```bash
# 拉取最新镜像
docker pull harbor.uzhicai.com/midtool/db-monitor:latest

# 停止旧容器
docker stop db-monitor
docker rm db-monitor

# 启动新容器（使用相同的run命令）
# 或使用docker-compose
docker-compose down
docker-compose pull
docker-compose up -d
```

### 回滚版本
```bash
# 切换到指定版本
docker pull harbor.uzhicai.com/midtool/db-monitor:v1.3.0

# 修改docker-compose.yml中的镜像标签
# image: harbor.uzhicai.com/midtool/db-monitor:v1.3.0

docker-compose up -d
```

## 📈 性能优化

### 资源限制
```yaml
# docker-compose.yml
services:
  db-monitor:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### 日志轮转
```bash
# 配置Docker日志驱动
docker run -d \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  ...
```

## 🔐 安全建议

1. **不要在镜像中包含config.json**
   - config.json包含数据库密码
   - 始终通过volume挂载

2. **使用只读挂载配置文件**
   ```bash
   -v /path/to/config.json:/app/config.json:ro
   ```

3. **定期更新镜像**
   ```bash
   # 每月更新一次基础镜像
   docker pull python:3.11-slim
   ./build.sh
   ```

4. **使用非root用户（可选）**
   在Dockerfile中添加：
   ```dockerfile
   RUN useradd -m -u 1000 appuser
   USER appuser
   ```

## 📞 获取帮助

- **GitHub Issues**: https://github.com/qw4285632q/db-monitor/issues
- **文档**: [README.md](README.md)
- **部署指南**: [DEPLOYMENT.md](DEPLOYMENT.md)

---

**版本**: v1.4.0
**更新时间**: 2026-01-29
**镜像仓库**: harbor.uzhicai.com/midtool/db-monitor
