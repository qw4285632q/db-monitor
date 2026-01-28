#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库Long SQL监控系统 - 测试数据生成脚本
用于生成模拟的数据库实例和长时间运行SQL记录
"""

import pymysql
import random
from datetime import datetime, timedelta
import os

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '192.168.11.85'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'Root#2025Jac.Com'),
    'database': os.getenv('DB_NAME', 'db_monitor'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 模拟数据配置
MOCK_INSTANCES = [
    {'db_project': '订单系统', 'db_ip': '192.168.1.101', 'db_port': 3306, 'db_type': 'MySQL', 'instance_name': 'order-db-master'},
    {'db_project': '订单系统', 'db_ip': '192.168.1.102', 'db_port': 3306, 'db_type': 'MySQL', 'instance_name': 'order-db-slave'},
    {'db_project': '用户中心', 'db_ip': '192.168.1.110', 'db_port': 3306, 'db_type': 'MySQL', 'instance_name': 'user-db-master'},
    {'db_project': '支付平台', 'db_ip': '192.168.1.120', 'db_port': 1521, 'db_type': 'Oracle', 'instance_name': 'pay-orcl'},
    {'db_project': '库存管理', 'db_ip': '192.168.1.130', 'db_port': 3306, 'db_type': 'MySQL', 'instance_name': 'inventory-db'},
    {'db_project': '日志分析', 'db_ip': '192.168.1.140', 'db_port': 5432, 'db_type': 'PostgreSQL', 'instance_name': 'log-analytics'},
    {'db_project': '报表系统', 'db_ip': '192.168.1.150', 'db_port': 1521, 'db_type': 'Oracle', 'instance_name': 'report-orcl'},
    {'db_project': 'CRM系统', 'db_ip': '192.168.1.160', 'db_port': 3306, 'db_type': 'MySQL', 'instance_name': 'crm-db'},
    {'db_project': 'ERP系统', 'db_ip': '192.168.1.170', 'db_port': 1521, 'db_type': 'Oracle', 'instance_name': 'erp-orcl'},
    {'db_project': '数据仓库', 'db_ip': '192.168.1.180', 'db_port': 3306, 'db_type': 'MySQL', 'instance_name': 'dw-master'},
]

SQL_TEMPLATES = [
    "SELECT * FROM orders o JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id WHERE o.created_at > DATE_SUB(NOW(), INTERVAL 30 DAY) AND o.status IN ('pending', 'processing') ORDER BY o.created_at DESC",
    "UPDATE users SET last_login = NOW(), login_count = login_count + 1 WHERE id IN (SELECT user_id FROM sessions WHERE expired_at < NOW())",
    "SELECT u.*, COUNT(o.id) as order_count, SUM(o.total_amount) as total_spent FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id HAVING order_count > 10",
    "DELETE FROM logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY) AND level = 'DEBUG'",
    "INSERT INTO report_cache (report_id, data, generated_at) SELECT id, generate_report_data(id), NOW() FROM reports WHERE status = 'pending'",
    "SELECT p.*, c.name as category_name, SUM(oi.quantity) as sold_count FROM products p JOIN categories c ON p.category_id = c.id LEFT JOIN order_items oi ON p.id = oi.product_id GROUP BY p.id ORDER BY sold_count DESC LIMIT 100",
    "WITH RECURSIVE category_tree AS (SELECT id, name, parent_id, 0 as level FROM categories WHERE parent_id IS NULL UNION ALL SELECT c.id, c.name, c.parent_id, ct.level + 1 FROM categories c JOIN category_tree ct ON c.parent_id = ct.id) SELECT * FROM category_tree",
    "SELECT DATE(created_at) as date, COUNT(*) as count, AVG(response_time) as avg_time FROM api_logs WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY) GROUP BY DATE(created_at)",
    "ANALYZE TABLE orders, order_items, products, users, inventory",
    "SELECT * FROM inventory i WHERE i.quantity < i.min_stock AND i.product_id IN (SELECT product_id FROM order_items WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY) GROUP BY product_id HAVING COUNT(*) > 5)",
    "SELECT c.customer_name, SUM(o.amount) total_amount FROM customers c INNER JOIN orders o ON c.id = o.customer_id WHERE o.order_date BETWEEN '2024-01-01' AND '2024-12-31' GROUP BY c.id ORDER BY total_amount DESC",
    "UPDATE inventory SET quantity = quantity - (SELECT SUM(qty) FROM order_items WHERE order_id = 12345) WHERE product_id IN (SELECT product_id FROM order_items WHERE order_id = 12345)",
    "SELECT * FROM transactions t WHERE t.status = 'pending' AND t.created_at < NOW() - INTERVAL 1 HOUR FOR UPDATE",
    "CREATE INDEX CONCURRENTLY idx_orders_user_date ON orders(user_id, created_at DESC)",
    "SELECT s.*, u.username, p.name as product_name FROM sales s JOIN users u ON s.seller_id = u.id JOIN products p ON s.product_id = p.id WHERE s.sale_date >= CURDATE() - INTERVAL 30 DAY AND s.amount > 1000",
    "CALL generate_monthly_report(@report_id, @start_date, @end_date)",
    "SELECT region, product_category, SUM(quantity) as total_qty, SUM(amount) as total_amount FROM sales_fact GROUP BY ROLLUP(region, product_category)",
    "MERGE INTO target_table t USING source_table s ON t.id = s.id WHEN MATCHED THEN UPDATE SET t.value = s.value WHEN NOT MATCHED THEN INSERT (id, value) VALUES (s.id, s.value)",
    "SELECT DISTINCT customer_id FROM orders WHERE order_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR) AND customer_id NOT IN (SELECT customer_id FROM orders WHERE order_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH))",
    "EXPLAIN ANALYZE SELECT * FROM large_table WHERE indexed_column = 'value' AND unindexed_column LIKE '%pattern%'"
]

USERNAMES = ['app_user', 'report_service', 'etl_process', 'admin', 'batch_job',
             'analytics', 'sync_service', 'backup_user', 'cron_task', 'api_gateway',
             'order_service', 'payment_worker', 'inventory_sync', 'log_collector']

MACHINES = ['app-server-01', 'app-server-02', 'batch-server-01', 'etl-worker-01',
            'report-server-01', 'api-gateway-01', 'scheduler-01', 'analytics-node-01']

PROGRAMS = ['python3', 'java', 'node', 'sqlplus', 'mysql', 'psql',
            'DataGrip', 'DBeaver', 'Navicat', 'JDBC Thin Client']

WAIT_EVENTS = ['db file sequential read', 'db file scattered read', 'log file sync',
               'buffer busy waits', 'enq: TX - row lock contention', 'direct path read',
               'SQL*Net message from client', 'latch: cache buffers chains', None]


def get_connection():
    """获取数据库连接"""
    try:
        return pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return None


def clear_existing_data(conn):
    """清除现有测试数据"""
    with conn.cursor() as cursor:
        print("正在清除现有数据...")
        cursor.execute("DELETE FROM long_running_sql_log")
        cursor.execute("DELETE FROM alert_history")
        cursor.execute("DELETE FROM db_instance_info")
        conn.commit()
        print("数据清除完成")


def insert_instances(conn):
    """插入数据库实例"""
    instance_ids = []
    with conn.cursor() as cursor:
        print("正在插入数据库实例...")
        for inst in MOCK_INSTANCES:
            sql = """
            INSERT INTO db_instance_info
            (db_project, db_ip, db_port, instance_name, db_type, db_user, db_admin, environment, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                inst['db_project'],
                inst['db_ip'],
                inst['db_port'],
                inst['instance_name'],
                inst['db_type'],
                'app_user',
                'dba_admin',
                random.choice(['production', 'staging', 'development']),
                1
            ))
            instance_ids.append(cursor.lastrowid)

        conn.commit()
        print(f"已插入 {len(instance_ids)} 个数据库实例")

    return instance_ids


