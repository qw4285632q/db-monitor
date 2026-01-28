#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL指纹生成工具
将SQL语句标准化为模板，用于聚合相似SQL
"""

import re
import hashlib
from typing import Dict, Any


class SQLFingerprint:
    """SQL指纹生成器"""

    @staticmethod
    def generate(sql: str) -> str:
        """
        生成SQL指纹（MD5）

        原理：将SQL中的具体值替换为占位符，生成标准化的SQL模板

        示例：
        SELECT * FROM users WHERE id = 123 AND name = 'test'
        => select * from users where id = ? and name = ?
        => MD5 hash

        Args:
            sql: 原始SQL语句

        Returns:
            32位MD5哈希值
        """
        template = SQLFingerprint.normalize(sql)
        return hashlib.md5(template.encode('utf-8')).hexdigest()

    @staticmethod
    def normalize(sql: str) -> str:
        """
        标准化SQL为模板

        Args:
            sql: 原始SQL语句

        Returns:
            标准化后的SQL模板
        """
        if not sql:
            return ''

        # 转小写
        sql = sql.lower().strip()

        # 移除注释
        # /* ... */ 注释
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        # -- 注释
        sql = re.sub(r'--[^\n]*', '', sql)
        # # 注释
        sql = re.sub(r'#[^\n]*', '', sql)

        # 替换数字（包括小数、负数、科学计数法）
        sql = re.sub(r'\b-?\d+\.?\d*(?:e[+-]?\d+)?\b', '?', sql)

        # 替换字符串（单引号）
        sql = re.sub(r"'(?:[^']|'')*'", '?', sql)

        # 替换字符串（双引号）
        sql = re.sub(r'"(?:[^"]|"")*"', '?', sql)

        # 替换十六进制值
        sql = re.sub(r'\b0x[0-9a-f]+\b', '?', sql)

        # 替换IN列表: IN (1,2,3) => IN (?)
        sql = re.sub(r'in\s*\([^)]*\)', 'in(?+)', sql)

        # 替换VALUES列表: VALUES (1,'a'),(2,'b') => VALUES (?)
        sql = re.sub(r'values\s*\([^)]*\)(?:\s*,\s*\([^)]*\))*', 'values(?+)', sql)

        # 替换LIMIT子句: LIMIT 10, 20 => LIMIT ?,?
        sql = re.sub(r'limit\s+\d+(?:\s*,\s*\d+)?', 'limit ?', sql)
        sql = re.sub(r'limit\s+\d+\s+offset\s+\d+', 'limit ? offset ?', sql)

        # 标准化空格（多个空格合并为一个）
        sql = re.sub(r'\s+', ' ', sql)

        # 移除首尾空格
        sql = sql.strip()

        return sql

    @staticmethod
    def extract_metadata(sql: str) -> Dict[str, Any]:
        """
        从SQL中提取元数据

        Args:
            sql: 原始SQL语句

        Returns:
            包含SQL元数据的字典
        """
        sql_lower = sql.lower().strip()

        metadata = {
            'sql_type': SQLFingerprint._detect_sql_type(sql_lower),
            'tables': SQLFingerprint._extract_tables(sql_lower),
            'has_where': 'where' in sql_lower,
            'has_join': 'join' in sql_lower,
            'has_subquery': '(' in sql_lower and 'select' in sql_lower,
            'has_order_by': 'order by' in sql_lower,
            'has_group_by': 'group by' in sql_lower,
            'has_limit': 'limit' in sql_lower
        }

        return metadata

    @staticmethod
    def _detect_sql_type(sql: str) -> str:
        """检测SQL类型"""
        sql = sql.strip()
        if sql.startswith('select'):
            return 'SELECT'
        elif sql.startswith('insert'):
            return 'INSERT'
        elif sql.startswith('update'):
            return 'UPDATE'
        elif sql.startswith('delete'):
            return 'DELETE'
        elif sql.startswith('replace'):
            return 'REPLACE'
        elif sql.startswith('create'):
            return 'CREATE'
        elif sql.startswith('alter'):
            return 'ALTER'
        elif sql.startswith('drop'):
            return 'DROP'
        elif sql.startswith('truncate'):
            return 'TRUNCATE'
        else:
            return 'OTHER'

    @staticmethod
    def _extract_tables(sql: str) -> list:
        """
        提取SQL中涉及的表名（简单实现）

        注意：这是简化版本，复杂SQL可能提取不完整
        """
        tables = []

        # FROM子句中的表
        from_match = re.findall(r'from\s+([`"]?\w+[`"]?)', sql)
        tables.extend(from_match)

        # JOIN子句中的表
        join_match = re.findall(r'join\s+([`"]?\w+[`"]?)', sql)
        tables.extend(join_match)

        # UPDATE语句中的表
        update_match = re.findall(r'update\s+([`"]?\w+[`"]?)', sql)
        tables.extend(update_match)

        # INSERT INTO语句中的表
        insert_match = re.findall(r'insert\s+into\s+([`"]?\w+[`"]?)', sql)
        tables.extend(insert_match)

        # DELETE FROM语句中的表
        delete_match = re.findall(r'delete\s+from\s+([`"]?\w+[`"]?)', sql)
        tables.extend(delete_match)

        # 去重并移除反引号/引号
        tables = list(set([t.strip('`"') for t in tables]))

        return tables


# 测试代码
if __name__ == '__main__':
    test_sqls = [
        "SELECT * FROM users WHERE id = 123 AND name = 'test'",
        "SELECT * FROM users WHERE id = 456 AND name = 'admin'",
        "SELECT id, name FROM orders WHERE user_id IN (1,2,3) AND status = 'paid'",
        "SELECT id, name FROM orders WHERE user_id IN (4,5,6,7,8) AND status = 'pending'",
        "UPDATE users SET login_count = login_count + 1 WHERE id = 100",
        "UPDATE users SET login_count = login_count + 1 WHERE id = 200",
        "/* comment */ SELECT * FROM users WHERE id = 1 -- inline comment",
    ]

    print("=" * 80)
    print("SQL指纹生成测试")
    print("=" * 80)

    for sql in test_sqls:
        fingerprint = SQLFingerprint.generate(sql)
        normalized = SQLFingerprint.normalize(sql)
        metadata = SQLFingerprint.extract_metadata(sql)

        print(f"\n原始SQL: {sql}")
        print(f"标准化: {normalized}")
        print(f"指纹:   {fingerprint}")
        print(f"元数据: {metadata}")
        print("-" * 80)

    # 验证相似SQL生成相同指纹
    print("\n" + "=" * 80)
    print("相似SQL指纹验证")
    print("=" * 80)

    fp1 = SQLFingerprint.generate("SELECT * FROM users WHERE id = 123")
    fp2 = SQLFingerprint.generate("SELECT * FROM users WHERE id = 456")

    print(f"SQL1指纹: {fp1}")
    print(f"SQL2指纹: {fp2}")
    print(f"相同指纹: {fp1 == fp2}")  # 应该为True
