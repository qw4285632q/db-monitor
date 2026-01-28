#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动化测试所有功能"""
import requests
import json
import sys
import time
import os

# 禁用代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
session = requests.Session()
session.trust_env = False

BASE_URL = "http://localhost:5000"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name, condition, error_msg=""):
        if condition:
            print(f"[OK] {name}")
            self.passed += 1
            return True
        else:
            print(f"[FAIL] {name}: {error_msg}")
            self.failed += 1
            self.errors.append(f"{name}: {error_msg}")
            return False

    def summary(self):
        total = self.passed + self.failed
        print("\n" + "=" * 70)
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.errors:
            print("\n失败的测试:")
            for err in self.errors:
                print(f"  - {err}")
        print("=" * 70)
        return self.failed == 0

result = TestResult()

print("=" * 70)
print("开始自动化测试所有功能")
print("=" * 70)

# 1. 测试Web服务
print("\n[1] 测试Web服务")
try:
    r = session.get(f"{BASE_URL}/", timeout=5)
    result.test("Web服务响应", r.status_code == 200, f"状态码: {r.status_code}")
    result.test("返回HTML内容", "SQL监控系统" in r.text, "页面标题不正确")
except Exception as e:
    result.test("Web服务连接", False, str(e))

# 2. 测试配置API
print("\n[2] 测试配置API")
try:
    r = requests.get(f"{BASE_URL}/api/config", timeout=5)
    result.test("配置API响应", r.status_code == 200)
    data = r.json()
    result.test("配置API返回格式", data.get('success') == True)
    result.test("配置包含database", 'database' in data.get('data', {}))
except Exception as e:
    result.test("配置API", False, str(e))

# 3. 测试实例API
print("\n[3] 测试实例API")
try:
    r = requests.get(f"{BASE_URL}/api/instances", timeout=5)
    result.test("实例API响应", r.status_code == 200)
    data = r.json()
    result.test("实例API返回格式", data.get('success') == True)
    instances = data.get('data', [])
    result.test("实例数据非空", len(instances) > 0, "没有配置实例")
    if instances:
        inst = instances[0]
        result.test("实例包含必要字段", all(k in inst for k in ['id', 'db_ip', 'db_port', 'db_type']))
except Exception as e:
    result.test("实例API", False, str(e))

# 4. 测试慢SQL API
print("\n[4] 测试慢SQL API")
try:
    r = requests.get(f"{BASE_URL}/api/long_sql?hours=24&page=1&page_size=20", timeout=5)
    result.test("慢SQL API响应", r.status_code == 200)
    data = r.json()
    result.test("慢SQL API返回格式", data.get('success') == True)
    result.test("慢SQL包含分页信息", 'pagination' in data)
except Exception as e:
    result.test("慢SQL API", False, str(e))

# 5. 测试死锁API
print("\n[5] 测试死锁API")
try:
    r = requests.get(f"{BASE_URL}/api/deadlocks?hours=24&page=1", timeout=5)
    result.test("死锁API响应", r.status_code == 200)
    data = r.json()
    result.test("死锁API返回格式", data.get('success') == True)
except Exception as e:
    result.test("死锁API", False, str(e))

# 6. 测试实时监控API (新功能)
print("\n[6] 测试实时监控API")
try:
    r = requests.get(f"{BASE_URL}/api/realtime_sql?min_seconds=0", timeout=5)
    result.test("实时监控API响应", r.status_code == 200)
    data = r.json()
    result.test("实时监控API返回格式", data.get('success') == True)
    result.test("实时监控包含stats", 'stats' in data)
    result.test("实时监控包含data", 'data' in data)
except Exception as e:
    result.test("实时监控API", False, str(e))

# 7. 测试SQL详情API (新功能)
print("\n[7] 测试SQL详情API")
try:
    # 先获取一个SQL ID
    r = requests.get(f"{BASE_URL}/api/long_sql?hours=168&page=1&page_size=1", timeout=5)
    if r.status_code == 200:
        data = r.json()
        if data.get('data'):
            sql_id = data['data'][0]['id']
            r2 = requests.get(f"{BASE_URL}/api/long_sql/{sql_id}", timeout=5)
            result.test("SQL详情API响应", r2.status_code == 200)
            detail = r2.json()
            result.test("SQL详情API返回格式", detail.get('success') == True)
            if detail.get('data'):
                sql_data = detail['data']
                result.test("SQL详情包含完整字段", 'sql_fulltext' in sql_data or 'sql_text' in sql_data)
        else:
            result.test("SQL详情API", True, "跳过（无SQL数据）")
    else:
        result.test("SQL详情API", False, "无法获取SQL列表")