def insert_sql_logs(conn, instance_ids, count=200):
    """插入长时间运行SQL日志"""
    now = datetime.now()

    with conn.cursor() as cursor:
        print(f"正在生成 {count} 条SQL日志...")

        for i in range(count):
            # 随机选择实例
            instance_id = random.choice(instance_ids)

            # 随机生成运行时间（分钟）
            # 权重分布：大部分在1-5分钟，少部分在5-10分钟，更少在10+分钟
            rand = random.random()
            if rand < 0.6:
                elapsed_minutes = random.uniform(1.0, 5.0)
            elif rand < 0.85:
                elapsed_minutes = random.uniform(5.0, 10.0)
            else:
                elapsed_minutes = random.uniform(10.0, 30.0)

            elapsed_seconds = elapsed_minutes * 60

            # 随机检测时间（最近48小时内）
            detect_time = now - timedelta(hours=random.uniform(0, 48))
            sql_exec_start = detect_time - timedelta(minutes=elapsed_minutes)

            # 选择SQL模板
            sql_text = random.choice(SQL_TEMPLATES)

            # 生成其他字段
            session_id = str(random.randint(1000, 9999))
            serial_no = str(random.randint(100, 999))
            sql_id = f"sql_{random.randint(10000, 99999)}"
            username = random.choice(USERNAMES)
            machine = random.choice(MACHINES)
            program = random.choice(PROGRAMS)
            event = random.choice(WAIT_EVENTS)

            # CPU时间和等待时间
            cpu_time = elapsed_seconds * random.uniform(0.3, 0.8)
            wait_time = elapsed_seconds - cpu_time

            # 读取数
            logical_reads = random.randint(1000, 10000000)
            physical_reads = int(logical_reads * random.uniform(0.01, 0.1))

            sql = """
            INSERT INTO long_running_sql_log
            (db_instance_id, session_id, serial_no, sql_id, sql_text, sql_fulltext,
             username, machine, program, elapsed_seconds, elapsed_minutes,
             cpu_time, wait_time, logical_reads, physical_reads, status,
             event, sql_exec_start, detect_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(sql, (
                instance_id,
                session_id,
                serial_no,
                sql_id,
                sql_text[:200] + '...' if len(sql_text) > 200 else sql_text,
                sql_text,
                username,
                machine,
                program,
                round(elapsed_seconds, 2),
                round(elapsed_minutes, 4),
                round(cpu_time, 2),
                round(wait_time, 2),
                logical_reads,
                physical_reads,
                random.choice(['ACTIVE', 'ACTIVE', 'ACTIVE', 'INACTIVE']),
                event,
                sql_exec_start,
                detect_time
            ))

            if (i + 1) % 50 == 0:
                print(f"  已生成 {i + 1} 条记录...")

        conn.commit()
        print(f"已插入 {count} 条SQL日志")


def generate_statistics(conn):
    """生成并显示统计信息"""
    with conn.cursor() as cursor:
        print("\n" + "=" * 50)
        print("数据统计信息")
        print("=" * 50)

        # 实例统计
        cursor.execute("SELECT COUNT(*) as count FROM db_instance_info")
        result = cursor.fetchone()
        print(f"数据库实例数: {result['count']}")

        # SQL日志统计
        cursor.execute("SELECT COUNT(*) as count FROM long_running_sql_log")
        result = cursor.fetchone()
        print(f"SQL日志总数: {result['count']}")

        # 按时间范围统计
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN detect_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 ELSE 0 END) as last_1h,
                SUM(CASE WHEN detect_time >= DATE_SUB(NOW(), INTERVAL 6 HOUR) THEN 1 ELSE 0 END) as last_6h,
                SUM(CASE WHEN detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN 1 ELSE 0 END) as last_24h
            FROM long_running_sql_log
        """)
        result = cursor.fetchone()
        print(f"最近1小时: {result['last_1h']} 条")
        print(f"最近6小时: {result['last_6h']} 条")
        print(f"最近24小时: {result['last_24h']} 条")

        # 按严重程度统计
        cursor.execute("""
            SELECT
                SUM(CASE WHEN elapsed_minutes > 10 THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN elapsed_minutes > 5 AND elapsed_minutes <= 10 THEN 1 ELSE 0 END) as warning,
                SUM(CASE WHEN elapsed_minutes <= 5 THEN 1 ELSE 0 END) as normal
            FROM long_running_sql_log
            WHERE detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """)
        result = cursor.fetchone()
        print(f"\n最近24小时告警分布:")
        print(f"  严重(>10分钟): {result['critical']} 条")
        print(f"  警告(5-10分钟): {result['warning']} 条")
        print(f"  正常(<=5分钟): {result['normal']} 条")

        # 按实例统计
        cursor.execute("""
            SELECT
                i.db_project,
                i.instance_name,
                COUNT(l.id) as sql_count,
                ROUND(AVG(l.elapsed_minutes), 2) as avg_minutes
            FROM db_instance_info i
            LEFT JOIN long_running_sql_log l ON i.id = l.db_instance_id
                AND l.detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY i.id
            ORDER BY sql_count DESC
            LIMIT 10
        """)
        results = cursor.fetchall()
        print(f"\n各实例SQL数量(最近24小时):")
        for row in results:
            print(f"  {row['db_project']} ({row['instance_name']}): {row['sql_count']} 条, 平均 {row['avg_minutes']} 分钟")


def main():
    """主函数"""
    print("=" * 50)
    print("数据库Long SQL监控系统 - 测试数据生成")
    print("=" * 50)

    conn = get_connection()
    if not conn:
        print("无法连接数据库，请检查配置")
        return

    try:
        # 清除现有数据
        clear_existing_data(conn)

        # 插入实例
        instance_ids = insert_instances(conn)

        # 插入SQL日志
        insert_sql_logs(conn, instance_ids, count=200)

        # 显示统计
        generate_statistics(conn)

        print("\n" + "=" * 50)
        print("测试数据生成完成！")
        print("=" * 50)

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
