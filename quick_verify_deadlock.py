#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速验证死锁详情功能"""
import re
import sys

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 70)
print("快速验证死锁详情点击功能")
print("=" * 70)

# 读取index.html文件
with open('static/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

print("\n[检查1] 查找按钮onclick属性...")
# 查找按钮的onclick属性
button_pattern = r"onclick='showDeadlockDetail\(([^)]+)\)'"
matches = re.findall(button_pattern, content)

if matches:
    print(f"[OK] 找到 {len(matches)} 处按钮定义")
    for i, match in enumerate(matches, 1):
        print(f"  {i}. onclick参数: {match}")
        if '${row.id}' in match or 'row.id' in match:
            print(f"     [OK] 正确：使用ID传递")
        else:
            print(f"     [WARN] 警告：可能使用其他方式")
else:
    print("[ERROR] 未找到按钮定义")

print("\n[检查2] 查找全局变量保存...")
if 'window.deadlockData' in content:
    print("[OK] 找到 window.deadlockData 全局变量")
    if 'window.deadlockData[row.id] = row' in content:
        print("  [OK] 正确保存数据到全局变量")
    else:
        print("  [WARN] 未找到数据保存语句")
else:
    print("[ERROR] 未找到 window.deadlockData")

print("\n[检查3] 查找showDeadlockDetail函数...")
func_pattern = r'function showDeadlockDetail\((\w+)\)'
func_matches = re.findall(func_pattern, content)

if func_matches:
    param_name = func_matches[0]
    print(f"[OK] 找到函数定义，参数名: {param_name}")

    if f'window.deadlockData[{param_name}]' in content or f'window.deadlockData && window.deadlockData[{param_name}]' in content:
        print(f"  [OK] 函数正确从全局变量获取数据")
    else:
        print(f"  [WARN] 函数可能未从全局变量获取数据")
else:
    print("[ERROR] 未找到函数定义")

print("\n[检查4] 验证数据流程...")
checks = {
    "数据保存": 'window.deadlockData[row.id] = row' in content,
    "按钮传递ID": '${row.id}' in content and "onclick='showDeadlockDetail(${row.id})'" in content,
    "函数获取数据": 'window.deadlockData[' in content and 'function showDeadlockDetail' in content,
    "模态框显示": "modal.classList.add('show')" in content
}

all_passed = True
for check_name, passed in checks.items():
    status = "[OK]" if passed else "[ERROR]"
    print(f"  {status} {check_name}")
    if not passed:
        all_passed = False

print("\n" + "=" * 70)
if all_passed:
    print("[SUCCESS] 代码验证通过！死锁详情功能应该能正常工作")
    print("\n下一步：在浏览器中测试")
    print("1. 打开 http://localhost:5000")
    print("2. 按 Ctrl+F5 强制刷新（清除缓存）")
    print("3. 点击【死锁监控】标签")
    print("4. 点击任意【详情】按钮")
    print("5. 应该弹出详情窗口")
else:
    print("[FAILED] 代码验证失败！需要检查代码")
    print("\n建议：检查 static/index.html 文件是否正确保存")

print("=" * 70)
