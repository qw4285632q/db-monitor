#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库Long SQL与死锁监控系统 - 增强版采集脚本
支持MySQL Performance Schema、死锁检测、执行计划采集、企业微信告警

特性:
- MySQL慢SQL实时监控 (Performance Schema + Processlist)
- 死锁自动检测和告警
- SQL执行计划采集
- SQL指纹去重
- 自适应采集间隔
- 企业微信实时告警
- SQL Server支持(可选)

使用:
    python collector_enhanced.py --daemon --interval 10
"""

import os
import sys
import time
import json
import logging
import hashlib
import argparse
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import pymysql

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.alert import AlertManager, load_alert_config
from sqlserver_collector import SQLServerCollector, PYODBC_AVAILABLE

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
# 设置日志编码避免中文/特殊字符错误
for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.stream.reconfigure(encoding='utf-8', errors='ignore')
logger = logging.getLogger(__name__)


def load_monitor_db_config() -> Dict:
    """从config.json加载监控数据库配置"""
    config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                db_config = config.get('database', {})
                logger.info(f"从config.json加载配置: {db_config.get('host')}:{db_config.get('port')}")
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
        logger.warning(f"加载config.json失败: {e}，使用默认配置")

    # 使用环境变量或默认值
    return {
        'host': os.getenv('DB_HOST', '127.0.0.1'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'db_monitor'),
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }


# 监控数据库配置
MONITOR_DB_CONFIG = load_monitor_db_config()

# 全局配置
LONG_SQL_THRESHOLD_SECONDS = 5  # 慢SQL阈值(秒) - 降低到5秒更容易捕获慢SQL
COLLECT_INTERVAL = 10  # 采集间隔(秒)
ALERT_THRESHOLD_MINUTES = 1  # 告警阈值(分钟) - 降低到1分钟更及时告警
MAX_WORKERS = 5  # 并发采集线程数


def get_sql_fingerprint(sql: str) -> str:
    """
    生成SQL指纹(去参数化)

    SELECT * FROM users WHERE id = 123
    → SELECT * FROM users WHERE id = ?
    """
    if not sql:
        return ''

    # 替换数字
    sql = re.sub(r'\b\d+\b', '?', sql)
    # 替换字符串
    sql = re.sub(r"'[^']*'", '?', sql)
    # 替换IN子句
    sql = re.sub(r'IN\s*\([^)]+\)', 'IN (?)', sql, flags=re.IGNORECASE)
    # 转小写并去除多余空格
    sql = ' '.join(sql.lower().split())

    return hashlib.md5(sql.encode()).hexdigest()


class MySQLCollector:
    """MySQL增强采集器"""

    def __init__(self, instance_config: Dict, alert_manager: Optional[AlertManager] = None):
        self.instance_config = instance_config
        self.alert_manager = alert_manager
        self.instance_id = instance_config['id']
        self.instance_name = instance_config.get('db_project', 'Unknown')

    def connect(self) -> Optional[pymysql.Connection]:
        """连接数据库"""
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
            logger.error(f"连接失败 {self.instance_name}: {e}")
            return None

    def collect_running_queries(self) -> List[Dict]:
        """采集正在运行的慢SQL"""
        conn = self.connect()
        if not conn:
            return []

        try:
            with conn.cursor() as cursor:
                # 查询正在运行的SQL
                query = """
                SELECT
                    p.id as session_id,
                    p.user as username,
                    p.host as machine,
                    p.db as database_name,
                    p.command,
                    p.time as elapsed_seconds,
                    p.state,
                    p.info as sql_text,
                    t.trx_id,
                    t.trx_started,
                    t.trx_isolation_level as isolation_level,
                    t.trx_rows_locked,
                    t.trx_rows_modified
                FROM information_schema.processlist p
                LEFT JOIN information_schema.innodb_trx t
                    ON t.trx_mysql_thread_id = p.id
                WHERE p.command != 'Sleep'
                  AND p.time >= %s
                  AND p.info IS NOT NULL
                  AND p.id != CONNECTION_ID()
                ORDER BY p.time DESC
                """

                cursor.execute(query, (LONG_SQL_THRESHOLD_SECONDS,))
                results = cursor.fetchall()

                logger.info(f"查询到 {len(results)} 条运行中的SQL (阈值={LONG_SQL_THRESHOLD_SECONDS}秒)")

                slow_sqls = []
                for row in results:
                    sql_text = row['sql_text'] or ''

                    # 获取执行计划
                    explain_result = self.get_explain(cursor, sql_text, row.get('database_name'))

                    # 获取性能指标
                    perf_metrics = self.get_performance_metrics(cursor, row['session_id'])

                    slow_sql = {
                        'db_instance_id': self.instance_id,
                        'session_id': str(row['session_id']),
                        'sql_id': row.get('trx_id', ''),
                        'sql_fingerprint': get_sql_fingerprint(sql_text),
                        'sql_text': sql_text[:4000] if len(sql_text) > 4000 else sql_text,
                        'sql_fulltext': sql_text,
                        'username': row['username'],
                        'machine': row['machine'],
                        'program': row['command'],
                        'elapsed_seconds': row['elapsed_seconds'] or 0,
                        'elapsed_minutes': (row['elapsed_seconds'] or 0) / 60.0,
                        'status': row['state'] or 'ACTIVE',
                        'isolation_level': row.get('isolation_level', ''),
                        'cpu_time': perf_metrics.get('cpu_time', 0),
                        'wait_time': perf_metrics.get('wait_time', 0),
                        'logical_reads': perf_metrics.get('logical_reads', 0),
                        'physical_reads': perf_metrics.get('physical_reads', 0),
                        'rows_examined': explain_result.get('rows_examined', 0) or perf_metrics.get('rows_examined', 0),
                        'rows_sent': perf_metrics.get('rows_sent', 0),
                        'query_cost': explain_result.get('query_cost', 0),
                        'execution_plan': json.dumps(explain_result.get('plan', []))if explain_result.get('plan') else None,
                        'index_used': explain_result.get('indexes_used', ''),
                        'full_table_scan': 1 if explain_result.get('has_full_scan') else 0,
                        'sql_exec_start': row.get('trx_started', datetime.now()),
                        'detect_time': datetime.now()
                    }

                    slow_sqls.append(slow_sql)

                return slow_sqls

        except Exception as e:
            logger.error(f"采集慢SQL失败 {self.instance_name}: {e}")
            return []
        finally:
            conn.close()

    def get_performance_metrics(self, cursor, session_id: int) -> Dict:
        """获取会话性能指标（从performance_schema）"""
        try:
            # 尝试从performance_schema获取详细性能指标
            cursor.execute("""
                SELECT
                    SUM(timer_wait)/1000000000000 as wait_time_seconds,
                    SUM(lock_time)/1000000000000 as lock_time_seconds,
                    SUM(rows_examined) as rows_examined,
                    SUM(rows_sent) as rows_sent,
                    SUM(rows_affected) as rows_affected
                FROM performance_schema.events_statements_current
                WHERE thread_id = (SELECT thread_id FROM performance_schema.threads WHERE processlist_id = %s)
            """, (session_id,))

            result = cursor.fetchone()

            if result and result.get('rows_examined'):
                return {
                    'cpu_time': 0,  # MySQL不直接提供CPU时间
                    'wait_time': result.get('wait_time_seconds', 0) or 0,
                    'logical_reads': 0,  # MySQL没有逻辑读概念
                    'physical_reads': 0,  # MySQL没有物理读概念
                    'rows_examined': result.get('rows_examined', 0) or 0,
                    'rows_sent': result.get('rows_sent', 0) or 0,
                }

        except Exception as e:
            logger.debug(f"获取性能指标失败: {e}")

        return {
            'cpu_time': 0,
            'wait_time': 0,
            'logical_reads': 0,
            'physical_reads': 0,
            'rows_examined': 0,
            'rows_sent': 0
        }

    def get_explain(self, cursor, sql: str, database: Optional[str]) -> Dict:
        """获取SQL执行计划"""
        try:
            # 切换数据库
            if database:
                cursor.execute(f"USE `{database}`")

            # 只对SELECT语句执行EXPLAIN
            if not sql.strip().upper().startswith('SELECT'):
                return {}

            cursor.execute(f"EXPLAIN {sql}")
            explain_rows = cursor.fetchall()

            total_rows = 0
            indexes = []
            has_full_scan = False
            plan = []

            for row in explain_rows:
                total_rows += row.get('rows', 0) or 0

                key = row.get('key')
                if key:
                    indexes.append(key)

                if row.get('type') in ('ALL', 'index'):
                    has_full_scan = True

                plan.append({
                    'table': row.get('table'),
                    'type': row.get('type'),
                    'possible_keys': row.get('possible_keys'),
                    'key': key,
                    'rows': row.get('rows'),
                    'Extra': row.get('Extra')
                })

            return {
                'rows_examined': total_rows,
                'indexes_used': ','.join(indexes) if indexes else 'NONE',
                'has_full_scan': has_full_scan,
                'plan': plan
            }

        except Exception as e:
            logger.debug(f"获取执行计划失败: {e}")
            return {}

    def check_deadlocks(self) -> List[Dict]:
        """检测死锁"""
        conn = self.connect()
        if not conn:
            return []

        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW ENGINE INNODB STATUS")
                result = cursor.fetchone()

                if not result:
                    return []

                status_text = result.get('Status', '')

                # 解析死锁信息
                deadlocks = self.parse_deadlock_from_status(status_text)

                return deadlocks

        except Exception as e:
            logger.error(f"检测死锁失败 {self.instance_name}: {e}")
            return []
        finally:
            conn.close()

    def parse_deadlock_from_status(self, status_text: str) -> List[Dict]:
        """从INNODB STATUS解析死锁信息"""
        deadlocks = []

        # 查找最近的死锁
        deadlock_match = re.search(
            r'LATEST DETECTED DEADLOCK\s*\n-+\s*\n(.*?)(?=\n-{5,}|\Z)',
            status_text,
            re.DOTALL | re.IGNORECASE
        )

        if not deadlock_match:
            return deadlocks

        deadlock_section = deadlock_match.group(1)

        # 提取时间
        time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', deadlock_section)
        deadlock_time = time_match.group(1) if time_match else None

        # 提取事务信息 (支持两种格式)
        # 格式1: 带 "query:" 标记
        transactions = re.findall(
            r'TRANSACTION\s+(\d+).*?(?:query|SQL):\s*(.+?)(?=\*\*\*|\Z)',
            deadlock_section,
            re.DOTALL | re.IGNORECASE
        )

        # 格式2: SQL直接在thread info后面 (如果格式1没找到)
        if not transactions:
            transactions = re.findall(
                r'TRANSACTION\s+(\d+).*?MySQL thread id \d+.*?\n(.+?)(?=\*\*\*|RECORD LOCKS|\Z)',
                deadlock_section,
                re.DOTALL | re.IGNORECASE
            )

        if len(transactions) >= 2:
            # 提取第一个事务(受害者)的详细信息
            victim_info = self.extract_transaction_info(deadlock_section, transactions[0][0])
            # 提取第二个事务(阻塞者)的详细信息
            blocker_info = self.extract_transaction_info(deadlock_section, transactions[1][0])

            deadlock = {
                'db_instance_id': self.instance_id,
                'deadlock_time': deadlock_time or datetime.now(),
                'victim_trx_id': transactions[0][0],
                'victim_session_id': victim_info.get('session_id'),
                'victim_sql': transactions[0][1].strip()[:1000],
                'blocker_trx_id': transactions[1][0],
                'blocker_session_id': blocker_info.get('session_id'),
                'blocker_sql': transactions[1][1].strip()[:1000],
                'deadlock_graph': json.dumps({
                    'raw': deadlock_section[:2000],
                    'victim_user': victim_info.get('username'),
                    'victim_host': victim_info.get('host'),
                    'blocker_user': blocker_info.get('username'),
                    'blocker_host': blocker_info.get('host'),
                    'database': victim_info.get('database') or blocker_info.get('database')
                }),
                'wait_resource': self.extract_wait_resource(deadlock_section),
                'lock_mode': self.extract_lock_mode(deadlock_section),
                'resolved_action': 'ROLLBACK',
                'detect_time': datetime.now()
            }

            deadlocks.append(deadlock)

        return deadlocks

    def extract_transaction_info(self, text: str, trx_id: str) -> Dict:
        """提取事务详细信息（session_id, username, host, database）"""
        info = {'session_id': None, 'username': None, 'host': None, 'database': None}

        # 查找包含该事务ID的部分
        trx_pattern = rf'TRANSACTION\s+{trx_id}.*?(?=TRANSACTION|\*\*\*|\Z)'
        trx_match = re.search(trx_pattern, text, re.DOTALL | re.IGNORECASE)

        if trx_match:
            trx_section = trx_match.group(0)

            # 提取 MySQL thread id (session_id)
            session_match = re.search(r'MySQL thread id\s+(\d+)', trx_section, re.IGNORECASE)
            if session_match:
                info['session_id'] = session_match.group(1)

            # 提取 host 和 username
            # 格式: query id 518674612 192.168.47.41 yzc_soft updating
            user_match = re.search(r'query id \d+\s+([\d\.]+)\s+(\w+)', trx_section)
            if user_match:
                info['host'] = user_match.group(1)
                info['username'] = user_match.group(2)

        # 从整个死锁文本中提取数据库名（从table信息中）
        # 格式: of table `database`.`table_name`
        db_match = re.search(r'of table\s+`([^`]+)`\.`([^`]+)`', text, re.IGNORECASE)
        if db_match:
            info['database'] = db_match.group(1)

        return info

    def extract_wait_resource(self, text: str) -> str:
        """提取等待资源"""
        # 尝试多种格式
        # 格式1: waiting for ... lock on table_name
        match = re.search(r'waiting for.*?lock on\s+(.+)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # 格式2: index PRIMARY of table `database`.`table_name`
        match = re.search(r'index\s+\w+\s+of table\s+`([^`]+)`\.`([^`]+)`', text, re.IGNORECASE)
        if match:
            return f'{match.group(1)}.{match.group(2)}'

        # 格式3: of table `table_name`
        match = re.search(r'of table\s+`([^`]+)`', text, re.IGNORECASE)
        if match:
            return match.group(1)

        return ''

    def extract_lock_mode(self, text: str) -> str:
        """提取锁模式"""
        match = re.search(r'lock_mode\s+(\w+)', text, re.IGNORECASE)
        return match.group(1) if match else ''


def should_send_alert(monitor_conn: pymysql.Connection, instance_id: int, alert_type: str, identifier: str, interval_minutes: int = 30) -> bool:
    """
    检查是否应该发送告警（避免重复告警）

    Args:
        monitor_conn: 监控数据库连接
        instance_id: 实例ID
        alert_type: 告警类型（slow_sql/deadlock）
        identifier: 标识符（SQL指纹或死锁时间）
        interval_minutes: 告警间隔（分钟）
    """
    try:
        with monitor_conn.cursor() as cursor:
            # 查询最近是否发送过相同告警
            cursor.execute("""
                SELECT MAX(created_at) as last_alert_time
                FROM alert_history
                WHERE db_instance_id = %s
                  AND alert_type = %s
                  AND alert_identifier = %s
                  AND created_at >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
            """, (instance_id, alert_type, identifier, interval_minutes))

            result = cursor.fetchone()
            # 如果没有记录或超过间隔时间，则可以发送告警
            return result['last_alert_time'] is None

    except Exception as e:
        logger.debug(f"检查告警间隔失败: {e}")
        return True  # 出错时默认允许发送


def save_alert_history(monitor_conn: pymysql.Connection, instance_id: int, identifier: str, alert_type: str, level: str, message: str) -> bool:
    """
    保存告警历史记录

    Args:
        monitor_conn: 监控数据库连接
        instance_id: 实例ID
        identifier: 标识符（SQL指纹或死锁时间）
        alert_type: 告警类型（slow_sql/deadlock）
        level: 告警级别（WARNING/CRITICAL）
        message: 告警消息
    """
    try:
        with monitor_conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO alert_history (
                    db_instance_id, alert_type, alert_identifier, alert_level, alert_message
                ) VALUES (%s, %s, %s, %s, %s)
            """, (instance_id, alert_type, identifier, level, message))

            monitor_conn.commit()
            return True

    except Exception as e:
        logger.error(f"保存告警历史失败: {e}")
        monitor_conn.rollback()
        return False


