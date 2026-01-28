#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库Long SQL监控系统 - 数据采集脚本
定期从各数据库实例采集长时间运行的SQL语句

支持的数据库类型:
- Oracle
- MySQL
- PostgreSQL

使用方法:
    python collect_long_sql.py              # 单次采集
    python collect_long_sql.py --daemon     # 后台持续采集
    python collect_long_sql.py --interval 60  # 指定采集间隔(秒)
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymysql

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 监控数据库配置
MONITOR_DB_CONFIG = {
    'host': os.getenv('DB_HOST', '192.168.11.85'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'Root#2025Jac.Com'),
    'database': os.getenv('DB_NAME', 'db_monitor'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 长时间SQL阈值(秒)
LONG_SQL_THRESHOLD_SECONDS = 60  # 1分钟

# Oracle查询长时间运行SQL的SQL语句
ORACLE_LONG_SQL_QUERY = """
SELECT
    s.sid as session_id,
    s.serial# as serial_no,
    s.sql_id,
    SUBSTR(q.sql_text, 1, 4000) as sql_text,
    q.sql_fulltext,
    s.username,
    s.machine,
    s.program,
    s.module,
    s.action,
    ROUND((SYSDATE - s.sql_exec_start) * 24 * 60 * 60, 2) as elapsed_seconds,
    ROUND((SYSDATE - s.sql_exec_start) * 24 * 60, 4) as elapsed_minutes,
    s.status,
    s.blocking_session,
    s.event,
    s.sql_exec_start
FROM v$session s
LEFT JOIN v$sql q ON s.sql_id = q.sql_id AND s.sql_child_number = q.child_number
WHERE s.status = 'ACTIVE'
    AND s.type = 'USER'
    AND s.sql_exec_start IS NOT NULL
    AND (SYSDATE - s.sql_exec_start) * 24 * 60 * 60 > :threshold
    AND s.username NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN')
ORDER BY elapsed_seconds DESC
"""

# MySQL查询长时间运行SQL的SQL语句
MYSQL_LONG_SQL_QUERY = """
SELECT
    p.ID as session_id,
    p.ID as serial_no,
    NULL as sql_id,
    SUBSTRING(p.INFO, 1, 4000) as sql_text,
    p.INFO as sql_fulltext,
    p.USER as username,
    p.HOST as machine,
    p.DB as program,
    NULL as module,
    NULL as action,
    p.TIME as elapsed_seconds,
    ROUND(p.TIME / 60, 4) as elapsed_minutes,
    p.STATE as status,
    NULL as blocking_session,
    p.STATE as event,
    DATE_SUB(NOW(), INTERVAL p.TIME SECOND) as sql_exec_start
FROM information_schema.PROCESSLIST p
WHERE p.COMMAND != 'Sleep'
    AND p.INFO IS NOT NULL
    AND p.TIME > %s
    AND p.USER NOT IN ('system user', 'event_scheduler')
ORDER BY p.TIME DESC
"""

# PostgreSQL查询长时间运行SQL的SQL语句
PGSQL_LONG_SQL_QUERY = """
SELECT
    pid as session_id,
    pid as serial_no,
    NULL as sql_id,
    SUBSTRING(query, 1, 4000) as sql_text,
    query as sql_fulltext,
    usename as username,
    client_addr::text as machine,
    application_name as program,
    NULL as module,
    NULL as action,
    EXTRACT(EPOCH FROM (NOW() - query_start))::integer as elapsed_seconds,
    ROUND(EXTRACT(EPOCH FROM (NOW() - query_start)) / 60, 4) as elapsed_minutes,
    state as status,
    NULL as blocking_session,
    wait_event as event,
    query_start as sql_exec_start
FROM pg_stat_activity
WHERE state = 'active'
    AND query NOT LIKE '%pg_stat_activity%'
    AND EXTRACT(EPOCH FROM (NOW() - query_start)) > %s
    AND usename NOT IN ('postgres', 'replication')
ORDER BY elapsed_seconds DESC
"""


def get_monitor_connection():
    """获取监控数据库连接"""
    try:
        return pymysql.connect(**MONITOR_DB_CONFIG)
    except Exception as e:
        logger.error(f"连接监控数据库失败: {e}")
        return None


def get_instances():
    """获取所有需要监控的数据库实例"""
    conn = get_monitor_connection()
    if not conn:
        return []

    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT id, db_project, db_ip, db_port, instance_name,
                   db_type, db_user, db_password
            FROM db_instance_info
            WHERE status = 1
                AND db_type IN ('Oracle', 'MySQL', 'PostgreSQL')
                AND db_ip IS NOT NULL
            """
            cursor.execute(sql)
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"获取实例列表失败: {e}")
        return []
    finally:
        conn.close()


def collect_from_oracle(instance):
    """从Oracle数据库采集长时间运行SQL"""
    try:
        import cx_Oracle
    except ImportError:
        logger.warning(f"cx_Oracle未安装，跳过Oracle实例 {instance['db_ip']}")
        return []

    try:
        dsn = cx_Oracle.makedsn(
            instance['db_ip'],
            instance['db_port'],
            service_name=instance['instance_name']
        )
        conn = cx_Oracle.connect(
            user=instance['db_user'],
            password=instance['db_password'],
            dsn=dsn
        )

        cursor = conn.cursor()
        cursor.execute(ORACLE_LONG_SQL_QUERY, {'threshold': LONG_SQL_THRESHOLD_SECONDS})

        columns = [col[0].lower() for col in cursor.description]
        results = []
        for row in cursor:
            results.append(dict(zip(columns, row)))

        cursor.close()
        conn.close()

        logger.info(f"从Oracle {instance['db_ip']} 采集到 {len(results)} 条长时间SQL")
        return results

    except Exception as e:
        logger.error(f"Oracle采集失败 {instance['db_ip']}: {e}")
        return []


def collect_from_mysql(instance):
    """从MySQL数据库采集长时间运行SQL"""
    try:
        conn = pymysql.connect(
            host=instance['db_ip'],
            port=instance['db_port'],
            user=instance['db_user'],
            password=instance['db_password'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10
        )

        with conn.cursor() as cursor:
            cursor.execute(MYSQL_LONG_SQL_QUERY, (LONG_SQL_THRESHOLD_SECONDS,))
            results = cursor.fetchall()

        conn.close()

        logger.info(f"从MySQL {instance['db_ip']} 采集到 {len(results)} 条长时间SQL")
        return results

    except Exception as e:
        logger.error(f"MySQL采集失败 {instance['db_ip']}: {e}")
        return []


def collect_from_postgresql(instance):
    """从PostgreSQL数据库采集长时间运行SQL"""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logger.warning(f"psycopg2未安装，跳过PostgreSQL实例 {instance['db_ip']}")
        return []

    try:
        conn = psycopg2.connect(
            host=instance['db_ip'],
            port=instance['db_port'],
            user=instance['db_user'],
            password=instance['db_password'],
            database='postgres',
            connect_timeout=10
        )

        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(PGSQL_LONG_SQL_QUERY, (LONG_SQL_THRESHOLD_SECONDS,))
        results = cursor.fetchall()

        cursor.close()
        conn.close()

        logger.info(f"从PostgreSQL {instance['db_ip']} 采集到 {len(results)} 条长时间SQL")
        return [dict(row) for row in results]

    except Exception as e:
        logger.error(f"PostgreSQL采集失败 {instance['db_ip']}: {e}")
        return []


def collect_from_instance(instance):
    """根据数据库类型调用对应的采集函数"""
    db_type = instance.get('db_type', '').lower()

    if db_type == 'oracle':
        return collect_from_oracle(instance)
    elif db_type == 'mysql':
        return collect_from_mysql(instance)
    elif db_type == 'postgresql':
        return collect_from_postgresql(instance)
    else:
        logger.warning(f"不支持的数据库类型: {db_type}")
        return []


def save_to_monitor_db(instance_id, sql_records):
    """保存采集到的SQL记录到监控数据库"""
    if not sql_records:
        return 0

    conn = get_monitor_connection()
    if not conn:
        return 0

    detect_time = datetime.now()
    saved_count = 0

    try:
        with conn.cursor() as cursor:
            for record in sql_records:
                sql = """
                INSERT INTO long_running_sql_log
                (db_instance_id, session_id, serial_no, sql_id, sql_text, sql_fulltext,
                 username, machine, program, module, action,
                 elapsed_seconds, elapsed_minutes, status, blocking_session,
                 event, sql_exec_start, detect_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                try:
                    cursor.execute(sql, (
                        instance_id,
                        str(record.get('session_id', '')),
                        str(record.get('serial_no', '')),
                        record.get('sql_id'),
                        record.get('sql_text', '')[:4000] if record.get('sql_text') else None,
                        record.get('sql_fulltext'),
                        record.get('username'),
                        record.get('machine'),
                        record.get('program'),
                        record.get('module'),
                        record.get('action'),
                        record.get('elapsed_seconds', 0),
                        record.get('elapsed_minutes', 0),
                        record.get('status'),
                        str(record.get('blocking_session', '')) if record.get('blocking_session') else None,
                        record.get('event'),
                        record.get('sql_exec_start'),
                        detect_time
                    ))
                    saved_count += 1
                except Exception as e:
                    logger.error(f"保存记录失败: {e}")

        conn.commit()
        logger.info(f"成功保存 {saved_count} 条SQL记录")

    except Exception as e:
        logger.error(f"保存数据失败: {e}")
        conn.rollback()
    finally:
        conn.close()

    return saved_count


def collect_all():
    """采集所有实例的长时间运行SQL"""
    logger.info("=" * 50)
    logger.info("开始采集长时间运行SQL")
    logger.info("=" * 50)

    instances = get_instances()
    if not instances:
        logger.warning("没有找到需要监控的数据库实例")
        return

    logger.info(f"共有 {len(instances)} 个实例需要采集")

    total_saved = 0

    # 使用线程池并行采集
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_instance = {
            executor.submit(collect_from_instance, inst): inst
            for inst in instances
        }

        for future in as_completed(future_to_instance):
            instance = future_to_instance[future]
            try:
                records = future.result()
                if records:
                    saved = save_to_monitor_db(instance['id'], records)
                    total_saved += saved
            except Exception as e:
                logger.error(f"采集实例 {instance['db_ip']} 时发生异常: {e}")

    logger.info(f"采集完成，共保存 {total_saved} 条记录")
    logger.info("=" * 50)


def run_daemon(interval=60):
    """以守护进程模式运行"""
    logger.info(f"启动守护进程模式，采集间隔: {interval}秒")

    while True:
        try:
            collect_all()
        except Exception as e:
            logger.error(f"采集过程发生异常: {e}")

        logger.info(f"等待 {interval} 秒后进行下一次采集...")
        time.sleep(interval)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据库长时间SQL采集脚本')
    parser.add_argument('--daemon', '-d', action='store_true',
                        help='以守护进程模式运行')
    parser.add_argument('--interval', '-i', type=int, default=60,
                        help='采集间隔(秒)，默认60秒')
    parser.add_argument('--threshold', '-t', type=int, default=60,
                        help='长时间SQL阈值(秒)，默认60秒')

    args = parser.parse_args()

    global LONG_SQL_THRESHOLD_SECONDS
    LONG_SQL_THRESHOLD_SECONDS = args.threshold

    if args.daemon:
        run_daemon(args.interval)
    else:
        collect_all()


if __name__ == '__main__':
    main()
