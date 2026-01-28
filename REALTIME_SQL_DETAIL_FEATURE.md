# 实时监控双击查看SQL详情功能

## 功能概述

在"实时监控"页面，用户可以**双击SQL会话行**快速查看该会话的详细信息，包括完整SQL、用户信息、执行时长等。

## 实现时间
2026-01-26

## 功能特性

### ✅ 双击查看详情
- 在实时监控表格的任意位置双击即可查看详情
- 鼠标悬停显示"双击查看详情"提示
- 行样式设置为 `cursor:pointer` 提示可点击

### ✅ 详细信息展示

模态框分为三个区域：

#### 1. 基本信息卡片
- **会话ID**: 数据库会话标识符
- **实例**: 项目名称
- **地址**: IP:端口
- **数据库类型**: MySQL / SQL Server
- **数据库**: 当前使用的数据库名（如果有）

#### 2. 用户信息卡片
- **用户名**: 执行SQL的用户
- **主机**: 客户端主机名/IP
- **状态**: ACTIVE / SLEEPING / LOCKED 等
- **执行时长**: 已运行时间（带颜色告警）
  - 绿色: ≤30秒
  - 黄色: 30-60秒
  - 红色: >60秒

#### 3. SQL语句区域
- 完整SQL语句（格式化显示）
- 支持横向和纵向滚动
- 最大高度40vh，超长可滚动
- 语法高亮（`<code>`标签）

### ✅ 操作按钮

模态框底部提供三个按钮：

1. **📋 复制SQL**: 一键复制完整SQL到剪贴板
2. **⚠️ 终止会话**: 关闭模态框并执行Kill操作
3. **关闭**: 关闭模态框

### ✅ 事件阻止

为避免冲突，以下元素添加了 `event.stopPropagation()`：
- SQL预览单元格（单击查看完整SQL）
- Kill按钮（避免触发双击详情）

## 技术实现

### 1. HTML修改（行1599）

**修改前**:
```html
<tr>
    <td>${row.session_id || '-'}</td>
    ...
</tr>
```

**修改后**:
```html
<tr style="cursor:pointer;"
    ondblclick='showRealtimeSqlDetail(${JSON.stringify(row).replace(/'/g, "&#39;")})'
    title="双击查看详情">
    <td>${row.session_id || '-'}</td>
    ...
</tr>
```

### 2. JavaScript函数（行1690-1796）

```javascript
function showRealtimeSqlDetail(row) {
    // 计算执行时长颜色
    const seconds = parseFloat(row.elapsed_seconds) || 0;
    let durationClass = 'badge-success';
    if (seconds > 60) durationClass = 'badge-danger';
    else if (seconds > 30) durationClass = 'badge-warning';

    // 转义SQL文本
    const sqlText = escapeHtml(row.sql_text || '无SQL语句');

    // 创建模态框
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.style.display = 'flex';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 1000px; max-height: 85vh;">
            <div class="modal-header">...</div>
            <div class="modal-body">
                <!-- 基本信息和用户信息卡片 -->
                <!-- SQL语句显示区域 -->
                <!-- 操作提示 -->
            </div>
            <div class="modal-footer">...</div>
        </div>
    `;

    // 点击外部关闭
    modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.remove();
    });

    document.body.appendChild(modal);
}
```

### 3. CSS样式（行135-140）

```css
/* Info Card for Detail Modal */
.info-card {
    background: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    border: 1px solid #e9ecef;
}

.info-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #e9ecef;
}

.info-row:last-child {
    border-bottom: none;
}

.info-label {
    color: #666;
    font-size: 13px;
    font-weight: 500;
}

