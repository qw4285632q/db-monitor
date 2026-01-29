#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server死锁检测器
使用Extended Events检测和采集死锁信息
"""

import pyodbc
import pymysql
import json
import logging
from datetime import datetime
from typing import List, Dict
import xml.etree.ElementTree as ET

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SQLServerDeadlockCollector:
    """SQL Server死锁采集器"""

    def __init__(self, instance_id: int, instance_name: str, host: str, port: int,
                 user: str, password: str, monitor_db_config: dict):
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.monitor_db_config = monitor_db_config

    def connect_sqlserver(self) -> pyodbc.Connection:
        """连接SQL Server"""
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.host},{self.port};"
            f"UID={self.user};"
            f"PWD={self.password};"
            f"TrustServerCertificate=yes;"
            f"Timeout=30;"
        )
        return pyodbc.connect(conn_str)

    def connect_monitor_db(self) -> pymysql.Connection:
        """连接监控数据库"""
        return pymysql.connect(
            host=self.monitor_db_config['host'],
            port=self.monitor_db_config['port'],
            user=self.monitor_db_config['user'],
            password=self.monitor_db_config['password'],
            database=self.monitor_db_config['database'],
            charset=self.monitor_db_config.get('charset', 'utf8mb4'),
            cursorclass=pymysql.cursors.DictCursor
        )

    def ensure_deadlock_session(self, conn: pyodbc.Connection) -> bool:
        """
        确保Extended Events会话存在
        如果不存在则创建
        """
        cursor = conn.cursor()

        try:
            # 检查会话是否存在
            check_query = """
            SELECT COUNT(*) as cnt
            FROM sys.server_event_sessions
            WHERE name = 'DeadlockMonitor'
            """
            cursor.execute(check_query)
            row = cursor.fetchone()

            if row.cnt > 0:
                # 会话已存在，检查是否运行
                check_running = """
                SELECT COUNT(*) as cnt
                FROM sys.dm_xe_sessions
                WHERE name = 'DeadlockMonitor'
                """
                cursor.execute(check_running)
                running_row = cursor.fetchone()

                if running_row.cnt == 0:
                    # 会话存在但未运行，启动它
                    logger.info(f"{self.instance_name} - 启动死锁监控会话")
                    cursor.execute("ALTER EVENT SESSION DeadlockMonitor ON SERVER STATE = START")
                    conn.commit()

                return True

            # 会话不存在，创建它
            logger.info(f"{self.instance_name} - 创建死锁监控Extended Events会话")

            create_session = """
            CREATE EVENT SESSION DeadlockMonitor ON SERVER
            ADD EVENT sqlserver.xml_deadlock_report
            ADD TARGET package0.ring_buffer
            (
                SET max_memory = 4096  -- 4MB
            )
            WITH (
                MAX_MEMORY = 4096 KB,
                EVENT_RETENTION_MODE = ALLOW_SINGLE_EVENT_LOSS,
                MAX_DISPATCH_LATENCY = 5 SECONDS,
                STARTUP_STATE = ON
            )
            """
            cursor.execute(create_session)
            conn.commit()

            # 启动会话
            cursor.execute("ALTER EVENT SESSION DeadlockMonitor ON SERVER STATE = START")
            conn.commit()

            logger.info(f"{self.instance_name} - 死锁监控会话已创建并启动")
            return True

        except Exception as e:
            logger.error(f"{self.instance_name} - 创建/启动死锁监控会话失败: {e}")
            return False
        finally:
            cursor.close()

    def collect_deadlocks(self) -> List[Dict]:
        """
        从Extended Events采集死锁数据
        """
        deadlocks = []

        try:
            conn = self.connect_sqlserver()

            # 确保死锁监控会话存在并运行
            if not self.ensure_deadlock_session(conn):
                logger.warning(f"{self.instance_name} - 无法启动死锁监控会话")
                conn.close()
                return deadlocks

            cursor = conn.cursor()

            # 从ring_buffer读取死锁数据
            query = """
            SELECT
                CAST(xet.target_data AS XML) as target_data
            FROM sys.dm_xe_session_targets xet
            JOIN sys.dm_xe_sessions xes ON xes.address = xet.event_session_address
            WHERE xes.name = 'DeadlockMonitor'
              AND xet.target_name = 'ring_buffer'
            """

            cursor.execute(query)
            row = cursor.fetchone()

            if not row or not row.target_data:
                logger.info(f"{self.instance_name} - 没有检测到死锁事件")
                cursor.close()
                conn.close()
                return deadlocks

            # 解析XML数据
            target_data_xml = row.target_data

            try:
                root = ET.fromstring(target_data_xml)

                # 查找所有死锁事件
                for event in root.findall(".//event[@name='xml_deadlock_report']"):
                    try:
                        deadlock_info = self.parse_deadlock_event(event)
                        if deadlock_info:
                            deadlocks.append(deadlock_info)
                    except Exception as e:
                        logger.error(f"{self.instance_name} - 解析死锁事件失败: {e}")
                        continue

            except ET.ParseError as e:
                logger.error(f"{self.instance_name} - XML解析失败: {e}")

            cursor.close()
            conn.close()

            logger.info(f"{self.instance_name} - 采集到 {len(deadlocks)} 个死锁事件")

        except Exception as e:
            logger.error(f"{self.instance_name} - 采集死锁失败: {e}")

        return deadlocks

    def parse_deadlock_event(self, event: ET.Element) -> Dict:
        """解析单个死锁事件"""
        try:
            # 获取时间戳
            timestamp_elem = event.find(".//data[@name='timestamp']")
            if timestamp_elem is not None:
                timestamp = timestamp_elem.find('value').text
                deadlock_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                deadlock_time = datetime.now()

            # 获取死锁XML
            deadlock_xml_elem = event.find(".//data[@name='xml_report']")
            if deadlock_xml_elem is None:
                return None

            deadlock_xml = deadlock_xml_elem.find('value').text

            # 解析死锁图
            deadlock_info = self.parse_deadlock_graph(deadlock_xml)
            deadlock_info['deadlock_time'] = deadlock_time
            deadlock_info['deadlock_xml'] = deadlock_xml

            return deadlock_info

        except Exception as e:
            logger.error(f"解析死锁事件失败: {e}")
            return None

    def parse_deadlock_graph(self, deadlock_xml: str) -> Dict:
        """解析死锁图XML，提取关键信息"""
        try:
            root = ET.fromstring(deadlock_xml)

            info = {
                'victim_spid': None,
                'process_count': 0,
                'resource_list': [],
                'process_list': []
            }

            # 获取受害者进程
            victim_elem = root.find(".//victimProcess")
            if victim_elem is not None:
                info['victim_spid'] = victim_elem.get('id', 'unknown')

            # 解析进程列表
            for process in root.findall(".//process-list/process"):
                process_info = {
                    'spid': process.get('id'),
                    'hostname': process.get('hostname'),
                    'loginname': process.get('loginname'),
                    'isolationlevel': process.get('isolationlevel'),
                    'status': process.get('status'),
                    'sql_text': ''
                }

                # 获取SQL文本
                input_buf = process.find('.//inputbuf')
                if input_buf is not None and input_buf.text:
                    process_info['sql_text'] = input_buf.text.strip()

                info['process_list'].append(process_info)
                info['process_count'] += 1

            # 解析资源列表
            for resource in root.findall(".//resource-list/*"):
                resource_info = {
                    'resource_type': resource.tag,
                    'database_name': resource.get('dbname', 'unknown'),
                    'object_name': resource.get('objectname', ''),
                    'index_name': resource.get('indexname', '')
                }
                info['resource_list'].append(resource_info)

            return info

        except ET.ParseError as e:
            logger.error(f"死锁图XML解析失败: {e}")
            return {
                'victim_spid': None,
                'process_count': 0,
                'resource_list': [],
                'process_list': []
            }

    def save_to_monitor_db(self, deadlocks: List[Dict]) -> int:
        """保存死锁记录到监控数据库"""
        if not deadlocks:
            return 0

        saved_count = 0

        try:
            monitor_conn = self.connect_monitor_db()
            cursor = monitor_conn.cursor()

            for deadlock in deadlocks:
                try:
                    # 检查是否已存在（根据时间和victim_spid去重）
                    check_query = """
                    SELECT COUNT(*) as cnt FROM deadlock_log
                    WHERE db_instance_id = %s
                      AND deadlock_time = %s
                      AND victim_spid = %s
                    """
                    cursor.execute(check_query, (
                        self.instance_id,
                        deadlock['deadlock_time'],
                        deadlock.get('victim_spid')
                    ))

                    if cursor.fetchone()['cnt'] > 0:
                        logger.debug(f"{self.instance_name} - 死锁记录已存在，跳过")
                        continue

                    # 插入死锁记录
                    insert_query = """
                    INSERT INTO deadlock_log
                    (db_instance_id, deadlock_time, victim_spid, process_count,
                     victim_sql, deadlock_xml, deadlock_graph, detect_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    """

                    # 获取受害者SQL
                    victim_sql = ''
                    if deadlock.get('victim_spid'):
                        for proc in deadlock.get('process_list', []):
                            if proc.get('spid') == deadlock['victim_spid']:
                                victim_sql = proc.get('sql_text', '')[:2000]
                                break

                    # 构建死锁图JSON
                    deadlock_graph = {
                        'victim_spid': deadlock.get('victim_spid'),
                        'process_count': deadlock.get('process_count', 0),
                        'processes': deadlock.get('process_list', []),
                        'resources': deadlock.get('resource_list', [])
                    }

                    cursor.execute(insert_query, (
                        self.instance_id,
                        deadlock['deadlock_time'],
                        deadlock.get('victim_spid'),
                        deadlock.get('process_count', 0),
                        victim_sql,
                        deadlock.get('deadlock_xml', '')[:10000],  # 限制大小
                        json.dumps(deadlock_graph, ensure_ascii=False)
                    ))

                    saved_count += 1

                except Exception as e:
                    logger.error(f"{self.instance_name} - 保存死锁记录失败: {e}")
                    continue

            monitor_conn.commit()
            cursor.close()
            monitor_conn.close()

            logger.info(f"{self.instance_name} - 保存了 {saved_count} 条新死锁记录")

        except Exception as e:
            logger.error(f"{self.instance_name} - 保存死锁到监控数据库失败: {e}")

        return saved_count

    def run(self):
        """执行死锁采集"""
        logger.info(f"{self.instance_name} - 开始死锁检测")

        try:
            # 采集死锁
            deadlocks = self.collect_deadlocks()

            # 保存到监控数据库
            if deadlocks:
                saved_count = self.save_to_monitor_db(deadlocks)
                logger.info(f"{self.instance_name} - 死锁检测完成，新增 {saved_count} 条记录")
            else:
                logger.info(f"{self.instance_name} - 未检测到死锁")

        except Exception as e:
            logger.error(f"{self.instance_name} - 死锁检测失败: {e}")


def collect_all_sqlserver_deadlocks(monitor_db_config: dict):
    """采集所有SQL Server实例的死锁"""
    try:
        # 连接监控数据库
        conn = pymysql.connect(
            host=monitor_db_config['host'],
            port=monitor_db_config['port'],
            user=monitor_db_config['user'],
            password=monitor_db_config['password'],
            database=monitor_db_config['database'],
            charset=monitor_db_config.get('charset', 'utf8mb4'),
            cursorclass=pymysql.cursors.DictCursor
        )

        cursor = conn.cursor()

        # 获取所有启用的SQL Server实例
        cursor.execute("""
            SELECT id, instance_name, db_ip, db_port, db_user, db_password
            FROM db_instance_info
            WHERE status = 1 AND db_type = 'SQL Server'
        """)

        instances = cursor.fetchall()
        cursor.close()
        conn.close()

        logger.info(f"找到 {len(instances)} 个SQL Server实例需要检测死锁")

        for instance in instances:
            try:
                collector = SQLServerDeadlockCollector(
                    instance_id=instance['id'],
                    instance_name=instance['instance_name'] or f"{instance['db_ip']}:{instance['db_port']}",
                    host=instance['db_ip'],
                    port=instance['db_port'],
                    user=instance['db_user'],
                    password=instance['db_password'],
                    monitor_db_config=monitor_db_config
                )

                collector.run()

            except Exception as e:
                logger.error(f"实例 {instance.get('instance_name')} 死锁检测失败: {e}")
                continue

    except Exception as e:
        logger.error(f"采集死锁失败: {e}")


if __name__ == '__main__':
    import json

    # 加载配置
    with open('../config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 执行采集
    collect_all_sqlserver_deadlocks(config['database'])
