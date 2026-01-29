# 📢 Database Monitor v1.5.0 更新说明

## 🎉 版本信息
- **版本号**: v1.5.0
- **发布日期**: 2026-01-29
- **重大更新**: Docker化、SQL Server死锁检测、显示单位优化

---

## ✨ 主要更新

### 1. ⏱️ 慢SQL执行时间单位优化

**变更说明**：慢SQL执行时间从"分钟"改为"秒"，更精确直观。

**影响范围**：
- Long SQL列表页面
- SQL详情弹窗
- 告警阈值配置

**示例**：
```
旧版: 2.35 分钟
新版: 141.00 秒
```

**配置调整**：
```json
{
  "app": {
    "warning_threshold": 5,    // 5秒（原5分钟改为5秒）
    "critical_threshold": 10   // 10秒（原10分钟改为10秒）
  }
}
```

⚠️ **重要**：请根据实际需求调整阈值！

---

### 2. 🐳 Docker容器化支持

**新增文件**：
- `Dockerfile` - 多阶段构建，优化镜像大小
- `docker-compose.yml` - 完整编排配置
- `build.sh` - Linux/Mac自动构建脚本
- `build.ps1` - Windows自动构建脚本
- `.dockerignore` - 排除不必要文件
- `DOCKER_DEPLOY.md` - 完整部署文档

**镜像仓库**：
```
harbor.uzhicai.com/midtool/db-monitor:latest
harbor.uzhicai.com/midtool/db-monitor:v1.5.0
```

**快速开始**：

**本地构建并推送到Harbor**：
```bash
# Linux/Mac
chmod +x build.sh
./build.sh v1.5.0

# Windows PowerShell
.\build.ps1 v1.5.0
```

**服务器部署**：
```bash
# 1. 拉取镜像
docker pull harbor.uzhicai.com/midtool/db-monitor:latest

# 2. 准备配置
mkdir -p /data/db-monitor
cp config.json.example /data/db-monitor/config.json
vim /data/db-monitor/config.json  # 编辑数据库连接

# 3. 运行（方式一：docker run）
docker run -d \
  --name db-monitor \
  --restart unless-stopped \
  -p 5000:5000 \
  -v /data/db-monitor/config.json:/app/config.json:ro \
  -v /data/db-monitor/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  harbor.uzhicai.com/midtool/db-monitor:latest

# 4. 运行（方式二：docker-compose，推荐）
cd /data/db-monitor
docker-compose up -d
```

**镜像特性**：
- ✅ 基于Python 3.11-slim
- ✅ 包含Microsoft ODBC Driver 17
- ✅ 多阶段构建（~400-500MB）
- ✅ 内置健康检查（30秒间隔）
- ✅ 时区设置（Asia/Shanghai）
- ✅ 支持热重启

---

### 3. 🚨 SQL Server死锁检测

**新功能**：自动检测并记录SQL Server死锁事件

**技术实现**：
- 基于Extended Events（扩展事件）
- 自动创建`DeadlockMonitor`会话
- 实时捕获`xml_deadlock_report`事件
- 解析死锁XML提取关键信息

**采集信息**：
- ⏰ 死锁发生时间
- 🎯 受害者进程SPID
- 📝 死锁进程列表和SQL文本
- 🔒 资源争用信息（表、索引、数据库）
- 📊 完整死锁图（JSON格式）

**配置示例**：
```json
{
  "collectors": {
    "deadlock": {
      "enabled": true,
      "interval": 300,
      "description": "SQL Server死锁检测器（通过Extended Events）"
    }
  }
}
```

**查看死锁**：
- 前往Web界面 → "性能监控"页面 → "死锁监控"
- API: `GET /api/deadlocks?hours=24&instance_id=5`

**注意事项**：
- 自动在SQL Server上创建Extended Events会话
- 会话名称：`DeadlockMonitor`
- 启动状态：`STARTUP_STATE = ON`
- 内存占用：4MB ring buffer
- 需要权限：`ALTER ANY EVENT SESSION`

---

## 🔧 配置文件更新

### 新增配置项

```json
{
  "collectors": {
    "mysql": {
      "enabled": true,
      "interval": 60,
      "threshold": 2          // ← 改为秒！
    },
    "sqlserver": {
      "enabled": true,
      "interval": 60,
      "threshold": 2,         // ← 改为秒！
      "auto_enable_querystore": false
    },
    "deadlock": {             // ← 新增！
      "enabled": true,
      "interval": 300,        // 5分钟检测一次
      "description": "SQL Server死锁检测器"
    }
  }
}
```

### 配置迁移指南

**从v1.4.x升级到v1.5.0**：

1. **阈值单位变更**（分钟→秒）：
   ```json
   // 旧版（v1.4.x）
   "threshold": 5   // 5秒

   // 新版（v1.5.0）保持不变
   "threshold": 5   // 依然是5秒
   ```

   ⚠️ 如果你之前配置的是"5分钟"，现在会变成"5秒"，请根据需要调整！

