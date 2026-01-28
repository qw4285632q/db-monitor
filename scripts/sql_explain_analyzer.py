#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL执行计划分析器
自动执行EXPLAIN并分析执行计划，识别性能问题并生成优化建议
"""

import json
import re
from typing import Dict, List, Any, Optional


class SQLExplainAnalyzer:
    """SQL执行计划分析器"""

    # 问题严重程度
    SEVERITY_CRITICAL = 'CRITICAL'   # 严重问题（全表扫描大表）
    SEVERITY_HIGH = 'HIGH'            # 高优先级（临时表、filesort）
    SEVERITY_MEDIUM = 'MEDIUM'        # 中等（索引不够优化）
    SEVERITY_LOW = 'LOW'              # 低优先级（建议优化）

    def __init__(self, db_connection):
        """
        初始化分析器

        Args:
            db_connection: 数据库连接对象
        """
        self.conn = db_connection

    def analyze_sql(self, sql_text: str, db_type: str = 'mysql') -> Dict[str, Any]:
        """
        分析SQL语句

        Args:
            sql_text: SQL语句
            db_type: 数据库类型（mysql/mssql/oracle）

        Returns:
            分析结果字典
        """
        if db_type.lower() == 'mysql':
            return self._analyze_mysql(sql_text)
        elif db_type.lower() == 'mssql':
            return self._analyze_mssql(sql_text)
        else:
            return {
                'success': False,
                'error': f'不支持的数据库类型: {db_type}'
            }

    def _analyze_mysql(self, sql_text: str) -> Dict[str, Any]:
        """分析MySQL SQL"""
        try:
            # 执行EXPLAIN获取执行计划
            plan_json = self._get_mysql_explain(sql_text)

            if not plan_json:
                return {
                    'success': False,
                    'error': '无法获取执行计划'
                }

            # 解析执行计划
            issues = []
            index_suggestions = []

            for query_block in plan_json.get('query_block', {}).get('table', []):
                if isinstance(query_block, dict):
                    table_issues, table_suggestions = self._analyze_mysql_table(query_block)
                    issues.extend(table_issues)
                    index_suggestions.extend(table_suggestions)

            # 检查嵌套查询
            if 'nested_loop' in plan_json.get('query_block', {}):
                nested_issues = self._analyze_nested_loop(
                    plan_json['query_block']['nested_loop']
                )
                issues.extend(nested_issues)

            return {
                'success': True,
                'plan_json': plan_json,
                'issues': issues,
                'index_suggestions': index_suggestions,
                'has_full_scan': any(i['type'] == 'FULL_SCAN' for i in issues),
                'has_temp_table': any(i['type'] == 'TEMP_TABLE' for i in issues),
                'has_filesort': any(i['type'] == 'FILESORT' for i in issues)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _get_mysql_explain(self, sql_text: str) -> Optional[Dict]:
        """获取MySQL EXPLAIN JSON格式结果"""
        try:
            with self.conn.cursor() as cursor:
                # 使用EXPLAIN FORMAT=JSON
                explain_sql = f"EXPLAIN FORMAT=JSON {sql_text}"
                cursor.execute(explain_sql)
                result = cursor.fetchone()

                if result and 'EXPLAIN' in result:
                    return json.loads(result['EXPLAIN'])

                return None

        except Exception as e:
            print(f"获取EXPLAIN失败: {e}")
            return None

    def _analyze_mysql_table(self, table_info: Dict) -> tuple:
        """
        分析MySQL表的执行计划

        Returns:
            (issues, index_suggestions)
        """
        issues = []
        suggestions = []

        table_name = table_info.get('table_name', 'unknown')
        access_type = table_info.get('access_type', '')
        possible_keys = table_info.get('possible_keys', [])
        key_used = table_info.get('key', None)
        rows = table_info.get('rows_examined_per_scan', 0)
        filtered = table_info.get('filtered', 100.0)

        # 检查1: 全表扫描
        if access_type == 'ALL':
            severity = self.SEVERITY_CRITICAL if rows > 10000 else self.SEVERITY_HIGH
            issues.append({
                'type': 'FULL_SCAN',
                'severity': severity,
                'table': table_name,
                'message': f'表 {table_name} 进行全表扫描，预估扫描 {rows} 行',
                'rows': rows
            })

            # 如果有可能的索引但没使用，建议使用
            if possible_keys:
                suggestions.append({
                    'table': table_name,
                    'type': 'USE_EXISTING_INDEX',
                    'message': f'可以使用现有索引: {", ".join(possible_keys)}',
                    'possible_keys': possible_keys
                })

        # 检查2: 索引扫描但效率低
        elif access_type in ['index', 'range'] and rows > 100000:
            issues.append({
                'type': 'INEFFICIENT_INDEX',
                'severity': self.SEVERITY_MEDIUM,
                'table': table_name,
                'message': f'索引扫描效率低，需扫描 {rows} 行',
                'rows': rows,
                'index_used': key_used
            })

        # 检查3: filtered值很低（选择性差）
        if filtered < 10:
            issues.append({
                'type': 'LOW_SELECTIVITY',
                'severity': self.SEVERITY_MEDIUM,
                'table': table_name,
                'message': f'过滤比例很低 ({filtered}%)，索引选择性差',
                'filtered': filtered
            })

        # 检查4: 使用临时表
        if 'using_temporary_table' in table_info:
            issues.append({
                'type': 'TEMP_TABLE',
                'severity': self.SEVERITY_HIGH,
                'table': table_name,
                'message': f'使用临时表，可能导致性能问题'
            })

        # 检查5: 使用文件排序
        if 'using_filesort' in table_info:
            issues.append({
                'type': 'FILESORT',
                'severity': self.SEVERITY_HIGH,
                'table': table_name,
                'message': f'使用文件排序，建议添加合适的索引'
            })

        # 生成索引建议（基于attached_condition）
        if 'attached_condition' in table_info:
            condition = table_info['attached_condition']
            suggested_columns = self._extract_columns_from_condition(condition)

            if suggested_columns and not key_used:
                suggestions.append({
                    'table': table_name,
                    'type': 'CREATE_INDEX',
                    'columns': suggested_columns,
                    'message': f'建议在 {table_name} 表上创建索引',
                    'create_statement': f"CREATE INDEX idx_{table_name}_{'_'.join(suggested_columns)} ON {table_name}({', '.join(suggested_columns)})"
                })

        return issues, suggestions

    def _analyze_nested_loop(self, nested_loop: List[Dict]) -> List[Dict]:
        """分析嵌套循环连接"""
        issues = []

        for item in nested_loop:
            if isinstance(item, dict) and 'table' in item:
                table_info = item['table']
                table_name = table_info.get('table_name', 'unknown')
                access_type = table_info.get('access_type', '')
                rows = table_info.get('rows_examined_per_scan', 0)

                # 嵌套循环中的全表扫描特别危险
                if access_type == 'ALL' and rows > 1000:
                    issues.append({
                        'type': 'NESTED_LOOP_FULL_SCAN',
                        'severity': self.SEVERITY_CRITICAL,
                        'table': table_name,
                        'message': f'嵌套循环中 {table_name} 表进行全表扫描，严重影响性能！',
                        'rows': rows
                    })

        return issues

    def _extract_columns_from_condition(self, condition: str) -> List[str]:
        """从WHERE条件中提取列名"""
        # 简单实现：提取形如 (table.column = value) 的模式
        pattern = r'\b(\w+)\s*(?:=|>|<|>=|<=|LIKE|IN)\s*'
        matches = re.findall(pattern, condition, re.IGNORECASE)

        # 去重并过滤常量
        columns = []
        for col in matches:
            if col.lower() not in ['and', 'or', 'not', 'true', 'false', 'null']:
                columns.append(col)

        return list(set(columns))[:3]  # 最多返回3个列

    def _analyze_mssql(self, sql_text: str) -> Dict[str, Any]:
        """分析SQL Server SQL（简化实现）"""
        try:
            # SQL Server使用SET SHOWPLAN_XML ON
            issues = []
            index_suggestions = []

            with self.conn.cursor() as cursor:
                cursor.execute("SET SHOWPLAN_XML ON")
                cursor.execute(sql_text)
                plan_xml = cursor.fetchone()[0]
                cursor.execute("SET SHOWPLAN_XML OFF")

                # 解析XML执行计划（需要xml.etree.ElementTree）
                # 这里是简化实现
                if 'TableScan' in plan_xml:
                    issues.append({
                        'type': 'FULL_SCAN',
                        'severity': self.SEVERITY_HIGH,
                        'message': '检测到表扫描操作'
                    })

                if 'Sort' in plan_xml:
                    issues.append({
                        'type': 'SORT_OPERATION',
                        'severity': self.SEVERITY_MEDIUM,
                        'message': '检测到排序操作'
                    })

            return {
                'success': True,
                'plan_xml': plan_xml,
                'issues': issues,
                'index_suggestions': index_suggestions
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def generate_optimization_report(self, analysis_result: Dict) -> str:
        """
        生成优化报告

        Args:
            analysis_result: 分析结果

        Returns:
            格式化的报告文本
        """
        if not analysis_result.get('success'):
            return f"分析失败: {analysis_result.get('error', '未知错误')}"

        report = []
        report.append("=" * 60)
        report.append("SQL执行计划分析报告")
        report.append("=" * 60)

        issues = analysis_result.get('issues', [])
        suggestions = analysis_result.get('index_suggestions', [])

        if not issues:
            report.append("\n✓ 未发现明显性能问题")
        else:
            report.append(f"\n发现 {len(issues)} 个性能问题:\n")

            # 按严重程度分组
            critical = [i for i in issues if i['severity'] == self.SEVERITY_CRITICAL]
            high = [i for i in issues if i['severity'] == self.SEVERITY_HIGH]
            medium = [i for i in issues if i['severity'] == self.SEVERITY_MEDIUM]

            if critical:
                report.append("🔴 严重问题:")
                for issue in critical:
                    report.append(f"  - {issue['message']}")

            if high:
                report.append("\n🟠 高优先级问题:")
                for issue in high:
                    report.append(f"  - {issue['message']}")

            if medium:
                report.append("\n🟡 中等问题:")
                for issue in medium:
                    report.append(f"  - {issue['message']}")

        if suggestions:
            report.append(f"\n\n优化建议 ({len(suggestions)} 条):\n")
            for idx, suggestion in enumerate(suggestions, 1):
                report.append(f"{idx}. {suggestion.get('message', '')}")
                if 'create_statement' in suggestion:
                    report.append(f"   SQL: {suggestion['create_statement']}")

        report.append("\n" + "=" * 60)

        return "\n".join(report)


# 测试代码
if __name__ == '__main__':
    # 这里是测试代码，实际使用时需要传入真实的数据库连接
    print("SQL执行计划分析器已加载")
    print("使用示例:")
    print("""
    from sql_explain_analyzer import SQLExplainAnalyzer

    analyzer = SQLExplainAnalyzer(db_connection)
    result = analyzer.analyze_sql("SELECT * FROM users WHERE name = 'test'", 'mysql')

    if result['success']:
        print("问题:", result['issues'])
        print("建议:", result['index_suggestions'])
        print(analyzer.generate_optimization_report(result))
    """)
