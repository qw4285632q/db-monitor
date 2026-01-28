# Long SQL 列表无数据问题修复

## 问题描述

Long SQL 列表页面显示"暂无记录"，但数据库中实际有数据。

## 问题原因

**根本原因**：默认的最小运行时间过滤条件设置为 **1.0 分钟**，导致运行时间较短的SQL被过滤掉。

### 数据库实际情况

```
总记录数: 3条
记录运行时间范围: 0.13-0.15分钟（约8-9秒）
```

### 原始过滤条件

```javascript
// 前端默认值
<input type="number" id="filterMinMinutes" value="1" min="0" step="0.5">

// 后端默认值
min_minutes = request.args.get('min_minutes', 1.0, type=float)
```

### 查询逻辑

```sql
WHERE l.detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
  AND l.elapsed_minutes >= 1.0  -- 这里过滤掉了所有 < 1分钟的记录
```

**结果**：3条记录都小于1分钟，全部被过滤，显示"暂无记录"

## 解决方案

### 修改1: 前端默认值改为0

**文件**: `static/index.html` 行210

**修改前**:
```html
<input type="number" id="filterMinMinutes" value="1" min="0" step="0.5">
```

**修改后**:
```html
<input type="number" id="filterMinMinutes" value="0" min="0" step="0.1">
```

**改进点**:
- 默认值从 `1` 改为 `0`（显示所有记录）
- 步进值从 `0.5` 改为 `0.1`（更精细的控制）

### 修改2: 后端默认值同步为0

**文件**: `app_new.py` 行781

**修改前**:
```python
min_minutes = request.args.get('min_minutes', 1.0, type=float)
```

**修改后**:
```python
min_minutes = request.args.get('min_minutes', 0.0, type=float)
```

## 验证结果

修改后，使用默认条件（min_minutes=0）查询：

```
查询条件: 最近24小时, 运行时间>=0.0分钟
查询结果: 3 条记录

Long SQL 列表:
1. ID=1 | 项目=预生产主库 | 运行时长=0.15分钟
2. ID=2 | 项目=预生产主库 | 运行时长=0.15分钟
3. ID=3 | 项目=预生产主库 | 运行时长=0.13分钟
```

✅ **问题已修复，现在可以正常显示所有记录！**

## 使用说明

修复后的行为：

1. **默认显示所有记录**（min_minutes=0）
   - 用户打开页面即可看到所有Long SQL记录
   - 不会因为过滤条件太严格而看不到数据

2. **用户可自定义过滤**
   - 如果只想看运行时间较长的SQL，可以手动调整"最小执行时间"
   - 例如：设置为 5 分钟，只显示运行超过5分钟的SQL

3. **更灵活的步进值**
   - 步进值改为 0.1，可以精确到 0.1 分钟（6秒）
   - 适合精细化的性能分析

## 相关文件

- `app_new.py` - 后端API逻辑
- `static/index.html` - 前端过滤控件
- `long_running_sql_log` - 数据库表

## 测试建议

1. **清空浏览器缓存**（Ctrl+F5）
2. **访问监控面板**
3. **查看Long SQL列表**
4. **验证可以看到所有记录**
5. **尝试调整"最小执行时间"过滤**

---

**修复日期**: 2026-01-26
**修复版本**: v2.1
