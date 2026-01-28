# 死锁详情点击功能 - 调试指南

## 问题描述
死锁监控页面的"详情"按钮无法点击或点击后无反应

## 已修复的代码

### 修复前（有问题）
```javascript
// 按钮直接传递整个JSON对象
<button onclick='showDeadlockDetail(${JSON.stringify(row).replace(/'/g, "&#39;")})'>详情</button>

// 函数接收对象
function showDeadlockDetail(deadlock) {
    // ...
}
```

**问题：**
- SQL文本包含特殊字符（引号、换行、反斜杠等）
- JSON.stringify序列化后放入HTML属性易出错
- HTML解析失败导致onclick无法执行

### 修复后（当前版本）
```javascript
// 1. 保存数据到全局变量
window.deadlockData = window.deadlockData || {};
window.deadlockData[row.id] = row;

// 2. 按钮只传递ID
<button onclick='showDeadlockDetail(${row.id})'>详情</button>

// 3. 函数通过ID获取数据
function showDeadlockDetail(deadlockId) {
    const deadlock = window.deadlockData[deadlockId];
    if (!deadlock) {
        alert('无法找到死锁详情数据');
        return;
    }
    // 显示详情...
}
```

## 测试方法

### 方法1：浏览器控制台测试（推荐）

1. 打开浏览器访问：http://localhost:5000
2. 按F12打开开发者工具，切换到Console标签
3. 复制并运行以下脚本：

```javascript
// 快速测试脚本
(async function() {
    // 切换到死锁页面
    document.querySelector('a[data-page="deadlock"]').click();

    // 等待数据加载
    await new Promise(r => setTimeout(r, 2000));

    // 检查数据
    console.log("window.deadlockData:", window.deadlockData);

    // 检查按钮
    const buttons = document.querySelectorAll('#deadlockTableBody button');
    console.log(`找到 ${buttons.length} 个详情按钮`);

    if (buttons.length > 0) {
        // 模拟点击第一个按钮
        buttons[0].click();
        console.log("已点击第一个按钮");

        // 检查模态框
        await new Promise(r => setTimeout(r, 500));
        const modal = document.getElementById('sqlModal');
        const isVisible = modal.classList.contains('show');
        console.log("模态框是否显示:", isVisible ? "是" : "否");

        if (isVisible) {
            console.log("✓✓✓ 测试成功！");
        } else {
            console.error("✗✗✗ 测试失败！");
        }
    }
})();
```

### 方法2：使用调试页面

1. 打开独立调试页面：
   ```
   file:///C:/运维工具类/database-monitor/debug_deadlock_click.html
   ```

2. 页面会显示两种实现方式的对比：
   - 场景1：使用ID传递（当前方式，应该能正常工作）
   - 场景2：使用JSON传递（原始方式，可能失败）

3. 分别点击两个场景的"详情"按钮，观察效果

### 方法3：手动测试步骤

1. **启动服务**
   ```bash
   cd C:\运维工具类\database-monitor
   python app_new.py
   ```

2. **访问页面**
   ```
   http://localhost:5000
   ```

3. **操作步骤**
   - 点击导航栏的【死锁监控】标签
   - 等待列表加载（应该看到死锁记录）
   - 点击任意一条记录的【详情】按钮
   - **预期结果**：弹出详情窗口显示死锁信息

4. **如果失败**
   - 按F12打开开发者工具
   - 切换到Console标签
   - 查看是否有JavaScript错误
   - 查看Network标签确认API请求是否成功

### 方法4：Playwright自动化测试

运行自动化测试脚本：

```bash
cd C:\运维工具类\database-monitor
python test_deadlock_ui.py
```

测试脚本会：
- 自动打开浏览器
- 访问死锁监控页面
- 点击详情按钮
- 验证模态框是否显示
- 截图保存结果

## 可能的问题和解决方案

### 问题1：按钮不存在
**症状：** 页面显示"暂无死锁记录"

**原因：** 数据库中没有死锁记录

**解决方案：**
```sql
-- 检查是否有死锁记录
SELECT COUNT(*) FROM deadlock_log;

-- 查看最近的死锁
SELECT * FROM deadlock_log ORDER BY id DESC LIMIT 5;
```

### 问题2：window.deadlockData未定义
**症状：** 点击按钮时提示"无法找到死锁详情数据"

**原因：** loadDeadlocks()函数未正确保存数据

**检查方法：**
```javascript
// 在控制台执行
console.log(window.deadlockData);
```