except Exception as e:
    result.test("SQL详情API", False, str(e))

# 8. 测试统计API
print("\n[8] 测试统计API")
try:
    r = requests.get(f"{BASE_URL}/api/statistics?hours=24", timeout=5)
    result.test("统计API响应", r.status_code == 200)
    data = r.json()
    result.test("统计API返回格式", data.get('success') == True)
    result.test("统计包含summary", 'summary' in data)
    result.test("统计包含trend", 'trend' in data)
except Exception as e:
    result.test("统计API", False, str(e))

# 9. 测试告警配置API
print("\n[9] 测试告警配置API")
try:
    r = requests.get(f"{BASE_URL}/api/alert-config", timeout=5)
    result.test("告警配置API响应", r.status_code == 200)
    data = r.json()
    result.test("告警配置API返回格式", data.get('success') == True)
except Exception as e:
    result.test("告警配置API", False, str(e))

# 10. 测试健康检查API
print("\n[10] 测试健康检查API")
try:
    r = requests.get(f"{BASE_URL}/api/health", timeout=5)
    result.test("健康检查API响应", r.status_code == 200)
    data = r.json()
    result.test("健康检查返回健康状态", data.get('status') in ['healthy', 'degraded'])
except Exception as e:
    result.test("健康检查API", False, str(e))

# 11. 检查数据库连接
print("\n[11] 检查数据库连接")
try:
    import pymysql
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    conn = pymysql.connect(**config['database'])
    result.test("监控数据库连接", True)

    cursor = conn.cursor()

    # 检查表是否存在
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    result.test("db_instance_info表存在", 'db_instance_info' in tables)
    result.test("long_running_sql_log表存在", 'long_running_sql_log' in tables)
    result.test("deadlock_log表存在", 'deadlock_log' in tables)
    result.test("alert_history表存在", 'alert_history' in tables)

    # 检查字段是否存在
    cursor.execute("DESC long_running_sql_log")
    columns = [row[0] for row in cursor.fetchall()]
    result.test("sql_fingerprint字段存在", 'sql_fingerprint' in columns)
    result.test("sql_fulltext字段存在", 'sql_fulltext' in columns)
    result.test("execution_plan字段存在", 'execution_plan' in columns)
    result.test("cpu_time字段存在", 'cpu_time' in columns)
    result.test("rows_examined字段存在", 'rows_examined' in columns)

    cursor.execute("DESC alert_history")
    alert_columns = [row[0] for row in cursor.fetchall()]
    result.test("alert_type字段存在", 'alert_type' in alert_columns)
    result.test("alert_identifier字段存在", 'alert_identifier' in alert_columns)

    conn.close()
except Exception as e:
    result.test("数据库检查", False, str(e))

# 12. 检查采集器
print("\n[12] 检查采集器文件")
import os
result.test("collector_enhanced.py存在", os.path.exists('scripts/collector_enhanced.py'))
result.test("utils/alert.py存在", os.path.exists('utils/alert.py'))
result.test("static/index.html存在", os.path.exists('static/index.html'))
result.test("app_new.py存在", os.path.exists('app_new.py'))

# 13. 检查关键函数
print("\n[13] 检查关键函数")
try:
    with open('scripts/collector_enhanced.py', 'r', encoding='utf-8') as f:
        collector_code = f.read()

    result.test("get_sql_fingerprint函数存在", 'def get_sql_fingerprint' in collector_code)
    result.test("get_explain函数存在", 'def get_explain' in collector_code)
    result.test("get_performance_metrics函数存在", 'def get_performance_metrics' in collector_code)
    result.test("should_send_alert函数存在", 'def should_send_alert' in collector_code)
    result.test("save_alert_history函数存在", 'def save_alert_history' in collector_code)

    with open('static/index.html', 'r', encoding='utf-8') as f:
        html_code = f.read()

    result.test("实时监控页面存在", 'page-realtime' in html_code)
    result.test("loadRealtimeSQL函数存在", 'function loadRealtimeSQL' in html_code)
    result.test("killSession函数存在", 'function killSession' in html_code or 'async function killSession' in html_code)
    result.test("showSqlDetail函数存在", 'function showSqlDetail' in html_code or 'async function showSqlDetail' in html_code)
except Exception as e:
    result.test("代码检查", False, str(e))

# 显示结果
success = result.summary()
sys.exit(0 if success else 1)
