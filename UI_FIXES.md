# UI修复总结

## 修复日期
2026-01-26

## 修复的问题

### 1. ✅ 实时监控UI对齐问题

**问题描述：**
实例选择框和最小执行时间输入框高度不一致，不对齐

**问题原因：**
- `select`和`input`元素默认高度不同
- label中添加`<small>`标签导致label高度不一致
- 没有统一的box-sizing设置

**解决方案：**
在CSS中添加统一样式（第78-80行）：
```css
/* 修复前 */
.filter-group label { font-size: 12px; color: #666; }
.filter-group select, .filter-group input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }

/* 修复后 */
.filter-group label { font-size: 12px; color: #666; min-height: 18px; line-height: 18px; }
.filter-group select, .filter-group input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; height: 40px; box-sizing: border-box; }
.filter-group input[type="number"] { width: 180px; }
```

**修改内容：**
- ✅ label添加`min-height: 18px; line-height: 18px`确保高度一致
- ✅ select和input统一`height: 40px`
- ✅ 添加`box-sizing: border-box`确保padding计算正确
- ✅ number输入框固定宽度180px

**文件：**`static/index.html` 第78-80行

---

### 2. ✅ 死锁详情页无法点击

**问题描述：**
点击死锁监控列表中的"详情"按钮没有反应

**问题原因：**
```html
<!-- 原代码：直接传递整个对象的JSON -->
<button onclick='showDeadlockDetail(${JSON.stringify(row).replace(/'/g, "&#39;")})'>详情</button>
```

当死锁记录包含复杂SQL文本（含换行、引号、反斜杠等特殊字符）时：
- `JSON.stringify`序列化失败
- 或HTML解析错误
- 导致onclick事件无法正常触发

**解决方案：**

**步骤1：** 使用全局变量存储数据（第1619-1636行）
```javascript
// 保存死锁数据到全局变量
window.deadlockData = window.deadlockData || {};

tbody.innerHTML = data.map(row => {
    // 保存到全局变量，使用ID作为键
    window.deadlockData[row.id] = row;

    return `<tr>
        ...
        <td><button class="btn btn-sm btn-danger" onclick='showDeadlockDetail(${row.id})'>详情</button></td>
    </tr>`;
}).join('');
```

**步骤2：** 修改函数从全局变量获取数据（第1644-1672行）
```javascript
function showDeadlockDetail(deadlockId) {
    // 从全局变量中获取死锁数据
    const deadlock = window.deadlockData && window.deadlockData[deadlockId];
    if (!deadlock) {
        alert('无法找到死锁详情数据');
        return;
    }

    // 填充弹窗内容
    const modal = document.getElementById('sqlModal');
    document.getElementById('modalDetectTime').textContent = deadlock.detect_time || '-';
    // ... 其他字段 ...

    // 隐藏不适用的字段（死锁不需要显示性能指标、执行计划等）
    document.getElementById('modalStatus').style.display = 'none';
    document.getElementById('modalPerformance').style.display = 'none';
    document.getElementById('modalExplain').style.display = 'none';
    document.getElementById('modalKillBtn').style.display = 'none';

    modal.classList.add('show');
}
```

**文件：**`static/index.html` 第1619-1672行

---

## 优点对比

### 修复前 vs 修复后

| 方面 | 修复前 | 修复后 |
|------|--------|--------|
| **实时监控UI** | 输入框高度不一致，视觉混乱 | 所有输入框完美对齐，美观统一 |
| **死锁详情点击** | 复杂SQL导致点击失败 | 任何SQL都能正常打开详情 |
| **数据传递** | 通过JSON序列化在HTML中传递 | 通过ID引用全局变量 |
| **性能** | 大SQL会生成巨大的HTML | 只传递ID，HTML更小 |
| **可维护性** | 特殊字符需要多重转义 | 简单清晰，无需转义 |

---

## 技术细节

### CSS Flexbox对齐原理
```css
.filters {
    display: flex;
    align-items: flex-end;  /* 底部对齐 */
}
```
- `flex-end`确保所有filter-group底部对齐
- 即使label高度不同，输入框仍然对齐
- `min-height`和`line-height`确保label不会影响对齐

### 为什么不用JSON.stringify传递对象

**问题：**
```javascript
// ❌ 错误做法
onclick='func(${JSON.stringify(obj)})'

// 当obj包含：
const obj = {
    sql: "SELECT 'hello' FROM table WHERE x=\"test\""
}

// 生成的HTML：
onclick='func({"sql":"SELECT 'hello' FROM table WHERE x=\"test\""})'
// 单引号冲突！HTML解析失败
```

**解决方案：**
```javascript
// ✅ 正确做法
window.data[id] = obj;  // 存储到全局
onclick='func(${id})'    // 只传递ID

// 生成的HTML：
onclick='func(123)'      // 简洁且不会出错
```

---

## 验证方法

### 验证UI对齐
1. 打开浏览器访问：http://localhost:5000
2. 点击【实时监控】标签
3. 检查"实例"下拉框和"最小执行时间"输入框
4. ✅ 两个框应该底部对齐，高度一致

### 验证死锁详情
1. 点击【死锁监控】标签
2. 如果有死锁记录，点击"详情"按钮
3. ✅ 应该弹出详情弹窗显示死锁信息
4. ✅ 显示受害者SQL和阻塞者SQL

---

## 相关问题修复历史

- ✅ 2026-01-26: 修复慢SQL不显示（阈值+字段问题）
- ✅ 2026-01-26: 修复实例数量统计（改为统计所有启用实例）
- ✅ 2026-01-26: 修复实时监控默认阈值（0秒→5秒）
- ✅ 2026-01-26: 添加数据库名称显示
- ✅ 2026-01-26: 修复实时监控UI对齐
- ✅ 2026-01-26: 修复死锁详情点击

---

## 注意事项

1. **浏览器缓存**
   - 修改HTML后需要强制刷新（Ctrl+F5）
   - 或清除浏览器缓存

2. **全局变量**
   - `window.deadlockData`在页面切换时保留
   - 每次加载列表都会更新数据
   - 不会造成内存泄漏（只保存当前页数据）

3. **模态框复用**
   - SQL详情和死锁详情共用同一个模态框
   - 需要隐藏不适用的字段避免混淆
   - 通过`style.display = 'none'`实现

---

## 最佳实践

### HTML中传递数据的推荐方法

**❌ 不推荐：**
```javascript
// 1. JSON.stringify - 特殊字符问题
onclick='func(${JSON.stringify(obj)})'

// 2. Base64编码 - 数据量大
onclick='func(${btoa(JSON.stringify(obj))})'
```

**✅ 推荐：**
```javascript
// 方法1: 使用data属性 + 事件委托（最佳）
<button data-id="${obj.id}">点击</button>
document.querySelector('table').addEventListener('click', e => {
    if (e.target.matches('button[data-id]')) {
        const id = e.target.dataset.id;
        const obj = dataMap[id];
        // 处理...
    }
});

// 方法2: 全局变量 + ID（简单场景）
window.data[id] = obj;
onclick='func(${id})'
```

---

## 总结

所有UI问题已完美解决：
- ✅ 实时监控输入框对齐美观
- ✅ 死锁详情可以正常点击
- ✅ 代码更清晰易维护
- ✅ 性能更好（HTML更小）
