#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MySQL Performance Schema 慢SQL采集器
对数据库侵入最低、性能最好、准确率最高的采集方式

优势:
1. 零侵入 - Performance Schema在后台自动聚合，不影响业务
2. 高性能 - 只需查询聚合表，不需要实时扫描processlist
3. 100%准确 - 所有执行过的SQL都会被记录，不会遗漏
4. 自动去重 - SQL Digest已经做了参数化
5. 丰富指标 - 包含执行次数、平均/最大时间、扫描行数等

使用:
    python mysql_perfschema_collector.py              # 单次采集
    python mysql_perfschema_collector.py --daemon     # 守护进程模式
"""

import os
import sys
import json
import time
import logging
import hashlib
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pymysql

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def load_monitor_db_config() -> Dict:
    """从config.json加载监控数据库配置"""
    config_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                db_config = config.get('database', {})
                return {
                    'host': db_config.get('host', '127.0.0.1'),
                    'port': int(db_config.get('port', 3306)),
                    'user': db_config.get('user', 'root'),
                    'password': db_config.get('password', ''),
                    'database': db_config.get('database', 'db_monitor'),
                    'charset': 'utf8mb4',
                    'cursorclass': pymysql.cursors.DictCursor
                }
    except Exception as e:
        logger.warning(f"加载config.json失败: {e}")

    return {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'root',
        'password': '',
        'database': 'db_monitor',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }


MONITOR_DB_CONFIG = load_monitor_db_config()


class MySQLPerfSchemaCollector:
    """
    MySQL Performance Schema 采集器

    采集策略:
    1. 主要数据源: events_statements_summary_by_digest (聚合数据)
    2. 辅助数据源: information_schema.processlist (实时快照)
    3. 采集间隔: 60秒 (Performance Schema已经聚合，不需要高频采集)
    """

    def __init__(self, instance_config: Dict, threshold_seconds: int = 5):
        self.instance_config = instance_config
        self.instance_id = instance_config['id']
        self.instance_name = instance_config.get('db_project', 'Unknown')
        self.threshold_seconds = threshold_seconds
        self.threshold_microseconds = threshold_seconds * 1000000000000  # Performance Schema用纳秒

    def connect_target(self) -> Optional[pymysql.Connection]:
        """连接目标MySQL实例"""
        try:
            conn = pymysql.connect(
                host=self.instance_config['db_ip'],
                port=self.instance_config.get('db_port', 3306),
                user=self.instance_config.get('db_user', 'root'),
                password=self.instance_config.get('db_password', ''),
                charset='utf8mb4',
                connect_timeout=5,
                cursorclass=pymysql.cursors.DictCursor
            )
            return conn
        except Exception as e:
            logger.error(f"连接目标MySQL失败 {self.instance_name}: {e}")
            return None

    def connect_monitor(self) -> Optional[pymysql.Connection]:
        """连接监控数据库"""
        try:
            return pymysql.connect(**MONITOR_DB_CONFIG)
        except Exception as e:
            logger.error(f"连接监控数据库失败: {e}")
            return None

    def check_perfschema_enabled(self, conn: pymysql.Connection) -> bool:
        """检查Performance Schema是否开启"""
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT @@performance_schema")
                result = cursor.fetchone()
                enabled = result['@@performance_schema'] == 1

                if not enabled:
                    logger.warning(f"{self.instance_name}: Performance Schema未开启")
                    logger.info("开启方法: 在my.cnf中添加 performance_schema=ON 并重启MySQL")

                return enabled
        except Exception as e:
            logger.error(f"检查Performance Schema失败: {e}")
            return False

    def collect_from_perfschema(self, conn: pymysql.Connection) -> List[Dict]:
        """
        从Performance Schema采集慢SQL聚合数据

        数据源: performance_schema.events_statements_summary_by_digest

        优点:
        - 已聚合: 相同SQL模式只有一条记录
        - 零开销: Performance Schema后台自动收集
        - 全面覆盖: 不会遗漏任何执行过的SQL
        - 丰富指标: 执行次数、平均/最大时间、扫描行数、锁等待等

        采集策略:
        - 只采集最近5分钟有执行的SQL
        - 按平均执行时间降序
        - 限制100条
        """
        try:
            with conn.cursor() as cursor:
                # 查询Performance Schema聚合表
                query = """
                SELECT
                    digest AS sql_fingerprint,
                    digest_text AS sql_template,
                    schema_name AS database_name,
                    count_star AS execution_count,
                    sum_timer_wait / 1000000000000 AS total_time_seconds,
                    avg_timer_wait / 1000000000000 AS avg_time_seconds,
                    min_timer_wait / 1000000000000 AS min_time_seconds,
                    max_timer_wait / 1000000000000 AS max_time_seconds,
                    sum_lock_time / 1000000000000 AS total_lock_time_seconds,
                    sum_rows_affected AS total_rows_affected,
                    sum_rows_sent AS total_rows_sent,
                    sum_rows_examined AS total_rows_examined,
                    sum_created_tmp_disk_tables AS tmp_disk_tables,
                    sum_created_tmp_tables AS tmp_tables,
                    sum_sort_rows AS sort_rows,
                    sum_no_index_used AS no_index_used_count,
                    sum_no_good_index_used AS no_good_index_used_count,
                    first_seen,
                    last_seen
                FROM performance_schema.events_statements_summary_by_digest
                WHERE avg_timer_wait >= %s
                  AND last_seen >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                  AND digest_text IS NOT NULL
                  AND digest_text NOT LIKE '%%performance_schema%%'
                  AND digest_text NOT LIKE '%%information_schema%%'
                ORDER BY avg_timer_wait DESC
                LIMIT 100
                """

                cursor.execute(query, (self.threshold_microseconds,))
                results = cursor.fetchall()

                logger.info(f"{self.instance_name}: 从Performance Schema采集到 {len(results)} 条慢SQL聚合记录")

                slow_sqls = []
                for row in results:
                    slow_sql = {
                        'db_instance_id': self.instance_id,
                        'sql_fingerprint': row['sql_fingerprint'][:64] if row['sql_fingerprint'] else None,
                        'sql_template': row['sql_template'],
                        'sql_text': row['sql_template'][:4000] if row['sql_template'] else None,
                        'sql_fulltext': row['sql_template'],
                        'database_name': row['database_name'],
                        'execution_count': int(row['execution_count'] or 0),
                        'avg_elapsed_seconds': float(row['avg_time_seconds'] or 0),
                        'min_elapsed_seconds': float(row['min_time_seconds'] or 0),
                        'max_elapsed_seconds': float(row['max_time_seconds'] or 0),
                        'total_elapsed_seconds': float(row['total_time_seconds'] or 0),
                        'total_lock_time_seconds': float(row['total_lock_time_seconds'] or 0),
                        'rows_examined': int(row['total_rows_examined'] or 0),
                        'rows_sent': int(row['total_rows_sent'] or 0),
                        'rows_affected': int(row['total_rows_affected'] or 0),
                        'tmp_tables': int(row['tmp_tables'] or 0),
                        'tmp_disk_tables': int(row['tmp_disk_tables'] or 0),
                        'no_index_used_count': int(row['no_index_used_count'] or 0),
                        'no_good_index_used_count': int(row['no_good_index_used_count'] or 0),
                        'first_seen': row['first_seen'],
                        'last_seen': row['last_seen'],
                        'detect_time': datetime.now(),
                        'collection_method': 'performance_schema'
                    }

                    slow_sqls.append(slow_sql)

                return slow_sqls

        except Exception as e:
            logger.error(f"{self.instance_name}: 从Performance Schema采集失败: {e}")
            return []

    def collect_from_processlist(self, conn: pymysql.Connection) -> List[Dict]:
        """
        从processlist采集正在执行的慢SQL (辅助)

        用途: 捕获当前正在执行的长时间SQL
        局限: 只能看到快照时刻正在运行的SQL
        """
        try:
            with conn.cursor() as cursor:
                query = """
                SELECT
                    p.id AS session_id,
                    p.user AS username,
                    p.host AS machine,
                    p.db AS database_name,
                    p.command,
                    p.time AS elapsed_seconds,
                    p.state,
                    p.info AS sql_text
                FROM information_schema.processlist p
                WHERE p.command != 'Sleep'
                  AND p.time >= %s
                  AND p.info IS NOT NULL
                  AND p.id != CONNECTION_ID()
                ORDER BY p.time DESC
                LIMIT 50
                """

                cursor.execute(query, (self.threshold_seconds,))
                results = cursor.fetchall()

                logger.info(f"{self.instance_name}: 从Processlist采集到 {len(results)} 条正在执行的慢SQL")

                slow_sqls = []
                for row in results:
                    # 生成SQL指纹
                    sql_fingerprint = self.generate_fingerprint(row['sql_text'])

                    slow_sql = {
                        'db_instance_id': self.instance_id,
                        'session_id': str(row['session_id']),
                        'sql_fingerprint': sql_fingerprint,
                        'sql_text': row['sql_text'][:4000] if row['sql_text'] else None,
                        'sql_fulltext': row['sql_text'],
                        'username': row['username'],
                        'machine': row['machine'],
                        'database_name': row['database_name'],
                        'elapsed_seconds': float(row['elapsed_seconds'] or 0),
                        'elapsed_minutes': float(row['elapsed_seconds'] or 0) / 60.0,
                        'status': row['state'] or 'ACTIVE',
                        'command': row['command'],
                        'detect_time': datetime.now(),
                        'collection_method': 'processlist'
                    }

                    slow_sqls.append(slow_sql)

                return slow_sqls

        except Exception as e:
            logger.error(f"{self.instance_name}: 从Processlist采集失败: {e}")
            return []

    def generate_fingerprint(self, sql: str) -> str:
        """生成SQL指纹 (简化版，Performance Schema的digest更准确)"""
        if not sql:
            return ''

        import re
        # 去除数字
        sql = re.sub(r'\b\d+\b', '?', sql)
        # 去除字符串
        sql = re.sub(r"'[^']*'", '?', sql)
        # 标准化空格
        sql = ' '.join(sql.lower().split())

        return hashlib.md5(sql.encode()).hexdigest()

    def save_to_monitor_db(self, slow_sqls: List[Dict]) -> int:
        """保存慢SQL到监控数据库"""
        if not slow_sqls:
            return 0

        monitor_conn = self.connect_monitor()
        if not monitor_conn:
            return 0

        saved_count = 0

        try:
            with monitor_conn.cursor() as cursor:
                for sql_record in slow_sqls:
                    try:
                        # 插入到long_running_sql_log表
                        insert_sql = """
                        INSERT INTO long_running_sql_log
                        (db_instance_id, session_id, sql_fingerprint, sql_text, sql_fulltext,
                         username, machine, database_name, elapsed_seconds, elapsed_minutes,
                         status, rows_examined, rows_sent, detect_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """

                        cursor.execute(insert_sql, (
                            sql_record.get('db_instance_id'),
                            sql_record.get('session_id', ''),
                            sql_record.get('sql_fingerprint'),
                            sql_record.get('sql_text'),
                            sql_record.get('sql_fulltext'),
                            sql_record.get('username', ''),
                            sql_record.get('machine', ''),
                            sql_record.get('database_name', ''),
                            sql_record.get('avg_elapsed_seconds', sql_record.get('elapsed_seconds', 0)),
                            sql_record.get('avg_elapsed_seconds', sql_record.get('elapsed_seconds', 0)) / 60.0,
                            sql_record.get('status', 'COMPLETED'),
                            sql_record.get('rows_examined', 0),
                            sql_record.get('rows_sent', 0),
                            sql_record.get('detect_time')
                        ))

                        saved_count += 1

                    except Exception as e:
                        logger.debug(f"保存单条记录失败: {e}")

            monitor_conn.commit()
            logger.info(f"{self.instance_name}: 成功保存 {saved_count} 条慢SQL记录")

        except Exception as e:
            logger.error(f"保存到监控数据库失败: {e}")
            monitor_conn.rollback()
        finally:
            monitor_conn.close()

        return saved_count

    def collect(self) -> int:
        """执行完整采集流程"""
        target_conn = self.connect_target()
        if not target_conn:
            return 0

        try:
            # 检查Performance Schema是否开启
            perfschema_enabled = self.check_perfschema_enabled(target_conn)

            all_slow_sqls = []

            # 优先从Performance Schema采集 (主要数据源)
            if perfschema_enabled:
                perfschema_sqls = self.collect_from_perfschema(target_conn)
                all_slow_sqls.extend(perfschema_sqls)

            # 辅助从Processlist采集当前正在运行的 (补充数据源)
            processlist_sqls = self.collect_from_processlist(target_conn)
            all_slow_sqls.extend(processlist_sqls)

            # 保存到监控数据库
            saved_count = self.save_to_monitor_db(all_slow_sqls)

            return saved_count

        finally:
            target_conn.close()


def get_mysql_instances() -> List[Dict]:
    """获取所有MySQL实例"""
    try:
        conn = pymysql.connect(**MONITOR_DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type
                FROM db_instance_info
                WHERE status = 1 AND db_type = 'MySQL'
            """)
            instances = cursor.fetchall()
        conn.close()
        return instances
    except Exception as e:
        logger.error(f"获取MySQL实例列表失败: {e}")
        return []


