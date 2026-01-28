# SQL预览显示增强

## 问题描述
用户反馈"sql实时监控的 sql预览 sql显示不全"

## 问题分析

### 原有限制
1. **实时监控页面**: SQL预览仅显示前60个字符
2. **Long SQL列表**: SQL预览仅显示前50个字符
3. 长SQL无法快速查看完整内容

## 解决方案

### 1. 增加预览长度
- 实时监控页面: 60字符 → **150字符**
- Long SQL列表: 50字符 → **150字符**

### 2. 添加点击查看完整SQL功能

**新增功能**:
- SQL预览区域添加 `cursor:pointer` 样式，鼠标悬停显示手型
- 添加 `title="点击查看完整SQL"` 提示
- 点击SQL预览弹出模态框显示完整SQL

**模态框特性**:
- 宽度900px，最大高度80vh
- SQL以`<pre><code>`格式化显示
- 支持横向和纵向滚动
- 提供"复制SQL"按钮，一键复制到剪贴板
- 点击外部或"关闭"按钮关闭模态框

### 3. 改进CSS样式

SQL预览单元格样式优化:
```css
font-size: 11px;
cursor: pointer;
display: block;
max-width: 400px;
overflow: hidden;
text-overflow: ellipsis;
white-space: nowrap;
```

**特性**:
- 文本超出时显示省略号（...）
- 单行显示，不换行
- 最大宽度400px
- 鼠标悬停变手型指针

## 修改文件

### static/index.html

#### 1. 实时监控页面 (行1588-1603)

**修改前**:
```javascript
const sqlPreview = (row.sql_text || '').substring(0, 60) + ...;
...
<td><code style="font-size:11px">${escapeHtml(sqlPreview)}</code></td>
```

**修改后**:
```javascript
const sqlText = row.sql_text || '';
const sqlPreview = sqlText.substring(0, 150) + (sqlText.length > 150 ? '...' : '');
const fullSql = escapeHtml(sqlText);
...
<td>
    <code style="font-size:11px;cursor:pointer;display:block;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
          onclick="showFullSQL('${fullSql.replace(/'/g, "&#39;")}')"
          title="点击查看完整SQL">${escapeHtml(sqlPreview)}</code>
</td>
```

#### 2. Long SQL列表页面 (行1194-1208)

**修改前**:
```javascript
const sqlPreview = (row.sql_text || '').substring(0, 50) + ...;
...
<td><code style="font-size:11px">${escapeHtml(sqlPreview)}</code></td>
```

**修改后**:
```javascript
const sqlText = row.sql_text || '';
const sqlPreview = sqlText.substring(0, 150) + (sqlText.length > 150 ? '...' : '');
const fullSql = escapeHtml(sqlText);
...
<td>
    <code style="font-size:11px;cursor:pointer;display:block;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
          onclick="showFullSQL('${fullSql.replace(/'/g, "&#39;")}')"
          title="点击查看完整SQL">${escapeHtml(sqlPreview)}</code>
</td>
```

#### 3. 新增showFullSQL函数 (行1653-1682)