**解决方案：**
- 刷新页面（Ctrl+F5）
- 检查loadDeadlocks()函数是否执行
- 检查API是否返回数据

### 问题3：点击无反应
**症状：** 点击按钮没有任何反应

**可能原因：**
1. JavaScript错误阻止了执行
2. 事件被其他代码阻止
3. 按钮被CSS遮挡

**检查步骤：**
```javascript
// 1. 检查函数是否存在
console.log(typeof showDeadlockDetail);  // 应该输出 "function"

// 2. 检查按钮的onclick属性
const btn = document.querySelector('#deadlockTableBody button');
console.log(btn.getAttribute('onclick'));  // 应该类似 "showDeadlockDetail(33)"

// 3. 手动调用函数测试
showDeadlockDetail(33);  // 使用实际的ID
```

### 问题4：模态框不显示
**症状：** 函数执行了但模态框没出现

**检查：**
```javascript
// 检查模态框元素
const modal = document.getElementById('sqlModal');
console.log(modal);  // 应该返回元素对象

// 检查class
console.log(modal.className);  // 应该包含 "show"

// 手动显示
modal.classList.add('show');
```

## 代码位置

修改的文件和行号：

| 文件 | 行号 | 修改内容 |
|------|------|----------|
| `static/index.html` | 1619-1636 | 使用全局变量保存数据 |
| `static/index.html` | 1644-1672 | 修改showDeadlockDetail函数 |

## 验证清单

测试前请确认：

- [ ] 服务正在运行（http://localhost:5000 可访问）
- [ ] 数据库中有死锁记录
- [ ] 浏览器已清除缓存（Ctrl+F5）
- [ ] JavaScript没有错误（F12 Console无红色错误）
- [ ] API返回正确数据（/api/deadlocks?hours=168）

## 成功标志

如果一切正常，应该看到：

1. ✓ 死锁监控页面显示死锁列表
2. ✓ 每条记录有"详情"按钮
3. ✓ 点击按钮弹出详情窗口
4. ✓ 窗口显示：
   - 检测时间
   - 项目名称
   - 受害者会话ID和SQL
   - 阻塞者会话ID和SQL
   - 锁模式和等待资源

## 联系支持

如果问题仍然存在，请提供：

1. 浏览器控制台的截图（F12 -> Console）
2. 点击按钮时的完整错误信息
3. `window.deadlockData`的内容
4. API返回的数据样本

## 附录：完整测试脚本

保存为`full_test.js`，在控制台运行：

```javascript
console.log("=== 完整死锁详情测试 ===\n");

// 1. 环境检查
console.log("1. 环境检查");
console.log("- jQuery:", typeof $ !== 'undefined' ? "✓" : "✗");
console.log("- showDeadlockDetail:", typeof showDeadlockDetail !== 'undefined' ? "✓" : "✗");

// 2. 切换页面
console.log("\n2. 切换到死锁页面");
const tab = document.querySelector('a[data-page="deadlock"]');
if (tab) {
    tab.click();
    console.log("✓ 已点击标签");
} else {
    console.error("✗ 未找到标签");
}

// 3. 延迟检查
setTimeout(() => {
    console.log("\n3. 检查数据");
    console.log("- deadlockData:", window.deadlockData ? `✓ (${Object.keys(window.deadlockData).length}条)` : "✗");

    // 4. 检查按钮
    const buttons = document.querySelectorAll('#deadlockTableBody button');
    console.log(`\n4. 找到 ${buttons.length} 个按钮`);

    if (buttons.length > 0) {
        // 5. 测试点击
        console.log("\n5. 测试第一个按钮");
        const btn = buttons[0];
        console.log("- onclick:", btn.getAttribute('onclick'));

        btn.click();

        setTimeout(() => {
            // 6. 检查结果
            console.log("\n6. 检查结果");
            const modal = document.getElementById('sqlModal');
            const visible = modal && modal.classList.contains('show');
            console.log("- 模态框显示:", visible ? "✓ 成功" : "✗ 失败");

            if (visible) {
                console.log("\n✓✓✓ 所有测试通过！死锁详情功能正常");
            } else {
                console.error("\n✗✗✗ 测试失败");
                console.log("调试信息:");
                console.log("- modal.className:", modal.className);
                console.log("- modal.style:", modal.style.cssText);
            }
        }, 500);
    }
}, 2000);
```

---

**最后更新：** 2026-01-26
**版本：** v2.0（使用ID传递方式）