def save_slow_sqls(slow_sqls: List[Dict], monitor_conn: pymysql.Connection) -> int:
    """保存慢SQL到监控数据库"""
    if not slow_sqls:
        return 0

    try:
        with monitor_conn.cursor() as cursor:
            insert_query = """
            INSERT INTO long_running_sql_log (
                db_instance_id, session_id, sql_id, sql_fingerprint,
                sql_text, sql_fulltext, username, machine, program,
                elapsed_seconds, elapsed_minutes, status, isolation_level,
                rows_examined, rows_sent, execution_plan, index_used,
                full_table_scan, sql_exec_start, detect_time
            ) VALUES (
                %(db_instance_id)s, %(session_id)s, %(sql_id)s, %(sql_fingerprint)s,
                %(sql_text)s, %(sql_fulltext)s, %(username)s, %(machine)s, %(program)s,
                %(elapsed_seconds)s, %(elapsed_minutes)s, %(status)s, %(isolation_level)s,
                %(rows_examined)s, %(rows_sent)s, %(execution_plan)s, %(index_used)s,
                %(full_table_scan)s, %(sql_exec_start)s, %(detect_time)s
            )
            """

            cursor.executemany(insert_query, slow_sqls)
            monitor_conn.commit()

            return len(slow_sqls)

    except Exception as e:
        logger.error(f"保存慢SQL失败: {e}")
        monitor_conn.rollback()
        return 0


