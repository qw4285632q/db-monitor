# 问题修复总结

## 修复日期
2026-01-26

## 修复的问题

### 1. ✅ 慢SQL不显示问题

**问题原因：**
- 采集器阈值设置为60秒（太高）
- 数据库表缺少4个必需字段导致INSERT失败
- 命令行参数默认值覆盖了代码配置

**解决方案：**
- 降低慢SQL阈值从60秒到5秒
- 添加缺失的数据库字段：
  - `isolation_level` - 事务隔离级别
  - `rows_sent` - 返回行数
  - `index_used` - 使用的索引
  - `full_table_scan` - 是否全表扫描
- 修复采集器的日志编码问题
- 修改命令行参数默认值

**文件修改：**
- `scripts/collector_enhanced.py`
  - 第87行：阈值改为5秒
  - 第811行：命令行参数默认值改为5秒
  - 第41-53行：修复日志编码

### 2. ✅ 实时监控UI混乱问题

**问题原因：**
- 默认阈值设置为0秒，显示所有查询（包括瞬时查询）导致页面刷新频繁

**解决方案：**
- 将实时监控默认阈值从0秒改为5秒
- 更新提示文字："建议≥5秒，0=所有查询"

**文件修改：**
- `static/index.html` 第265行

### 3. ✅ 实时SQL缺少数据库名称

**问题原因：**
- 前端未显示database_name字段

**解决方案：**
- 在"用户"列下方显示数据库名称（带图标📁）
- 使用绿色字体区分

**文件修改：**
- `static/index.html` 第1524-1528行

## 使用指南

### 启动采集器

**方式1：命令行**
```bash
# 使用默认配置（阈值5秒，间隔10秒）
python scripts/collector_enhanced.py

# 守护进程模式（持续采集）
python scripts/collector_enhanced.py --daemon

# 自定义阈值（10秒）
python scripts/collector_enhanced.py --threshold 10

# 自定义采集间隔（5秒）
python scripts/collector_enhanced.py --interval 5
```

**方式2：双击批处理文件**
```
双击运行: start_collector.bat
```

### 查看慢SQL

1. 启动Web服务：`python app_new.py`
2. 打开浏览器：http://localhost:5000
3. 点击【慢SQL监控】标签
4. 选择时间范围（默认24小时）
5. 可按实例、最小执行时间筛选

### 查看实时监控

1. 点击【实时监控】标签
2. 默认显示执行时间≥5秒的SQL
3. 可以调整阈值（建议≥5秒，避免页面混乱）
4. 点击【自动刷新】按钮启用5秒自动刷新
5. 点击【Kill】按钮终止SQL会话

## 测试验证

### 测试采集功能
```bash
python test_slow_sql_collection.py
```

### 测试自动化
```bash
python auto_test_all.py
```
预期结果：52/52 测试通过

## 配置说明

### 采集器配置
- 慢SQL阈值：5秒（可通过--threshold参数修改）
- 采集间隔：10秒（可通过--interval参数修改）
- 告警阈值：1分钟（可通过--alert-threshold参数修改）

### Web界面配置
- 实时监控默认阈值：5秒
- 慢SQL默认时间范围：24小时
- 自动刷新间隔：5秒

## 注意事项

1. **采集器必须持续运行** 才能采集到慢SQL
   - 建议使用 `--daemon` 模式或设置为系统服务
   - 可以使用 nssm 在Windows上安装为服务

2. **阈值设置建议**
   - 开发/测试环境：5-10秒
   - 生产环境：10-30秒（根据业务调整）

3. **数据库权限**
   - MySQL需要：SELECT权限（information_schema, performance_schema）
   - 如果要使用Kill功能：需要PROCESS和SUPER权限

4. **性能影响**
   - 采集器对数据库影响极小（只查询系统表）
   - 建议采集间隔≥10秒

## 后续优化建议

1. 解析MySQL慢查询日志文件（slow_query_log）
2. 添加慢SQL趋势分析图表
3. 添加SQL优化建议（基于执行计划）
4. 支持更多数据库类型（PostgreSQL, Oracle）
5. 添加邮件告警功能