2. **新增死锁检测器配置**：
   ```bash
   # 复制示例配置
   cp config.json config.json.backup
   vim config.json

   # 在collectors中添加deadlock配置（见上）
   ```

---

## 📦 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `static/index.html` | 修改 | 慢SQL显示单位改为秒 |
| `app_new.py` | 修改 | 集成死锁检测器 |
| `scripts/sqlserver_deadlock_collector.py` | 新增 | 死锁采集器（400+行） |
| `Dockerfile` | 新增 | Docker镜像定义 |
| `docker-compose.yml` | 新增 | Docker编排文件 |
| `build.sh` | 新增 | Linux/Mac构建脚本 |
| `build.ps1` | 新增 | Windows构建脚本 |
| `.dockerignore` | 新增 | Docker忽略文件 |
| `DOCKER_DEPLOY.md` | 新增 | Docker部署文档 |
| `config.json.example` | 修改 | 新增deadlock配置 |

---

## 🚀 升级步骤

### 方式一：传统部署升级

```bash
# 1. 备份配置
cp config.json config.json.backup

# 2. 拉取最新代码
git pull origin main

# 3. 更新配置文件（添加deadlock配置）
vim config.json

# 4. 停止旧服务
# 查找并kill旧进程
ps aux | grep app_new.py
kill -9 <PID>

# 5. 安装依赖（如有新增）
pip install -r requirements.txt

# 6. 启动新服务
python start.py
# 或
python app_new.py
```

### 方式二：Docker部署升级

```bash
# 1. 拉取最新镜像
docker pull harbor.uzhicai.com/midtool/db-monitor:latest

# 2. 停止旧容器
docker-compose down
# 或
docker stop db-monitor && docker rm db-monitor

# 3. 更新配置文件（添加deadlock配置）
vim /data/db-monitor/config.json

# 4. 启动新容器
docker-compose up -d
# 或
docker run -d \
  --name db-monitor \
  --restart unless-stopped \
  -p 5000:5000 \
  -v /data/db-monitor/config.json:/app/config.json:ro \
  -v /data/db-monitor/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  harbor.uzhicai.com/midtool/db-monitor:latest

# 5. 查看日志
docker-compose logs -f
```

---

## ✅ 验证测试

### 1. 验证基本功能

```bash
# 检查服务状态
curl http://localhost:5000/

# 查看慢SQL（确认单位是"秒"）
打开浏览器: http://localhost:5000
点击 "Long SQL列表"
确认显示: "141.00 秒"（不是"分钟"）
```

### 2. 验证死锁检测

```sql
-- 在SQL Server上手动触发死锁测试
-- 会话1:
BEGIN TRAN
UPDATE Table1 SET Col1 = 1 WHERE ID = 1
WAITFOR DELAY '00:00:10'
UPDATE Table2 SET Col1 = 1 WHERE ID = 1
COMMIT

-- 会话2（同时执行）:
BEGIN TRAN
UPDATE Table2 SET Col1 = 2 WHERE ID = 1
UPDATE Table1 SET Col1 = 2 WHERE ID = 1
COMMIT
```

等待5-10分钟后，查看Web界面"死锁监控"是否出现记录。

### 3. 验证Docker部署

```bash
# 检查容器健康状态
docker ps
# HEALTH列应显示: healthy

# 查看容器日志
docker logs db-monitor

# 进入容器调试
docker exec -it db-monitor bash
python -c "import pyodbc; print('ODBC OK')"
```

---

## 🐛 已知问题

### SQL Server性能指标404错误

**症状**：切换到"SQL Server"性能指标时显示"加载失败: Not Found"

**原因**：应用未重启，新增API未加载

**解决**：
```bash
# 重启应用
python app_new.py

# 或Docker
docker-compose restart
```

### 死锁检测权限不足

**症状**：日志显示"创建/启动死锁监控会话失败: permission denied"

**原因**：监控账号缺少权限

**解决**：
```sql
-- 授予Extended Events权限
ALTER SERVER ROLE sysadmin ADD MEMBER [monitor_user]
-- 或最小权限
GRANT ALTER ANY EVENT SESSION TO [monitor_user]
GRANT VIEW SERVER STATE TO [monitor_user]
```

---

## 📞 获取帮助

- **GitHub Issues**: https://github.com/qw4285632q/db-monitor/issues
- **文档中心**: [docs/README.md](docs/README.md)
- **Docker部署**: [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md)
- **快速开始**: [QUICK_START.md](QUICK_START.md)

---

## 🔗 相关链接

- **GitHub仓库**: https://github.com/qw4285632q/db-monitor
- **Harbor镜像**: harbor.uzhicai.com/midtool/db-monitor
- **提交历史**: https://github.com/qw4285632q/db-monitor/commits/main

---

**感谢使用 Database Monitor！** 🎉

如有问题或建议，欢迎提Issue或PR！