def save_deadlocks(deadlocks: List[Dict], monitor_conn: pymysql.Connection) -> int:
    """保存死锁信息到监控数据库（带去重）"""
    if not deadlocks:
        return 0

    try:
        with monitor_conn.cursor() as cursor:
            saved_count = 0

            for deadlock in deadlocks:
                # 去重检查：检查是否已存在相同的死锁记录
                # 根据：实例ID + 死锁时间 + 受害者SQL的前100字符
                cursor.execute("""
                    SELECT COUNT(*) as count FROM deadlock_log
                    WHERE db_instance_id = %s
                      AND deadlock_time = %s
                      AND LEFT(victim_sql, 100) = %s
                """, (
                    deadlock['db_instance_id'],
                    deadlock['deadlock_time'],
                    deadlock['victim_sql'][:100]
                ))

                if cursor.fetchone()['count'] > 0:
                    logger.debug(f"跳过重复死锁: {deadlock['deadlock_time']}")
                    continue

                # 插入新的死锁记录
                insert_query = """
                INSERT INTO deadlock_log (
                    db_instance_id, deadlock_time,
                    victim_trx_id, victim_session_id, victim_sql,
                    blocker_trx_id, blocker_session_id, blocker_sql,
                    deadlock_graph, wait_resource, lock_mode,
                    resolved_action, detect_time
                ) VALUES (
                    %(db_instance_id)s, %(deadlock_time)s,
                    %(victim_trx_id)s, %(victim_session_id)s, %(victim_sql)s,
                    %(blocker_trx_id)s, %(blocker_session_id)s, %(blocker_sql)s,
                    %(deadlock_graph)s, %(wait_resource)s, %(lock_mode)s,
                    %(resolved_action)s, %(detect_time)s
                )
                """

                cursor.execute(insert_query, deadlock)
                saved_count += 1

            monitor_conn.commit()
            return saved_count

    except Exception as e:
        logger.error(f"保存死锁信息失败: {e}")
        monitor_conn.rollback()
        return 0