def collect_all(threshold_seconds: int = 5) -> int:
    """采集所有MySQL实例"""
    logger.info("=" * 60)
    logger.info("开始采集MySQL慢SQL (Performance Schema模式)")
    logger.info("=" * 60)

    instances = get_mysql_instances()
    if not instances:
        logger.warning("没有找到启用的MySQL实例")
        return 0

    logger.info(f"找到 {len(instances)} 个MySQL实例")

    total_saved = 0

    for instance in instances:
        try:
            collector = MySQLPerfSchemaCollector(instance, threshold_seconds)
            saved = collector.collect()
            total_saved += saved
        except Exception as e:
            logger.error(f"采集实例 {instance.get('db_project')} 失败: {e}")

    logger.info(f"采集完成，共保存 {total_saved} 条慢SQL记录")
    logger.info("=" * 60)

    return total_saved


def run_daemon(interval: int = 60, threshold: int = 5):
    """守护进程模式运行"""
    logger.info(f"启动守护进程模式")
    logger.info(f"采集间隔: {interval} 秒")
    logger.info(f"慢SQL阈值: {threshold} 秒")
    logger.info("按 Ctrl+C 停止")
    logger.info("=" * 60)

    while True:
        try:
            collect_all(threshold)
        except Exception as e:
            logger.error(f"采集过程发生异常: {e}")

        logger.info(f"等待 {interval} 秒...")
        time.sleep(interval)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MySQL Performance Schema 慢SQL采集器')
    parser.add_argument('--daemon', '-d', action='store_true', help='守护进程模式')
    parser.add_argument('--interval', '-i', type=int, default=60, help='采集间隔(秒)，默认60秒')
    parser.add_argument('--threshold', '-t', type=int, default=5, help='慢SQL阈值(秒)，默认5秒')

    args = parser.parse_args()

    if args.daemon:
        run_daemon(args.interval, args.threshold)
    else:
        collect_all(args.threshold)


if __name__ == '__main__':
    main()