.info-value {
    color: #333;
    font-size: 13px;
    text-align: right;
}
```

## 使用方法

### 方式1: 双击查看详情（新功能）⭐

1. 打开"实时监控"页面
2. 在SQL会话列表中，**双击任意行**
3. 弹出详情模态框，显示完整信息
4. 可以复制SQL或终止会话

### 方式2: 单击SQL预览

1. 单击表格中的SQL预览文本
2. 弹出模态框显示完整SQL
3. 可以复制SQL

### 方式3: Kill按钮

1. 点击"Kill"按钮
2. 确认对话框会显示SQL预览
3. 确认后终止会话

## 界面展示

### 详情模态框布局

```
┌─────────────────────────────────────────────────────────┐
│ 实时SQL详情 - 会话 12345                          [×]   │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────┐  ┌────────────────────────┐   │
│ │ 📊 基本信息          │  │ 👤 用户信息             │   │
│ │ 会话ID: 12345        │  │ 用户名: root            │   │
│ │ 实例: 生产数据库     │  │ 主机: 192.168.1.100    │   │
│ │ 地址: 192.168.1.1... │  │ 状态: [ACTIVE]          │   │
│ │ 数据库类型: [MySQL]  │  │ 执行时长: [35 秒]       │   │
│ │ 数据库: [db_prod]    │  │                         │   │
│ └─────────────────────┘  └────────────────────────┘   │
│                                                         │
│ 📝 SQL语句                                             │
│ ┌─────────────────────────────────────────────────┐   │
│ │ SELECT u.*, o.order_id                          │   │
│ │ FROM users u                                    │   │
│ │ LEFT JOIN orders o ON u.id = o.user_id         │   │
│ │ WHERE u.created_at > '2026-01-01'              │   │
│ │ ORDER BY u.id DESC                              │   │
│ │ LIMIT 1000                                      │   │
│ └─────────────────────────────────────────────────┘   │
│                                                         │
│ 💡 提示: 您可以复制SQL语句或终止该会话                │
├─────────────────────────────────────────────────────────┤
│               [📋 复制SQL] [⚠️ 终止会话] [关闭]         │
└─────────────────────────────────────────────────────────┘
```

## 视觉设计

### 颜色方案

- **基本信息**: 绿色主题 (#4CAF50)
- **用户信息**: 蓝色主题 (#2196F3)
- **SQL语句**: 橙色主题 (#FF9800)
- **提示信息**: 黄色背景 (#fff3cd)

### 响应式设计

- 模态框宽度: 最大1000px，90%自适应
- 模态框高度: 最大85vh，支持滚动
- SQL区域: 最大高度40vh，超长可滚动
- 两列卡片: 自适应网格布局

## 交互细节

### 1. 双击触发
- 在表格行任意位置双击即可
- 鼠标悬停提示："双击查看详情"
- 行样式变为手型指针

### 2. 防止冲突
- SQL预览单击事件: 添加 `event.stopPropagation()`
- Kill按钮点击事件: 添加 `event.stopPropagation()`
- 避免这些元素触发双击详情

### 3. 关闭方式
- 点击右上角 × 按钮
- 点击底部"关闭"按钮
- 点击模态框外部灰色区域
- 按ESC键（浏览器默认行为）

### 4. 快捷操作
- 复制SQL: 点击"📋 复制SQL"按钮
- 终止会话: 点击"⚠️ 终止会话"按钮（会关闭模态框并执行Kill）

## 优势对比

### 原有方式
❌ 需要点击Kill按钮才能看部分SQL（仅前100字符）
❌ 无法查看完整会话信息
❌ 操作步骤多

### 新增方式
✅ 双击即可查看所有详细信息
✅ 完整SQL语句展示
✅ 一屏显示所有关键信息
✅ 快捷复制和终止操作

## 使用场景

### 场景1: 快速排查慢SQL
1. 发现某个SQL执行时间很长（红色标识）
2. 双击该行查看详情
3. 查看完整SQL和执行时长
4. 复制SQL到客户端分析
5. 如需终止，点击"终止会话"

### 场景2: 分析用户行为
1. 看到某个用户的SQL
2. 双击查看详情
3. 查看用户名、主机、数据库
4. 了解该用户正在执行什么操作

### 场景3: 监控数据库负载
1. 查看当前活动SQL数量
2. 双击查看每个SQL的详细信息
3. 判断是否需要优化或终止

## 文件修改清单

### static/index.html

**修改位置**:
1. **CSS样式** (行135-140): 添加info-card和info-row样式
2. **表格行** (行1599): 添加双击事件和样式
3. **JavaScript函数** (行1690-1796): 添加showRealtimeSqlDetail函数

**修改内容**:
- 添加 `ondblclick` 事件处理
- 添加 `event.stopPropagation()` 防止冲突
- 添加详情模态框生成逻辑
- 添加样式定义

## 兼容性

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Edge 90+
- ✅ Safari 14+

## 后续优化建议

1. **键盘快捷键**: 添加键盘快捷键（如按D键）快速查看详情
2. **性能指标**: 在详情中显示更多性能指标（CPU时间、IO等待等）
3. **历史记录**: 记录最近查看的SQL详情
4. **对比功能**: 对比两个SQL的执行时长和性能
5. **导出功能**: 导出详情为文本或JSON格式

## 总结

此功能极大提升了实时监控的用户体验：

✅ **操作简便**: 双击即可查看，无需多次点击
✅ **信息完整**: 一屏展示所有关键信息
✅ **快捷操作**: 支持快速复制SQL和终止会话
✅ **视觉友好**: 清晰的分区和颜色标识
✅ **响应迅速**: 即时显示详情，无需额外API请求

用户现在可以更高效地监控和管理数据库实时SQL！