def collect_from_instance(instance: Dict, alert_manager: Optional[AlertManager]) -> Tuple[int, int]:
    """采集单个实例的数据"""
    instance_name = instance.get('db_project', 'Unknown')
    db_type = instance.get('db_type', 'MySQL')
    logger.info(f"开始采集实例: {instance_name} ({instance['db_ip']}:{instance.get('db_port', 3306)}) - {db_type}")

    try:
        # 根据数据库类型选择采集器
        if db_type == 'SQLServer':
            if not PYODBC_AVAILABLE:
                logger.warning(f"跳过SQL Server实例 {instance_name}: pyodbc未安装")
                return 0, 0
            collector = SQLServerCollector(instance)
            slow_sqls = collector.collect_running_queries(LONG_SQL_THRESHOLD_SECONDS)
            deadlocks = collector.check_deadlocks()
        else:  # MySQL, Oracle, PostgreSQL
            collector = MySQLCollector(instance, alert_manager)
            slow_sqls = collector.collect_running_queries()
            deadlocks = collector.check_deadlocks()

        # 保存到监控数据库
        monitor_conn = pymysql.connect(**MONITOR_DB_CONFIG)

        sql_count = save_slow_sqls(slow_sqls, monitor_conn)
        deadlock_count = save_deadlocks(deadlocks, monitor_conn)

        monitor_conn.close()

        # 发送告警（带历史记录和间隔控制）
        if alert_manager:
            monitor_conn_for_alert = pymysql.connect(**MONITOR_DB_CONFIG)

            # 慢SQL告警
            for slow_sql in slow_sqls:
                if slow_sql['elapsed_minutes'] >= ALERT_THRESHOLD_MINUTES:
                    # 检查是否需要发送告警（控制告警间隔）
                    if should_send_alert(monitor_conn_for_alert, instance['id'], 'slow_sql', slow_sql.get('sql_fingerprint')):
                        slow_sql_info = {
                            **slow_sql,
                            'instance_name': instance_name,
                            'db_ip': instance['db_ip'],
                            'db_port': instance.get('db_port', 3306)
                        }

                        # 发送告警
                        if alert_manager.send_slow_sql_alert(slow_sql_info, ALERT_THRESHOLD_MINUTES):
                            # 记录告警历史
                            save_alert_history(
                                monitor_conn_for_alert,
                                instance['id'],
                                slow_sql.get('sql_fingerprint'),
                                'slow_sql',
                                'WARNING' if slow_sql['elapsed_minutes'] < 30 else 'CRITICAL',
                                f"慢SQL告警: 执行时长 {slow_sql['elapsed_minutes']:.2f} 分钟"
                            )

            # 死锁告警(立即发送)
            for deadlock in deadlocks:
                # 检查是否需要发送告警
                if should_send_alert(monitor_conn_for_alert, instance['id'], 'deadlock', deadlock.get('deadlock_time')):
                    deadlock_info = {
                        **deadlock,
                        'instance_name': instance_name,
                        'db_ip': instance['db_ip'],
                        'db_port': instance.get('db_port', 3306),
                        'db_type': 'MySQL'
                    }

                    # 发送告警
                    if alert_manager.send_deadlock_alert(deadlock_info):
                        # 记录告警历史
                        save_alert_history(
                            monitor_conn_for_alert,
                            instance['id'],
                            str(deadlock.get('deadlock_time')),
                            'deadlock',
                            'CRITICAL',
                            f"死锁告警: {deadlock.get('victim_sql', '')[:100]}"
                        )

            monitor_conn_for_alert.close()

        logger.info(f"采集完成: {instance_name} - 慢SQL:{sql_count}, 死锁:{deadlock_count}")

        return sql_count, deadlock_count

    except Exception as e:
        logger.error(f"采集实例失败 {instance_name}: {e}")
        return 0, 0


