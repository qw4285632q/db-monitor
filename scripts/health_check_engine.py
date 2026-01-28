#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库健康检查引擎 - 核心实现
"""
from typing import Dict, List, Any
from datetime import datetime

class HealthCheckEngine:
    """数据库健康检查引擎"""
    
    SEVERITY_CRITICAL = 'CRITICAL'
    SEVERITY_HIGH = 'HIGH'
    SEVERITY_MEDIUM = 'MEDIUM'
    SEVERITY_LOW = 'LOW'
    
    def __init__(self, db_connection, instance_info: Dict):
        self.conn = db_connection
        self.instance = instance_info
    
    def perform_full_check(self) -> Dict[str, Any]:
        """执行完整健康检查"""
        db_type = self.instance.get('db_type', '').lower()
        
        if db_type == 'mysql':
            return self._check_mysql()
        else:
            return {'success': False, 'error': f'Unsupported DB type: {db_type}'}
    
    def _check_mysql(self) -> Dict[str, Any]:
        """MySQL健康检查"""
        issues = []
        
        # 检查配置参数
        issues.extend(self._check_mysql_config())
        
        # 检查统计信息
        issues.extend(self._check_mysql_statistics())
        
        # 计算健康评分
        score = self._calculate_health_score(issues)
        
        return {
            'success': True,
            'score': score,
            'issues': issues,
            'check_time': datetime.now().isoformat(),
            'total_issues': len(issues),
            'critical_count': len([i for i in issues if i['severity'] == self.SEVERITY_CRITICAL]),
            'high_count': len([i for i in issues if i['severity'] == self.SEVERITY_HIGH]),
            'medium_count': len([i for i in issues if i['severity'] == self.SEVERITY_MEDIUM])
        }
    
    def _check_mysql_config(self) -> List[Dict]:
        """检查MySQL配置参数"""
        issues = []
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("SHOW VARIABLES")
                variables = {row[0]: row[1] for row in cursor.fetchall()}
                
                # 检查buffer_pool_size
                buffer_pool_size = int(variables.get('innodb_buffer_pool_size', 0))
                if buffer_pool_size < 1024 * 1024 * 1024:  # < 1GB
                    issues.append({
                        'category': 'CONFIG',
                        'severity': self.SEVERITY_HIGH,
                        'parameter': 'innodb_buffer_pool_size',
                        'current': f"{buffer_pool_size / (1024**3):.2f}GB",
                        'recommended': '> 1GB',
                        'impact': 'Buffer Pool too small causes frequent disk IO'
                    })
                
                # 检查max_connections
                max_conn = int(variables.get('max_connections', 0))
                if max_conn < 200:
                    issues.append({
                        'category': 'CONFIG',
                        'severity': self.SEVERITY_MEDIUM,
                        'parameter': 'max_connections',
                        'current': max_conn,
                        'recommended': '>=200'
                    })
        
        except Exception as e:
            issues.append({
                'category': 'CONFIG',
                'severity': self.SEVERITY_LOW,
                'error': f'Config check failed: {str(e)}'
            })
        
        return issues
    
    def _check_mysql_statistics(self) -> List[Dict]:
        """检查统计信息新鲜度"""
        issues = []
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_schema, table_name, update_time,
                           DATEDIFF(NOW(), update_time) AS days_old
                    FROM information_schema.tables
                    WHERE table_schema NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
                      AND table_rows > 10000
                      AND update_time < DATE_SUB(NOW(), INTERVAL 7 DAY)
                    LIMIT 10
                """)
                
                stale_tables = cursor.fetchall()
                
                for row in stale_tables:
                    issues.append({
                        'category': 'STATISTICS',
                        'severity': self.SEVERITY_HIGH if row[3] > 30 else self.SEVERITY_MEDIUM,
                        'table': f"{row[0]}.{row[1]}",
                        'days_old': row[3],
                        'fix': f"ANALYZE TABLE {row[0]}.{row[1]};"
                    })
        
        except Exception as e:
            pass
        
        return issues
    
    def _calculate_health_score(self, issues: List[Dict]) -> int:
        """计算健康评分(0-100)"""
        base_score = 100
        
        for issue in issues:
            severity = issue.get('severity', 'LOW')
            if severity == self.SEVERITY_CRITICAL:
                base_score -= 20
            elif severity == self.SEVERITY_HIGH:
                base_score -= 10
            elif severity == self.SEVERITY_MEDIUM:
                base_score -= 5
            elif severity == self.SEVERITY_LOW:
                base_score -= 2
        
        return max(0, min(100, base_score))

if __name__ == '__main__':
    print("Health Check Engine loaded")
