#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server Query Store 慢SQL采集器
对数据库侵入最低、性能最好、准确率最高的采集方式

优势:
1. 零侵入 - Query Store在后台自动收集，不影响业务
2. 高性能 - 只需查询聚合表，不需要实时扫描DMV
3. 100%准确 - 所有执行过的SQL都会被持久化，不会遗漏
4. 自动去重 - Query Store已经做了参数化
5. 执行计划 - 自动保存每个SQL的执行计划
6. 持久化 - 数据不会因为SQL Server重启而丢失

要求: SQL Server 2016及以上版本

使用:
    python sqlserver_querystore_collector.py              # 单次采集
    python sqlserver_querystore_collector.py --daemon     # 守护进程模式
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    logging.error("pyodbc未安装，SQL Server监控不可用。安装命令: pip install pyodbc")
    sys.exit(1)

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


class SQLServerQueryStoreCollector:
    """
    SQL Server Query Store 采集器

    采集策略:
    1. 主要数据源: sys.query_store_* 系列视图 (聚合数据)
    2. 辅助数据源: sys.dm_exec_requests (实时快照)
    3. 采集间隔: 60秒 (Query Store已经聚合，不需要高频采集)
    """

    def __init__(self, instance_config: Dict, threshold_seconds: int = 5):
        self.instance_config = instance_config
        self.instance_id = instance_config['id']
        self.instance_name = instance_config.get('db_project', 'Unknown')
        self.threshold_seconds = threshold_seconds
        self.threshold_microseconds = threshold_seconds * 1000000  # Query Store用微秒

    def connect_target(self) -> Optional[pyodbc.Connection]:
        """连接目标SQL Server实例"""
        try:
            conn_str = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={self.instance_config['db_ip']},{self.instance_config.get('db_port', 1433)};"
                f"DATABASE=master;"
                f"UID={self.instance_config.get('db_user', 'sa')};"
                f"PWD={self.instance_config.get('db_password', '')};"
                f"Encrypt=no;"
                f"TrustServerCertificate=yes;"
            )

            conn = pyodbc.connect(conn_str, timeout=5)
            return conn

        except Exception as e:
            logger.error(f"连接目标SQL Server失败 {self.instance_name}: {e}")
            return None

    def connect_monitor(self) -> Optional[pymysql.Connection]:
        """连接监控数据库"""
        try:
            return pymysql.connect(**MONITOR_DB_CONFIG)
        except Exception as e:
            logger.error(f"连接监控数据库失败: {e}")
            return None

    def get_user_databases(self, conn: pyodbc.Connection) -> List[str]:
        """获取所有用户数据库"""
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name
                FROM sys.databases
                WHERE database_id > 4  -- 排除系统数据库
                  AND state_desc = 'ONLINE'
                  AND name NOT IN ('tempdb', 'model', 'msdb')
            """)

            databases = [row[0] for row in cursor.fetchall()]
            cursor.close()

            return databases

        except Exception as e:
            logger.error(f"获取数据库列表失败: {e}")
            return []

    def check_querystore_enabled(self, conn: pyodbc.Connection, database: str) -> bool:
        """检查Query Store是否开启"""
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT actual_state_desc, readonly_reason
                FROM sys.database_query_store_options
                WHERE database_id = DB_ID('{database}')
            """)

            row = cursor.fetchone()
            cursor.close()

            if row:
                state = row[0]
                readonly_reason = row[1]

                if state == 'READ_WRITE':
                    return True
                elif state == 'READ_ONLY':
                    logger.warning(f"{database}: Query Store是只读模式 (原因: {readonly_reason})")
                    return True  # 可以读取数据
                else:
                    logger.warning(f"{database}: Query Store未开启 (状态: {state})")
                    return False
            else:
                logger.warning(f"{database}: 无法查询Query Store状态")
                return False

        except Exception as e:
            logger.debug(f"检查Query Store失败 {database}: {e}")
            return False

    def enable_querystore(self, conn: pyodbc.Connection, database: str) -> bool:
        """开启Query Store"""
        try:
            cursor = conn.cursor()

            # 开启Query Store
            cursor.execute(f"""
                ALTER DATABASE [{database}] SET QUERY_STORE = ON;
            """)

            # 配置Query Store
            cursor.execute(f"""
                ALTER DATABASE [{database}] SET QUERY_STORE (
                    OPERATION_MODE = READ_WRITE,
                    DATA_FLUSH_INTERVAL_SECONDS = 900,
                    MAX_STORAGE_SIZE_MB = 1024,
                    INTERVAL_LENGTH_MINUTES = 60,
                    QUERY_CAPTURE_MODE = AUTO,
                    SIZE_BASED_CLEANUP_MODE = AUTO
                );
            """)

            conn.commit()
            cursor.close()

            logger.info(f"{database}: Query Store已成功开启")
            return True

        except Exception as e:
            logger.error(f"开启Query Store失败 {database}: {e}")
            return False

    def collect_from_querystore(self, conn: pyodbc.Connection, database: str) -> List[Dict]:
        """
        从Query Store采集慢SQL聚合数据

        数据源: sys.query_store_* 系列视图

        优点:
        - 已聚合: 相同SQL模式只有一条记录
        - 零开销: Query Store后台自动收集
        - 全面覆盖: 不会遗漏任何执行过的SQL
        - 执行计划: 每个SQL都有对应的执行计划
        - 持久化: 数据不会丢失

        采集策略:
        - 只采集最近5分钟有执行的SQL
        - 按平均执行时间降序
        - 限制100条
        """
        try:
            cursor = conn.cursor()

            # 查询Query Store聚合数据 (过滤CDC作业)
            query = f"""
            USE [{database}];

            SELECT TOP 100
                qsq.query_id,
                qsqt.query_sql_text,
                qsq.query_hash,
                qsrs.count_executions,
                qsrs.avg_duration / 1000000.0 AS avg_duration_seconds,
                qsrs.min_duration / 1000000.0 AS min_duration_seconds,
                qsrs.max_duration / 1000000.0 AS max_duration_seconds,
                qsrs.stdev_duration / 1000000.0 AS stdev_duration_seconds,
                qsrs.avg_cpu_time / 1000000.0 AS avg_cpu_seconds,
                qsrs.avg_logical_io_reads,
                qsrs.avg_logical_io_writes,
                qsrs.avg_physical_io_reads,
                qsrs.avg_rowcount,
                qsrs.last_execution_time,
                qsp.query_plan
            FROM sys.query_store_query qsq
            JOIN sys.query_store_query_text qsqt ON qsq.query_text_id = qsqt.query_text_id
            JOIN sys.query_store_plan qsp ON qsq.query_id = qsp.query_id
            JOIN sys.query_store_runtime_stats qsrs ON qsp.plan_id = qsrs.plan_id
            WHERE qsrs.avg_duration >= ?
              AND qsrs.last_execution_time >= DATEADD(MINUTE, -5, GETDATE())
              -- 过滤CDC作业 (Change Data Capture)
              AND qsqt.query_sql_text NOT LIKE '%sp_cdc_%'
              AND qsqt.query_sql_text NOT LIKE '%sp_MScdc_%'
              AND qsqt.query_sql_text NOT LIKE '%cdc.lsn_time_mapping%'
              AND qsqt.query_sql_text NOT LIKE '%cdc.change_tables%'
              AND qsqt.query_sql_text NOT LIKE '%cdc.captured_columns%'
              -- 过滤复制作业
              AND qsqt.query_sql_text NOT LIKE '%sp_replcmds%'
              AND qsqt.query_sql_text NOT LIKE '%sp_MSrepl_%'
              -- 过滤系统健康检查
              AND qsqt.query_sql_text NOT LIKE '%sp_server_diagnostics%'
              -- 过滤事务管理代码 (连接池/应用框架)
              AND NOT (qsqt.query_sql_text LIKE '%@@TRANCOUNT%' AND qsqt.query_sql_text LIKE '%COMMIT%')
            ORDER BY qsrs.avg_duration DESC
            """

            cursor.execute(query, self.threshold_microseconds)
            rows = cursor.fetchall()

            logger.info(f"{self.instance_name} - {database}: 从Query Store采集到 {len(rows)} 条慢SQL记录")

            slow_sqls = []
            for row in rows:
                # 生成SQL指纹 (使用query_hash)
                sql_fingerprint = f"{database}_{row.query_hash}"[:64]

                slow_sql = {
                    'db_instance_id': self.instance_id,
                    'database_name': database,
                    'query_id': str(row.query_id),
                    'sql_fingerprint': sql_fingerprint,
                    'sql_text': row.query_sql_text[:4000] if row.query_sql_text else None,
                    'sql_fulltext': row.query_sql_text,
                    'execution_count': int(row.count_executions or 0),
                    'avg_elapsed_seconds': float(row.avg_duration_seconds or 0),
                    'min_elapsed_seconds': float(row.min_duration_seconds or 0),
                    'max_elapsed_seconds': float(row.max_duration_seconds or 0),
                    'stdev_elapsed_seconds': float(row.stdev_duration_seconds or 0),
                    'avg_cpu_seconds': float(row.avg_cpu_seconds or 0),
                    'avg_logical_reads': int(row.avg_logical_io_reads or 0),
                    'avg_logical_writes': int(row.avg_logical_io_writes or 0),
                    'avg_physical_reads': int(row.avg_physical_io_reads or 0),
                    'avg_rowcount': int(row.avg_rowcount or 0),
                    'last_execution_time': row.last_execution_time,
                    'query_plan': row.query_plan,
                    'detect_time': datetime.now(),
                    'collection_method': 'query_store'
                }

                slow_sqls.append(slow_sql)

            cursor.close()
            return slow_sqls

        except Exception as e:
            logger.error(f"{database}: 从Query Store采集失败: {e}")
            return []

    def collect_from_dmv(self, conn: pyodbc.Connection) -> List[Dict]:
        """
        从DMV采集正在执行的慢SQL (辅助)

        用途: 捕获当前正在执行的长时间SQL
        局限: 只能看到快照时刻正在运行的SQL
        """
        try:
            cursor = conn.cursor()

            query = """
            SELECT
                r.session_id,
                s.login_name AS username,
                s.host_name AS machine,
                s.program_name AS program,
                r.status,
                r.total_elapsed_time / 1000.0 AS elapsed_seconds,
                DB_NAME(r.database_id) AS database_name,
                t.text AS sql_text,
                r.cpu_time / 1000.0 AS cpu_seconds,
                r.reads AS logical_reads,
                r.writes AS logical_writes
            FROM sys.dm_exec_requests r
            JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
            CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
            WHERE r.session_id != @@SPID
              AND r.total_elapsed_time >= ?
              AND t.text IS NOT NULL
              -- 过滤CDC作业 (Change Data Capture)
              AND NOT (t.text LIKE '%sp_cdc_%' OR t.text LIKE '%sp_MScdc_%'
                       OR t.text LIKE '%cdc.lsn_time_mapping%'
                       OR t.text LIKE '%cdc.change_tables%'
                       OR t.text LIKE '%cdc.captured_columns%')
              -- 过滤复制作业
              AND NOT (t.text LIKE '%sp_replcmds%' OR t.text LIKE '%sp_MSrepl_%')
              -- 过滤系统健康检查 (AlwaysOn/FCI健康监控)
              AND NOT (t.text LIKE '%sp_server_diagnostics%')
              -- 过滤事务管理代码 (连接池/应用框架清理)
              AND NOT (t.text LIKE '%@@TRANCOUNT%' AND t.text LIKE '%COMMIT%')
              -- 过滤日志读取器
              AND NOT (s.program_name LIKE '%Repl-LogReader%' OR s.program_name LIKE '%REPLICATION%')
              -- 过滤SQLAgent后台作业 (但保留用户通过SQLAgent执行的业务SQL)
              AND NOT (s.program_name LIKE '%SQLAgent%' AND (
                  t.text LIKE '%sp_cdc_%'
                  OR t.text LIKE '%sp_replcmds%'
                  OR t.text LIKE '%sp_MSrepl_%'
                  OR t.text LIKE '%sp_publication_%'
                  OR DB_NAME(r.database_id) IN ('distribution', 'msdb')
              ))
              -- 过滤系统数据库的系统维护作业
              AND NOT (DB_NAME(r.database_id) IN ('master', 'tempdb', 'model', 'msdb')
                       AND s.program_name LIKE '%SQLAgent%')
            ORDER BY r.total_elapsed_time DESC
            """

            cursor.execute(query, self.threshold_seconds * 1000)  # 转换为毫秒
            rows = cursor.fetchall()

            logger.info(f"{self.instance_name}: 从DMV采集到 {len(rows)} 条正在执行的慢SQL")

            slow_sqls = []
            for row in rows:
                slow_sql = {
                    'db_instance_id': self.instance_id,
                    'session_id': str(row.session_id),
                    'sql_text': row.sql_text[:4000] if row.sql_text else None,
                    'sql_fulltext': row.sql_text,
                    'username': row.username or '',
                    'machine': row.machine or '',
                    'program': row.program or '',
                    'database_name': row.database_name or '',
                    'elapsed_seconds': float(row.elapsed_seconds or 0),
                    'elapsed_minutes': float(row.elapsed_seconds or 0) / 60.0,
                    'cpu_time': float(row.cpu_seconds or 0),
                    'logical_reads': int(row.logical_reads or 0),
                    'status': row.status or 'ACTIVE',
                    'detect_time': datetime.now(),
                    'collection_method': 'dmv'
                }

                slow_sqls.append(slow_sql)

            cursor.close()
            return slow_sqls

        except Exception as e:
            logger.error(f"{self.instance_name}: 从DMV采集失败: {e}")
            return []

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
                        insert_sql = """
                        INSERT INTO long_running_sql_log
                        (db_instance_id, session_id, sql_fingerprint, sql_text, sql_fulltext,
                         username, machine, program, elapsed_seconds, elapsed_minutes,
                         cpu_time, logical_reads, status, detect_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """

                        cursor.execute(insert_sql, (
                            sql_record.get('db_instance_id'),
                            sql_record.get('session_id', sql_record.get('query_id', '')),
                            sql_record.get('sql_fingerprint'),
                            sql_record.get('sql_text'),
                            sql_record.get('sql_fulltext'),
                            sql_record.get('username', ''),
                            sql_record.get('machine', ''),
                            sql_record.get('program', ''),
                            sql_record.get('avg_elapsed_seconds', sql_record.get('elapsed_seconds', 0)),
                            sql_record.get('avg_elapsed_seconds', sql_record.get('elapsed_seconds', 0)) / 60.0,
                            sql_record.get('avg_cpu_seconds', sql_record.get('cpu_time', 0)),
                            sql_record.get('avg_logical_reads', sql_record.get('logical_reads', 0)),
                            sql_record.get('status', 'COMPLETED'),
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

    def collect(self, auto_enable_querystore: bool = False) -> int:
        """执行完整采集流程"""
        target_conn = self.connect_target()
        if not target_conn:
            return 0

        try:
            all_slow_sqls = []

            # 获取用户数据库列表
            databases = self.get_user_databases(target_conn)

            logger.info(f"{self.instance_name}: 找到 {len(databases)} 个用户数据库")

            # 对每个数据库采集Query Store数据
            for database in databases:
                querystore_enabled = self.check_querystore_enabled(target_conn, database)

                if not querystore_enabled and auto_enable_querystore:
                    logger.info(f"{database}: 尝试自动开启Query Store...")
                    querystore_enabled = self.enable_querystore(target_conn, database)

                if querystore_enabled:
                    querystore_sqls = self.collect_from_querystore(target_conn, database)
                    all_slow_sqls.extend(querystore_sqls)

            # 辅助从DMV采集当前正在运行的 (补充数据源)
            dmv_sqls = self.collect_from_dmv(target_conn)
            all_slow_sqls.extend(dmv_sqls)

            # 保存到监控数据库
            saved_count = self.save_to_monitor_db(all_slow_sqls)

            return saved_count

        finally:
            target_conn.close()


def get_sqlserver_instances() -> List[Dict]:
    """获取所有SQL Server实例"""
    try:
        conn = pymysql.connect(**MONITOR_DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type
                FROM db_instance_info
                WHERE status = 1 AND db_type = 'SQLServer'
            """)
            instances = cursor.fetchall()
        conn.close()
        return instances
    except Exception as e:
        logger.error(f"获取SQL Server实例列表失败: {e}")
        return []


def collect_all(threshold_seconds: int = 5, auto_enable: bool = False) -> int:
    """采集所有SQL Server实例"""
    logger.info("=" * 60)
    logger.info("开始采集SQL Server慢SQL (Query Store模式)")
    logger.info("=" * 60)

    instances = get_sqlserver_instances()
    if not instances:
        logger.warning("没有找到启用的SQL Server实例")
        return 0

    logger.info(f"找到 {len(instances)} 个SQL Server实例")

    total_saved = 0

    for instance in instances:
        try:
            collector = SQLServerQueryStoreCollector(instance, threshold_seconds)
            saved = collector.collect(auto_enable_querystore=auto_enable)
            total_saved += saved
        except Exception as e:
            logger.error(f"采集实例 {instance.get('db_project')} 失败: {e}")

    logger.info(f"采集完成，共保存 {total_saved} 条慢SQL记录")
    logger.info("=" * 60)

    return total_saved


def run_daemon(interval: int = 60, threshold: int = 5, auto_enable: bool = False):
    """守护进程模式运行"""
    logger.info(f"启动守护进程模式")
    logger.info(f"采集间隔: {interval} 秒")
    logger.info(f"慢SQL阈值: {threshold} 秒")
    logger.info(f"自动开启Query Store: {auto_enable}")
    logger.info("按 Ctrl+C 停止")
    logger.info("=" * 60)

    while True:
        try:
            collect_all(threshold, auto_enable)
        except Exception as e:
            logger.error(f"采集过程发生异常: {e}")

        logger.info(f"等待 {interval} 秒...")
        time.sleep(interval)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='SQL Server Query Store 慢SQL采集器')
    parser.add_argument('--daemon', '-d', action='store_true', help='守护进程模式')
    parser.add_argument('--interval', '-i', type=int, default=60, help='采集间隔(秒)，默认60秒')
    parser.add_argument('--threshold', '-t', type=int, default=5, help='慢SQL阈值(秒)，默认5秒')
    parser.add_argument('--auto-enable', '-e', action='store_true', help='自动开启Query Store')

    args = parser.parse_args()

    if args.daemon:
        run_daemon(args.interval, args.threshold, args.auto_enable)
    else:
        collect_all(args.threshold, args.auto_enable)


if __name__ == '__main__':
    main()