def get_active_instances() -> List[Dict]:
    """获取所有启用的监控实例"""
    try:
        conn = pymysql.connect(**MONITOR_DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, db_project, db_ip, db_port, db_type, db_user, db_password, instance_name
                FROM db_instance_info
                WHERE status = 1
                ORDER BY id
            """)
            instances = cursor.fetchall()
        conn.close()

        return instances

    except Exception as e:
        logger.error(f"获取实例列表失败: {e}")
        return []


def collect_all(alert_manager: Optional[AlertManager] = None):
    """采集所有实例"""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("开始新一轮采集")

    instances = get_active_instances()

    if not instances:
        logger.warning("没有找到启用的监控实例")
        return

    logger.info(f"找到 {len(instances)} 个启用的实例")

    total_sqls = 0
    total_deadlocks = 0

    # 并发采集
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(collect_from_instance, instance, alert_manager): instance
            for instance in instances
        }

        for future in as_completed(futures):
            try:
                sql_count, deadlock_count = future.result()
                total_sqls += sql_count
                total_deadlocks += deadlock_count
            except Exception as e:
                instance = futures[future]
                logger.error(f"实例采集异常 {instance.get('db_project')}: {e}")

    elapsed = time.time() - start_time
    logger.info(f"采集完成: 总计慢SQL {total_sqls} 条, 死锁 {total_deadlocks} 个, 耗时 {elapsed:.2f}秒")
    logger.info("=" * 60)

    return total_sqls, total_deadlocks


def run_daemon(interval: int = 10, alert_config: Optional[Dict] = None):
    """守护进程模式运行"""
    logger.info("=" * 60)
    logger.info("数据库监控采集器启动")
    logger.info(f"采集间隔: {interval} 秒")
    logger.info(f"慢SQL阈值: {LONG_SQL_THRESHOLD_SECONDS} 秒")
    logger.info(f"告警阈值: {ALERT_THRESHOLD_MINUTES} 分钟")
    logger.info("=" * 60)

    # 初始化告警管理器
    alert_manager = None
    if alert_config:
        alert_manager = AlertManager(alert_config)
        logger.info(f"告警通道已加载: {len(alert_manager.channels)} 个")

    while True:
        try:
            collect_all(alert_manager)
        except KeyboardInterrupt:
            logger.info("收到停止信号，退出...")
            break
        except Exception as e:
            logger.error(f"采集过程异常: {e}")

        logger.info(f"等待 {interval} 秒后进行下一次采集...")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='数据库监控采集器 - 增强版')
    parser.add_argument('--daemon', '-d', action='store_true', help='守护进程模式')
    parser.add_argument('--interval', '-i', type=int, default=10, help='采集间隔(秒), 默认10秒')
    parser.add_argument('--threshold', '-t', type=int, default=5, help='慢SQL阈值(秒), 默认5秒')
    parser.add_argument('--alert-threshold', '-a', type=int, default=1, help='告警阈值(分钟), 默认1分钟')
    parser.add_argument('--alert-config', type=str, default='alert_config.json', help='告警配置文件')

    args = parser.parse_args()

    global LONG_SQL_THRESHOLD_SECONDS, COLLECT_INTERVAL, ALERT_THRESHOLD_MINUTES
    LONG_SQL_THRESHOLD_SECONDS = args.threshold
    COLLECT_INTERVAL = args.interval
    ALERT_THRESHOLD_MINUTES = args.alert_threshold

    # 加载告警配置
    alert_config = None
    if os.path.exists(args.alert_config):
        alert_config = load_alert_config(args.alert_config)
        logger.info(f"加载告警配置: {args.alert_config}")
    else:
        logger.warning(f"告警配置文件不存在: {args.alert_config}")

    if args.daemon:
        run_daemon(args.interval, alert_config)
    else:
        collect_all(AlertManager(alert_config) if alert_config else None)


if __name__ == '__main__':
    main()
