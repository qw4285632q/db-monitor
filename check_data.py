#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查数据库中的监控数据"""
import pymysql
import json
from datetime import datetime, timedelta

# 加载配置
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
    db_config = config['database']

# 连接数据库
conn = pymysql.connect(
    host=db_config['host'],
    port=db_config['port'],
    user=db_config['user'],
    password=db_config['password'],
    database=db_config['database'],
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)

print("=" * 70)
print("数据库监控数据检查")
print("=" * 70)

with conn.cursor() as cursor:
    # 1. 检查慢SQL数据
    print("\n[1] 慢SQL数据")
    print("-" * 70)

    # 总数
    cursor.execute("SELECT COUNT(*) as count FROM long_running_sql_log")
    total_slow_sql = cursor.fetchone()['count']
    print(f"总记录数: {total_slow_sql}")

    if total_slow_sql > 0:
        # 最近的记录
        cursor.execute("""
            SELECT l.id, l.detect_time, l.elapsed_minutes, l.sql_text,
                   i.db_project, i.db_ip, i.db_port
            FROM long_running_sql_log l
            LEFT JOIN db_instance_info i ON l.db_instance_id = i.id
            ORDER BY l.detect_time DESC
            LIMIT 5
        """)
        recent_sqls = cursor.fetchall()

        print(f"\n最近5条记录:")
        for sql in recent_sqls:
            print(f"  ID: {sql['id']}")
            print(f"  时间: {sql['detect_time']}")
            print(f"  实例: {sql['db_project']} ({sql['db_ip']}:{sql['db_port']})")
            print(f"  时长: {sql['elapsed_minutes']:.2f} 分钟")
            print(f"  SQL: {sql['sql_text'][:100]}...")
            print()

        # 按时间统计
        cursor.execute("""
            SELECT DATE_FORMAT(detect_time, '%Y-%m-%d %H:00') as hour,
                   COUNT(*) as count
            FROM long_running_sql_log
            WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY hour
            ORDER BY hour DESC
            LIMIT 10
        """)
        hourly_stats = cursor.fetchall()

        print("最近24小时统计 (按小时):")
        for stat in hourly_stats:
            print(f"  {stat['hour']}: {stat['count']} 条")

    else:
        print("[!] 没有慢SQL数据")

    # 2. 检查死锁数据
    print("\n" + "=" * 70)
    print("[2] 死锁数据")
    print("-" * 70)

    cursor.execute("SELECT COUNT(*) as count FROM deadlock_log")
    total_deadlocks = cursor.fetchone()['count']
    print(f"总记录数: {total_deadlocks}")

    if total_deadlocks > 0:
        # 最近的死锁
        cursor.execute("""
            SELECT d.id, d.deadlock_time, d.victim_session_id, d.blocker_session_id,
                   d.victim_sql, d.blocker_sql,
                   i.db_project, i.db_ip, i.db_port
            FROM deadlock_log d
            LEFT JOIN db_instance_info i ON d.db_instance_id = i.id
            ORDER BY d.deadlock_time DESC
            LIMIT 3
        """)
        recent_deadlocks = cursor.fetchall()

        print(f"\n最近3条记录:")
        for dl in recent_deadlocks:
            print(f"  ID: {dl['id']}")
            print(f"  时间: {dl['deadlock_time']}")
            print(f"  实例: {dl['db_project']} ({dl['db_ip']}:{dl['db_port']})")
            print(f"  受害者会话: {dl['victim_session_id']}")
            print(f"  阻塞者会话: {dl['blocker_session_id']}")
            print(f"  受害者SQL: {dl['victim_sql'][:80]}...")
            print(f"  阻塞者SQL: {dl['blocker_sql'][:80]}...")
            print()

    else:
        print("[!] 没有死锁数据")

    # 3. 检查采集情况
    print("\n" + "=" * 70)
    print("[3] 采集情况分析")
    print("-" * 70)

    # 按实例统计慢SQL
    cursor.execute("""
        SELECT i.db_project, i.db_ip, i.db_type,
               COUNT(l.id) as slow_sql_count,
               MAX(l.detect_time) as last_collect_time
        FROM db_instance_info i
        LEFT JOIN long_running_sql_log l ON i.id = l.db_instance_id
        WHERE i.status = 1
        GROUP BY i.id
        ORDER BY i.id
    """)
    instance_stats = cursor.fetchall()

    print("\n各实例慢SQL统计:")
    for stat in instance_stats:
        print(f"  {stat['db_project']} ({stat['db_ip']}) [{stat['db_type']}]")
        print(f"    慢SQL记录: {stat['slow_sql_count']}")
        print(f"    最后采集: {stat['last_collect_time'] or '从未'}")

    # 最近24小时是否有采集
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM long_running_sql_log
        WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    """)
    recent_count = cursor.fetchone()['count']

    print(f"\n最近24小时采集的慢SQL: {recent_count} 条")

    if recent_count == 0:
        print("\n[警告] 最近24小时没有采集到任何慢SQL数据！")
        print("可能原因:")
        print("  1. 采集器未运行或运行时间不足")
        print("  2. 数据库确实没有慢SQL（运行时间 > 60秒）")
        print("  3. 采集器无法连接到目标数据库")
        print("  4. 慢SQL阈值设置太高")

conn.close()

print("\n" + "=" * 70)
print("检查完成")
print("=" * 70)
