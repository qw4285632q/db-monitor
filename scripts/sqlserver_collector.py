#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server 监控采集器
支持慢SQL和死锁监控
"""

import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    logging.warning("pyodbc未安装，SQL Server监控功能不可用。请运行: pip install pyodbc")

logger = logging.getLogger(__name__)


class SQLServerCollector:
    """SQL Server采集器"""

    def __init__(self, instance_config: Dict):
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc模块未安装")

        self.instance_config = instance_config
        self.instance_id = instance_config['id']
        self.instance_name = instance_config.get('db_project', 'Unknown')

    def connect(self) -> Optional[pyodbc.Connection]:
        """连接SQL Server"""
        try:
            # 构建连接字符串
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
            logger.error(f"连接SQL Server失败 {self.instance_name}: {e}")
            return None

    def collect_running_queries(self, threshold_seconds: int = 60) -> List[Dict]:
        """采集正在运行的慢SQL"""
        conn = self.connect()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            query = """
            SELECT
                r.session_id,
                s.login_name as username,
                s.host_name as machine,
                s.program_name as program,
                r.status,
                r.command,
                r.cpu_time / 1000.0 as cpu_time_sec,
                r.total_elapsed_time / 1000.0 as elapsed_seconds,
                DB_NAME(r.database_id) as database_name,
                t.text as sql_text,
                r.blocking_session_id,
                r.wait_type,
                r.wait_time / 1000.0 as wait_time_sec,
                r.wait_resource,
                r.reads,
                r.writes,
                r.logical_reads,
                r.row_count as rows_sent,
                qp.query_plan
            FROM sys.dm_exec_requests r
            CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
            LEFT JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
            OUTER APPLY sys.dm_exec_query_plan(r.plan_handle) qp
            WHERE r.session_id != @@SPID
              AND r.total_elapsed_time > ?
              AND t.text IS NOT NULL
              AND t.text NOT LIKE '%sp_server_diagnostics%'
              AND t.text NOT LIKE '%sp_cdc_%'
              AND (s.program_name NOT LIKE '%SQLAgent%' OR s.program_name IS NULL)
            ORDER BY r.total_elapsed_time DESC
            """

            cursor.execute(query, threshold_seconds * 1000)  # 转换为毫秒
            rows = cursor.fetchall()

            slow_sqls = []
            for row in rows:
                sql_text = row.sql_text or ''
                elapsed_seconds = row.elapsed_seconds or 0

                # 解析执行计划
                plan_info = self.parse_query_plan(row.query_plan)

                slow_sql = {
                    'db_instance_id': self.instance_id,
                    'session_id': str(row.session_id),
                    'sql_text': sql_text[:4000] if len(sql_text) > 4000 else sql_text,
                    'sql_fulltext': sql_text,
                    'username': row.username or '',
                    'machine': row.machine or '',
                    'program': row.program or '',
                    'elapsed_seconds': float(elapsed_seconds),
                    'elapsed_minutes': float(elapsed_seconds) / 60.0,
                    'cpu_time': row.cpu_time_sec or 0,
                    'wait_time': row.wait_time_sec or 0,
                    'wait_type': row.wait_type or '',
                    'wait_resource': row.wait_resource or '',
                    'logical_reads': row.logical_reads or 0,
                    'physical_reads': row.reads or 0,
                    'rows_sent': row.rows_sent or 0,
                    'status': row.status or 'ACTIVE',
                    'blocking_session': str(row.blocking_session_id) if row.blocking_session_id else None,
                    'rows_examined': plan_info.get('estimated_rows', 0),
                    'query_cost': plan_info.get('cost', 0),
                    'execution_plan': json.dumps(plan_info.get('plan', {})) if plan_info.get('plan') else None,
                    'index_used': plan_info.get('indexes_used', ''),
                    'full_table_scan': 1 if plan_info.get('has_scan') else 0,
                    'detect_time': datetime.now()
                }

                slow_sqls.append(slow_sql)

            cursor.close()
            return slow_sqls

        except Exception as e:
            logger.error(f"采集SQL Server慢SQL失败 {self.instance_name}: {e}")
            return []
        finally:
            conn.close()

    def parse_query_plan(self, query_plan_xml: Optional[str]) -> Dict:
        """解析SQL Server执行计划XML"""
        if not query_plan_xml:
            return {}

        try:
            root = ET.fromstring(query_plan_xml)
            ns = {'sp': 'http://schemas.microsoft.com/sqlserver/2004/07/showplan'}

            # 提取成本
            cost = 0
            cost_elem = root.find('.//sp:StmtSimple', ns)
            if cost_elem is not None:
                cost = float(cost_elem.get('StatementSubTreeCost', 0))

            # 提取预估行数
            estimated_rows = 0
            rows_elem = root.find('.//sp:StmtSimple', ns)
            if rows_elem is not None:
                estimated_rows = int(float(rows_elem.get('StatementEstRows', 0)))

            # 查找索引使用和扫描
            indexes = []
            has_scan = False

            for index_scan in root.findall('.//sp:IndexScan', ns):
                obj = index_scan.find('sp:Object', ns)
                if obj is not None:
                    index_name = obj.get('Index', '')
                    if index_name:
                        indexes.append(index_name)
                    if 'Scan' in index_scan.get('Type', ''):
                        has_scan = True

            for table_scan in root.findall('.//sp:TableScan', ns):
                has_scan = True

            return {
                'cost': cost,
                'estimated_rows': estimated_rows,
                'indexes_used': ','.join(indexes) if indexes else 'NONE',
                'has_scan': has_scan,
                'plan': {'cost': cost, 'rows': estimated_rows}
            }

        except Exception as e:
            logger.debug(f"解析执行计划失败: {e}")
            return {}

    def check_deadlocks(self) -> List[Dict]:
        """检测死锁 - 使用Extended Events"""
        conn = self.connect()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            # 查询Extended Events中的死锁记录
            query = """
            SELECT TOP 10
                CAST(event_data AS XML) as event_xml
            FROM sys.fn_xe_file_target_read_file(
                'system_health*.xel',
                NULL, NULL, NULL
            )
            WHERE object_name = 'xml_deadlock_report'
            ORDER BY file_name DESC, file_offset DESC
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            deadlocks = []
            for row in rows:
                deadlock_info = self.parse_deadlock_xml(str(row.event_xml))
                if deadlock_info:
                    deadlock_info['db_instance_id'] = self.instance_id
                    deadlocks.append(deadlock_info)

            cursor.close()
            return deadlocks

        except Exception as e:
            logger.error(f"检测SQL Server死锁失败 {self.instance_name}: {e}")
            return []
        finally:
            conn.close()

    def parse_deadlock_xml(self, xml_str: str) -> Optional[Dict]:
        """解析死锁XML"""
        try:
            root = ET.fromstring(xml_str)

            # 提取时间
            deadlock_time = root.find('.//timestamp')
            if deadlock_time is not None:
                deadlock_time = deadlock_time.text

            # 提取事务信息
            process_list = root.find('.//process-list')
            if process_list is None:
                return None

            processes = list(process_list.findall('process'))
            if len(processes) < 2:
                return None

            victim = processes[0]
            blocker = processes[1]

            # 提取SQL
            victim_sql_elem = victim.find('.//inputbuf')
            blocker_sql_elem = blocker.find('.//inputbuf')

            victim_sql = victim_sql_elem.text if victim_sql_elem is not None else ''
            blocker_sql = blocker_sql_elem.text if blocker_sql_elem is not None else ''

            # 提取资源信息
            resource_list = root.find('.//resource-list')
            wait_resource = ''
            lock_mode = ''
            if resource_list is not None:
                for resource in resource_list:
                    wait_resource = resource.get('objectname', '')
                    lock_mode = resource.get('mode', '')
                    break

            return {
                'deadlock_time': deadlock_time or datetime.now(),
                'victim_session_id': victim.get('id', ''),
                'victim_trx_id': victim.get('xactid', ''),
                'victim_sql': victim_sql[:1000],
                'blocker_session_id': blocker.get('id', ''),
                'blocker_trx_id': blocker.get('xactid', ''),
                'blocker_sql': blocker_sql[:1000],
                'wait_resource': wait_resource,
                'lock_mode': lock_mode,
                'resolved_action': 'ROLLBACK',
                'deadlock_graph': xml_str[:2000],
                'detect_time': datetime.now()
            }

        except Exception as e:
            logger.debug(f"解析死锁XML失败: {e}")
            return None

    def get_current_blocks(self) -> List[Dict]:
        """获取当前阻塞会话"""
        conn = self.connect()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            query = """
            SELECT
                blocked.session_id as blocked_session,
                blocked_sql.text as blocked_sql,
                blocking.session_id as blocking_session,
                blocking_sql.text as blocking_sql,
                blocked.wait_type,
                blocked.wait_time,
                blocked.wait_resource
            FROM sys.dm_exec_requests blocked
            CROSS APPLY sys.dm_exec_sql_text(blocked.sql_handle) blocked_sql
            LEFT JOIN sys.dm_exec_requests blocking
                ON blocked.blocking_session_id = blocking.session_id
            OUTER APPLY sys.dm_exec_sql_text(blocking.sql_handle) blocking_sql
            WHERE blocked.blocking_session_id > 0
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            blocks = []
            for row in rows:
                blocks.append({
                    'blocked_session': row.blocked_session,
                    'blocked_sql': row.blocked_sql,
                    'blocking_session': row.blocking_session,
                    'blocking_sql': row.blocking_sql,
                    'wait_type': row.wait_type,
                    'wait_time': row.wait_time,
                    'wait_resource': row.wait_resource
                })

            cursor.close()
            return blocks

        except Exception as e:
            logger.error(f"获取阻塞会话失败: {e}")
            return []
        finally:
            conn.close()

    def get_alwayson_status(self) -> List[Dict]:
        """获取Always On可用性组状态和延迟"""
        conn = self.connect()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            # 查询Always On可用性组和副本状态
            # 延迟计算说明：
            # - 使用日志发送队列大小和发送速率计算延迟
            # - 同步状态为SYNCHRONIZED且队列为0时，延迟为0
            # - 注意：estimate_recovery_time 和 secondary_lag_seconds 只在 SQL Server 2016+ 存在
            query = """
            SELECT
                ag.name as ag_name,
                ar.replica_server_name,
                ar.availability_mode_desc,
                ar.failover_mode_desc,
                ars.role_desc,
                ars.connected_state_desc,
                ars.synchronization_health_desc,
                DB_NAME(drs.database_id) as database_name,
                drs.synchronization_state_desc,
                drs.synchronization_health_desc,
                drs.log_send_queue_size,
                drs.log_send_rate,
                drs.redo_queue_size,
                drs.redo_rate,
                drs.last_commit_time,
                drs.last_hardened_time,
                drs.last_redone_time,
                drs.is_suspended,
                drs.suspend_reason_desc
            FROM sys.availability_groups ag
            INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
            INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
            LEFT JOIN sys.dm_hadr_database_replica_states drs ON ar.replica_id = drs.replica_id
            WHERE ars.is_local = 1
            ORDER BY ag.name, DB_NAME(drs.database_id)
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            alwayson_status = []
            for row in rows:
                # 计算延迟（秒）
                # 延迟计算策略：
                # 1. 如果同步状态为SYNCHRONIZED且日志队列和重做队列都为0 -> 延迟=0（完全同步）
                # 2. 如果有日志发送队列 -> 根据队列大小÷发送速率估算
                # 3. 如果有重做队列 -> 根据队列大小÷重做速率估算
                # 4. 否则延迟=0

                lag_seconds = 0

                # 完全同步状态
                if (row.synchronization_state_desc == 'SYNCHRONIZED' and
                    (not row.log_send_queue_size or row.log_send_queue_size == 0) and
                    (not row.redo_queue_size or row.redo_queue_size == 0)):
                    lag_seconds = 0

                # 根据日志发送队列估算延迟
                elif row.log_send_queue_size and row.log_send_queue_size > 0:
                    if row.log_send_rate and row.log_send_rate > 0:
                        # 队列大小(字节) ÷ 发送速率(字节/秒) = 延迟(秒)
                        lag_seconds = int(row.log_send_queue_size / row.log_send_rate)
                    else:
                        # 没有速率信息，假设网络速度10MB/s
                        lag_seconds = int(row.log_send_queue_size / (10 * 1024 * 1024))

                # 根据重做队列估算延迟
                elif row.redo_queue_size and row.redo_queue_size > 0:
                    if row.redo_rate and row.redo_rate > 0:
                        # 队列大小(字节) ÷ 重做速率(字节/秒) = 延迟(秒)
                        lag_seconds = int(row.redo_queue_size / row.redo_rate)
                    else:
                        # 没有速率信息，假设磁盘速度100MB/s
                        lag_seconds = int(row.redo_queue_size / (100 * 1024 * 1024))

                # SYNCHRONIZING状态且队列为0，延迟接近0
                else:
                    lag_seconds = 0

                # 判断健康状态
                is_healthy = (
                    row.synchronization_health_desc == 'HEALTHY' and
                    row.connected_state_desc == 'CONNECTED' and
                    not row.is_suspended
                )

                status = {
                    'db_instance_id': self.instance_id,
                    'ag_name': row.ag_name or '',
                    'replica_server': row.replica_server_name or '',
                    'availability_mode': row.availability_mode_desc or '',
                    'failover_mode': row.failover_mode_desc or '',
                    'role': row.role_desc or '',
                    'connected_state': row.connected_state_desc or '',
                    'sync_health': row.synchronization_health_desc or '',
                    'database_name': row.database_name or '',
                    'sync_state': row.synchronization_state_desc or '',
                    'db_sync_health': row.synchronization_health_desc or '',
                    'log_send_queue_kb': round((row.log_send_queue_size or 0) / 1024.0, 2),
                    'log_send_rate_kb': round((row.log_send_rate or 0) / 1024.0, 2),
                    'redo_queue_kb': round((row.redo_queue_size or 0) / 1024.0, 2),
                    'redo_rate_kb': round((row.redo_rate or 0) / 1024.0, 2),
                    'last_commit_time': row.last_commit_time,
                    'lag_seconds': lag_seconds,
                    'is_suspended': 1 if row.is_suspended else 0,
                    'suspend_reason': row.suspend_reason_desc or '',
                    'is_healthy': 1 if is_healthy else 0,
                    'check_time': datetime.now()
                }

                alwayson_status.append(status)

            cursor.close()
            return alwayson_status

        except Exception as e:
            logger.error(f"获取Always On状态失败 {self.instance_name}: {e}")
            return []
        finally:
            conn.close()


# 测试函数
if __name__ == '__main__':
    if not PYODBC_AVAILABLE:
        print("请先安装pyodbc: pip install pyodbc")
        exit(1)

    # 测试配置
    test_config = {
        'id': 1,
        'db_project': '测试SQL Server',
        'db_ip': '192.168.1.100',
        'db_port': 1433,
        'db_user': 'sa',
        'db_password': 'YourPassword'
    }

    collector = SQLServerCollector(test_config)

    print("测试连接...")
    conn = collector.connect()
    if conn:
        print("连接成功")
        conn.close()

    print("\n采集慢SQL...")
    slow_sqls = collector.collect_running_queries()
    print(f"找到 {len(slow_sqls)} 条慢SQL")

    print("\n检测死锁...")
    deadlocks = collector.check_deadlocks()
    print(f"找到 {len(deadlocks)} 个死锁")