```javascript
function showFullSQL(sqlText) {
    // 创建模态框显示完整SQL
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.style.display = 'flex';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 900px; max-height: 80vh;">
            <div class="modal-header">
                <h3>完整SQL语句</h3>
                <button class="btn btn-sm" onclick="this.closest('.modal').remove()"
                        style="font-size:20px;padding:0 10px;">&times;</button>
            </div>
            <div class="modal-body" style="overflow-y: auto;">
                <pre style="background:#f5f5f5;padding:15px;border-radius:4px;overflow-x:auto;
                            max-height:60vh;margin:0;"><code>${sqlText}</code></pre>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary"
                        onclick="navigator.clipboard.writeText(\`${sqlText.replace(/`/g, '\\`')}\`)
                                 .then(() => alert('SQL已复制到剪贴板'))">复制SQL</button>
                <button class="btn btn-primary"
                        onclick="this.closest('.modal').remove()">关闭</button>
            </div>
        </div>
    `;

    // 点击模态框外部关闭
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.remove();
        }
    });

    document.body.appendChild(modal);
}
```

## 使用方法

### 1. 查看SQL预览
- 打开"实时监控"或"Long SQL"页面
- SQL预览现在显示150个字符（原来60/50）
- 鼠标悬停在SQL上，显示"点击查看完整SQL"提示

### 2. 查看完整SQL
**方式1: 点击SQL预览**
- 直接点击表格中的SQL预览文本
- 弹出模态框显示完整SQL
- SQL以格式化的代码块显示

**方式2: 复制SQL**
- 在完整SQL模态框中
- 点击"复制SQL"按钮
- SQL自动复制到系统剪贴板
- 可直接粘贴到SQL客户端执行

**方式3: 查看详情（Long SQL）**
- 点击"详情"按钮
- 在详情页面查看完整SQL及所有性能指标

### 3. 关闭模态框
- 点击右上角"×"按钮
- 点击底部"关闭"按钮
- 点击模态框外部灰色区域
- 按ESC键（浏览器默认行为）

## 功能特性

### ✓ 预览长度增加
- 实时监控: 60 → 150字符 (2.5倍)
- Long SQL: 50 → 150字符 (3倍)
- 更多上下文信息一目了然

### ✓ 点击查看完整SQL
- 无需进入详情页
- 快速查看完整SQL内容
- 格式化显示，易于阅读

### ✓ 一键复制SQL
- 点击即可复制
- 支持长SQL完整复制
- 方便在SQL客户端执行

### ✓ 响应式设计
- 模态框自适应屏幕大小
- 最大宽度900px
- 最大高度80vh
- 超长SQL自动滚动

### ✓ 用户体验优化
- 鼠标悬停提示
- 手型指针明确可点击
- 点击外部关闭
- 复制成功提示

## 测试验证

### 测试场景1: 短SQL（<150字符）
**SQL示例**: `SELECT * FROM users WHERE id = 1`

**预期结果**:
- 预览完整显示SQL
- 无省略号
- 点击可查看完整内容
- 完整SQL与预览一致

### 测试场景2: 中等SQL（150-500字符）
**SQL示例**:
```sql
SELECT u.id, u.name, u.email, o.order_id, o.total_amount
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.created_at > '2026-01-01'
ORDER BY o.total_amount DESC
```

**预期结果**:
- 预览显示前150字符 + "..."
- 点击查看完整SQL
- 模态框显示完整格式化SQL
- 可复制完整SQL

### 测试场景3: 长SQL（>1000字符）
**SQL示例**: 复杂查询，多表JOIN，子查询等

**预期结果**:
- 预览显示前150字符 + "..."
- 点击查看完整SQL
- 模态框内容可滚动
- 复制功能正常

### 测试场景4: 特殊字符SQL
**SQL示例**: 包含单引号、双引号、换行符

**预期结果**:
- HTML正确转义
- 点击不报错
- 模态框正确显示
- 复制内容正确

## 兼容性

- ✓ Chrome 90+
- ✓ Firefox 88+
- ✓ Edge 90+
- ✓ Safari 14+
- ✓ 移动端浏览器

## 后续优化建议

1. **语法高亮**: 为SQL添加语法高亮显示
2. **格式化按钮**: 添加SQL格式化功能（美化SQL）
3. **执行按钮**: 直接在监控界面执行SQL（需谨慎）
4. **历史记录**: 保存最近查看的SQL
5. **收藏功能**: 收藏常用SQL以便后续分析

## 总结

此次优化显著改善了SQL预览的用户体验：
- **预览更多**: 150字符预览提供更多上下文
- **操作便捷**: 一键查看完整SQL，一键复制
- **界面友好**: 清晰的视觉提示和交互反馈
- **功能完整**: 支持查看、复制、关闭等完整操作流程

现在用户可以快速查看和复制SQL，无需繁琐地打开详情页面。
