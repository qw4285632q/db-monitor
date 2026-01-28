#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prometheus客户端
用于查询Prometheus API获取MySQL监控指标
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Prometheus API客户端"""

    def __init__(self, url: str, timeout: int = 5):
        """
        初始化Prometheus客户端

        Args:
            url: Prometheus服务器URL (如: http://192.168.98.4:9090)
            timeout: 请求超时时间（秒）
        """
        self.url = url.rstrip('/')
        self.api_url = f"{self.url}/api/v1"
        self.timeout = timeout
        # 禁用代理（内网访问）
        self.proxies = {
            'http': None,
            'https': None
        }

    def query(self, promql: str) -> Optional[Dict]:
        """
        执行即时查询

        Args:
            promql: PromQL查询语句

        Returns:
            查询结果，失败返回None
        """
        try:
            response = requests.get(
                f"{self.api_url}/query",
                params={'query': promql},
                timeout=self.timeout,
                proxies=self.proxies
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Prometheus查询失败: {promql}, 错误: {e}")
            return None

    def query_range(self, promql: str, start: str, end: str, step: str = '15s') -> Optional[Dict]:
        """
        执行范围查询

        Args:
            promql: PromQL查询语句
            start: 起始时间（Unix时间戳或RFC3339格式）
            end: 结束时间
            step: 步长（如: 15s, 1m, 5m）

        Returns:
            查询结果，失败返回None
        """
        try:
            response = requests.get(
                f"{self.api_url}/query_range",
                params={
                    'query': promql,
                    'start': start,
                    'end': end,
                    'step': step
                },
                timeout=self.timeout * 2,  # 范围查询可能较慢
                proxies=self.proxies
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Prometheus范围查询失败: {promql}, 错误: {e}")
            return None

    def get_instance_metrics(self, instance_ip: str) -> Dict[str, Any]:
        """
        获取实例的关键指标

        Args:
            instance_ip: 实例IP地址

        Returns:
            包含各项指标的字典
        """
        metrics = {
            'instance_ip': instance_ip,
            'timestamp': datetime.now().isoformat()
        }

        # 1. 连接数指标
        conn_query = f'mysql_global_status_threads_connected{{ip="{instance_ip}"}}'
        metrics['connections'] = self._extract_value(self.query(conn_query))

        max_conn_query = f'mysql_global_variables_max_connections{{ip="{instance_ip}"}}'
        metrics['max_connections'] = self._extract_value(self.query(max_conn_query))

        # 计算连接使用率
        if metrics['connections'] is not None and metrics['max_connections'] is not None:
            metrics['connection_usage'] = round(
                (metrics['connections'] / metrics['max_connections']) * 100, 2
            )
        else:
            metrics['connection_usage'] = None

        # 活跃连接
        running_query = f'mysql_global_status_threads_running{{ip="{instance_ip}"}}'
        metrics['threads_running'] = self._extract_value(self.query(running_query))

        # 2. QPS/TPS指标
        qps_query = f'rate(mysql_global_status_questions{{ip="{instance_ip}"}}[1m])'
        metrics['qps'] = self._extract_value(self.query(qps_query))

        # TPS
        tps_query = f'''
        rate(mysql_global_status_commands_total{{command="commit",ip="{instance_ip}"}}[1m])
        + ignoring(command) rate(mysql_global_status_commands_total{{command="rollback",ip="{instance_ip}"}}[1m])
        '''
        metrics['tps'] = self._extract_value(self.query(tps_query))

        # 3. Buffer Pool指标
        # 命中率
        bp_hit_query = f'''
        (mysql_global_status_innodb_buffer_pool_read_requests{{ip="{instance_ip}"}}
        - mysql_global_status_innodb_buffer_pool_reads{{ip="{instance_ip}"}})
        / mysql_global_status_innodb_buffer_pool_read_requests{{ip="{instance_ip}"}} * 100
        '''
        metrics['buffer_pool_hit_rate'] = self._extract_value(self.query(bp_hit_query))

        # 使用率
        bp_usage_query = f'''
        mysql_global_status_innodb_buffer_pool_bytes_data{{ip="{instance_ip}"}}
        / mysql_global_variables_innodb_buffer_pool_size{{ip="{instance_ip}"}} * 100
        '''
        metrics['buffer_pool_usage'] = self._extract_value(self.query(bp_usage_query))

        # 脏页比例
        bp_dirty_query = f'''
        mysql_global_status_innodb_buffer_pool_pages_dirty{{ip="{instance_ip}"}}
        / mysql_global_status_innodb_buffer_pool_pages_total{{ip="{instance_ip}"}} * 100
        '''
        metrics['buffer_pool_dirty_pages'] = self._extract_value(self.query(bp_dirty_query))

        # 4. 复制延迟
        repl_lag_query = f'mysql_slave_status_seconds_behind_master{{ip="{instance_ip}"}}'
        metrics['replication_lag'] = self._extract_value(self.query(repl_lag_query))

        # 复制IO线程
        repl_io_query = f'mysql_slave_status_slave_io_running{{ip="{instance_ip}"}}'
        metrics['slave_io_running'] = self._extract_value(self.query(repl_io_query))

        # 复制SQL线程
        repl_sql_query = f'mysql_slave_status_slave_sql_running{{ip="{instance_ip}"}}'
        metrics['slave_sql_running'] = self._extract_value(self.query(repl_sql_query))

        # 5. 慢查询
        slow_query = f'rate(mysql_global_status_slow_queries{{ip="{instance_ip}"}}[5m])'
        metrics['slow_queries_rate'] = self._extract_value(self.query(slow_query))

        # 6. InnoDB行锁
        row_lock_waits_query = f'mysql_global_status_innodb_row_lock_waits{{ip="{instance_ip}"}}'
        metrics['innodb_row_lock_waits'] = self._extract_value(self.query(row_lock_waits_query))

        row_lock_time_query = f'mysql_global_status_innodb_row_lock_time_avg{{ip="{instance_ip}"}}'
        metrics['innodb_row_lock_time_avg'] = self._extract_value(self.query(row_lock_time_query))

        # 7. 表锁
        table_locks_waited_query = f'mysql_global_status_table_locks_waited{{ip="{instance_ip}"}}'
        metrics['table_locks_waited'] = self._extract_value(self.query(table_locks_waited_query))

        # 8. 临时表
        tmp_tables_query = f'rate(mysql_global_status_created_tmp_tables{{ip="{instance_ip}"}}[1m])'
        metrics['tmp_tables_rate'] = self._extract_value(self.query(tmp_tables_query))

        tmp_disk_tables_query = f'rate(mysql_global_status_created_tmp_disk_tables{{ip="{instance_ip}"}}[1m])'
        metrics['tmp_disk_tables_rate'] = self._extract_value(self.query(tmp_disk_tables_query))

        # 临时磁盘表比例
        if metrics['tmp_tables_rate'] and metrics['tmp_disk_tables_rate']:
            if metrics['tmp_tables_rate'] > 0:
                metrics['tmp_disk_tables_ratio'] = round(
                    (metrics['tmp_disk_tables_rate'] / metrics['tmp_tables_rate']) * 100, 2
                )
            else:
                metrics['tmp_disk_tables_ratio'] = 0
        else:
            metrics['tmp_disk_tables_ratio'] = None

        # 9. 磁盘IO
        io_reads_query = f'rate(mysql_global_status_innodb_data_reads{{ip="{instance_ip}"}}[1m])'
        metrics['innodb_data_reads_rate'] = self._extract_value(self.query(io_reads_query))

        io_writes_query = f'rate(mysql_global_status_innodb_data_writes{{ip="{instance_ip}"}}[1m])'
        metrics['innodb_data_writes_rate'] = self._extract_value(self.query(io_writes_query))

        # 10. 进程CPU使用率（需要process_exporter或node_exporter）
        cpu_query = f'rate(process_cpu_seconds_total{{ip="{instance_ip}"}}[5m]) * 100'
        metrics['cpu_usage'] = self._extract_value(self.query(cpu_query))

        # 11. 进程内存使用（字节）
        memory_query = f'process_resident_memory_bytes{{ip="{instance_ip}"}}'
        memory_bytes = self._extract_value(self.query(memory_query))
        if memory_bytes:
            metrics['memory_usage_mb'] = round(memory_bytes / 1024 / 1024, 2)
        else:
            metrics['memory_usage_mb'] = None

        return metrics

    def get_instance_trends(self, instance_ip: str, hours: int = 24) -> Dict[str, List]:
        """
        获取实例的趋势数据（用于绘制图表）

        Args:
            instance_ip: 实例IP
            hours: 查询最近N小时的数据

        Returns:
            包含趋势数据的字典
        """
        end = datetime.now()
        start = end - timedelta(hours=hours)

        trends = {}

        # QPS趋势
        qps_query = f'rate(mysql_global_status_questions{{ip="{instance_ip}"}}[1m])'
        qps_result = self.query_range(
            qps_query,
            start.isoformat(),
            end.isoformat(),
            step='1m'
        )
        trends['qps'] = self._extract_timeseries(qps_result)

        # 连接数趋势
        conn_query = f'mysql_global_status_threads_connected{{ip="{instance_ip}"}}'
        conn_result = self.query_range(
            conn_query,
            start.isoformat(),
            end.isoformat(),
            step='1m'
        )
        trends['connections'] = self._extract_timeseries(conn_result)

        # Buffer Pool命中率趋势
        bp_query = f'''
        (mysql_global_status_innodb_buffer_pool_read_requests{{ip="{instance_ip}"}}
        - mysql_global_status_innodb_buffer_pool_reads{{ip="{instance_ip}"}})
        / mysql_global_status_innodb_buffer_pool_read_requests{{ip="{instance_ip}"}} * 100
        '''
        bp_result = self.query_range(
            bp_query,
            start.isoformat(),
            end.isoformat(),
            step='5m'
        )
        trends['buffer_pool_hit_rate'] = self._extract_timeseries(bp_result)

        return trends

    def check_health(self) -> bool:
        """
        检查Prometheus服务是否可用

        Returns:
            True if健康, False otherwise
        """
        try:
            response = requests.get(f"{self.url}/-/healthy", timeout=2, proxies=self.proxies)
            return response.status_code == 200
        except:
            return False

    def get_targets(self) -> Optional[List[Dict]]:
        """
        获取所有监控目标

        Returns:
            目标列表
        """
        try:
            response = requests.get(f"{self.api_url}/targets", timeout=self.timeout, proxies=self.proxies)
            response.raise_for_status()
            result = response.json()
            if result['status'] == 'success':
                return result['data']['activeTargets']
            return None
        except Exception as e:
            logger.error(f"获取Prometheus targets失败: {e}")
            return None

    def _extract_value(self, response: Optional[Dict]) -> Optional[float]:
        """
        从Prometheus响应中提取单个值

        Args:
            response: Prometheus API响应

        Returns:
            提取的数值，失败返回None
        """
        try:
            if response and response.get('status') == 'success':
                result = response['data']['result']
                if result and len(result) > 0:
                    value = result[0]['value'][1]
                    return float(value)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.debug(f"提取值失败: {e}")
        return None

    def _extract_timeseries(self, response: Optional[Dict]) -> List[Dict]:
        """
        从Prometheus范围查询响应中提取时间序列

        Args:
            response: Prometheus API响应

        Returns:
            时间序列数据 [{'timestamp': ts, 'value': val}, ...]
        """
        timeseries = []
        try:
            if response and response.get('status') == 'success':
                result = response['data']['result']
                if result and len(result) > 0:
                    values = result[0]['values']
                    for timestamp, value in values:
                        timeseries.append({
                            'timestamp': timestamp,
                            'value': float(value)
                        })
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.debug(f"提取时间序列失败: {e}")
        return timeseries

    def get_sqlserver_instance_metrics(self, instance_ip: str) -> Dict[str, Any]:
        """
        获取SQL Server实例的关键指标

        Args:
            instance_ip: 实例IP地址

        Returns:
            包含各项指标的字典
        """
        metrics = {
            'instance_ip': instance_ip,
            'timestamp': datetime.now().isoformat(),
            'db_type': 'SQL Server'
        }

        # 1. 连接数指标 (SQL Server使用不同的metric名称)
        # 注意：SQL Server exporter的metric名称可能不同，需要根据实际情况调整
        conn_query = f'mssql_connections{{ip="{instance_ip}"}}'
        metrics['connections'] = self._extract_value(self.query(conn_query))

        max_conn_query = f'mssql_server_properties_max_connections{{ip="{instance_ip}"}}'
        metrics['max_connections'] = self._extract_value(self.query(max_conn_query))

        # 计算连接使用率
        if metrics['connections'] is not None and metrics['max_connections'] is not None:
            metrics['connection_usage'] = round(
                (metrics['connections'] / metrics['max_connections']) * 100, 2
            )
        else:
            metrics['connection_usage'] = None

        # 2. 批处理请求（类似于MySQL的QPS）
        batch_query = f'rate(mssql_batch_requests{{ip="{instance_ip}"}}[1m])'
        metrics['batch_requests'] = self._extract_value(self.query(batch_query))

        # 3. SQL编译数/秒
        compilations_query = f'rate(mssql_sql_compilations{{ip="{instance_ip}"}}[1m])'
        metrics['sql_compilations'] = self._extract_value(self.query(compilations_query))

        # 4. Buffer Pool命中率 (Buffer Cache Hit Ratio)
        buffer_hit_query = f'mssql_buffer_cache_hit_ratio{{ip="{instance_ip}"}}'
        metrics['buffer_cache_hit_ratio'] = self._extract_value(self.query(buffer_hit_query))

        # 5. 页面生命期望值 (Page Life Expectancy) - 越高越好
        ple_query = f'mssql_page_life_expectancy{{ip="{instance_ip}"}}'
        metrics['page_life_expectancy'] = self._extract_value(self.query(ple_query))

        # 6. 锁等待 (Lock Waits/sec)
        lock_waits_query = f'rate(mssql_lock_waits{{ip="{instance_ip}"}}[1m])'
        metrics['lock_waits_rate'] = self._extract_value(self.query(lock_waits_query))

        # 7. 死锁数/秒
        deadlocks_query = f'rate(mssql_deadlocks{{ip="{instance_ip}"}}[1m])'
        metrics['deadlocks_rate'] = self._extract_value(self.query(deadlocks_query))

        # 8. IO延迟 (IO Stall - 毫秒)
        io_stall_query = f'mssql_io_stall_seconds{{ip="{instance_ip}"}}'
        metrics['io_stall_seconds'] = self._extract_value(self.query(io_stall_query))

        # 9. 用户错误数/秒
        errors_query = f'rate(mssql_user_errors{{ip="{instance_ip}"}}[1m])'
        metrics['user_errors_rate'] = self._extract_value(self.query(errors_query))

        # 10. Always On 可用性组信息（如果有）
        # 同步状态
        ao_sync_query = f'mssql_ao_synchronization_health{{ip="{instance_ip}"}}'
        metrics['ao_sync_health'] = self._extract_value(self.query(ao_sync_query))

        # 数据库状态
        db_state_query = f'mssql_database_state{{ip="{instance_ip}"}}'
        metrics['database_state'] = self._extract_value(self.query(db_state_query))

        # 11. 内存指标
        # Target Server Memory (KB)
        target_memory_query = f'mssql_memory_target_kb{{ip="{instance_ip}"}}'
        target_memory = self._extract_value(self.query(target_memory_query))
        if target_memory:
            metrics['target_memory_mb'] = round(target_memory / 1024, 2)
        else:
            metrics['target_memory_mb'] = None

        # Total Server Memory (KB)
        total_memory_query = f'mssql_memory_total_kb{{ip="{instance_ip}"}}'
        total_memory = self._extract_value(self.query(total_memory_query))
        if total_memory:
            metrics['total_memory_mb'] = round(total_memory / 1024, 2)
        else:
            metrics['total_memory_mb'] = None

        # 内存压力
        if target_memory and total_memory:
            metrics['memory_pressure'] = round((total_memory / target_memory) * 100, 2)
        else:
            metrics['memory_pressure'] = None

        # 12. 系统资源（如果有process_exporter）
        cpu_query = f'rate(process_cpu_seconds_total{{ip="{instance_ip}"}}[5m]) * 100'
        metrics['cpu_usage'] = self._extract_value(self.query(cpu_query))

        memory_query = f'process_resident_memory_bytes{{ip="{instance_ip}"}}'
        memory_bytes = self._extract_value(self.query(memory_query))
        if memory_bytes:
            metrics['memory_usage_mb'] = round(memory_bytes / 1024 / 1024, 2)
        else:
            metrics['memory_usage_mb'] = None

        return metrics


# 测试函数
if __name__ == '__main__':
    # 测试Prometheus客户端
    prom = PrometheusClient('http://192.168.98.4:9090')

    # 检查健康
    print("Prometheus健康检查:", prom.check_health())

    # 获取生产实例指标
    test_ip = '192.168.46.101'
    print(f"\n获取实例 {test_ip} 的指标:")

    metrics = prom.get_instance_metrics(test_ip)
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    # 获取趋势数据
    print(f"\n获取实例 {test_ip} 最近1小时的趋势:")
    trends = prom.get_instance_trends(test_ip, hours=1)
    for metric, data in trends.items():
        print(f"  {metric}: {len(data)} 个数据点")
