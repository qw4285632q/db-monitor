#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建测试用的长时间运行SQL"""
import pymysql
import json
import time
import threading

# 加载配置
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# 连接监控数据库
monitor_conn = pymysql.connect(**config['database'], cursorclass=pymysql.cursors.DictCursor)

with monitor_conn.cursor() as cursor:
    cursor.execute("""
        SELECT db_ip, db_port, db_user, db_password, db_project
        FROM db_instance_info
        WHERE db_type = 'MySQL' AND status = 1
        LIMIT 1
    """)
    instance = cursor.fetchone()

monitor_conn.close()

if not instance:
    print("没有找到MySQL实例")
    exit(1)

print(f"将在实例上创建测试SQL: {instance['db_project']} ({instance['db_ip']}:{instance['db_port']})")
print("=" * 70)
print("创建3个长时间运行的SQL，持续30秒...")
print("你可以在实时监控页面看到这些SQL")
print("=" * 70)

def run_long_query(query_id, duration):
    """运行一个长时间查询"""
    conn = pymysql.connect(
        host=instance['db_ip'],
        port=instance['db_port'],
        user=instance['db_user'],
        password=instance['db_password']
    )

    cursor = conn.cursor()
    try:
        print(f"[查询{query_id}] 开始执行，持续{duration}秒...")
        # 使用SLEEP函数模拟长时间查询
        cursor.execute(f"SELECT SLEEP({duration}) as result, '测试查询{query_id}' as name")
        result = cursor.fetchone()
        print(f"[查询{query_id}] 执行完成")
    except Exception as e:
        print(f"[查询{query_id}] 被终止或出错: {e}")
    finally:
        cursor.close()
        conn.close()

# 创建3个线程，每个运行一个长查询
threads = []
for i in range(1, 4):
    t = threading.Thread(target=run_long_query, args=(i, 30))
    t.daemon = True
    t.start()
    threads.append(t)
    time.sleep(1)  # 错开启动时间

print("\n✓ 测试SQL已启动！")
print("现在去浏览器打开实时监控页面，应该能看到3个正在运行的SQL")
print("它们会在30秒后自动结束")
print("\n按 Ctrl+C 可以提前终止所有查询")

try:
    for t in threads:
        t.join()
    print("\n所有测试SQL已完成")
except KeyboardInterrupt:
    print("\n用户中断，测试SQL会自动结束")
