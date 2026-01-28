#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库迁移脚本 - 添加新字段"""
import pymysql
import json

print("=" * 70)
print("开始数据库迁移 - 添加新功能所需的字段")
print("=" * 70)

# 加载配置
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# 连接数据库
conn = pymysql.connect(**config['database'])
cursor = conn.cursor()

# 检查并添加字段
migrations = [
    {
        'table': 'long_running_sql_log',
        'field': 'sql_fingerprint',
        'sql': "ALTER TABLE long_running_sql_log ADD COLUMN sql_fingerprint VARCHAR(64) COMMENT 'SQL指纹(MD5)' AFTER sql_id"
    },
    {
        'table': 'long_running_sql_log',
        'field': 'sql_fulltext',
        'sql': "ALTER TABLE long_running_sql_log ADD COLUMN sql_fulltext LONGTEXT COMMENT 'SQL完整文本' AFTER sql_text"
    },
    {
        'table': 'long_running_sql_log',
        'field': 'execution_plan',
        'sql': "ALTER TABLE long_running_sql_log ADD COLUMN execution_plan JSON COMMENT '执行计划(JSON格式)' AFTER query_cost"
    },
    {
        'table': 'long_running_sql_log',
        'field': 'cpu_time',
        'sql': "ALTER TABLE long_running_sql_log ADD COLUMN cpu_time DECIMAL(15,2) COMMENT 'CPU时间(秒)' AFTER elapsed_minutes"
    },
    {
        'table': 'long_running_sql_log',
        'field': 'rows_examined',
        'sql': "ALTER TABLE long_running_sql_log ADD COLUMN rows_examined BIGINT COMMENT '扫描行数' AFTER physical_reads"
    },
    {
        'table': 'alert_history',
        'field': 'alert_type',
        'sql': "ALTER TABLE alert_history ADD COLUMN alert_type VARCHAR(50) NOT NULL DEFAULT 'slow_sql' COMMENT '告警类型(slow_sql/deadlock)' AFTER db_instance_id"
    },
    {
        'table': 'alert_history',
        'field': 'alert_identifier',
        'sql': "ALTER TABLE alert_history ADD COLUMN alert_identifier VARCHAR(200) COMMENT '告警标识符(SQL指纹/死锁时间)' AFTER alert_type"
    }
]

# 添加索引
indexes = [
    {
        'table': 'alert_history',
        'index': 'idx_alert_type',
        'sql': "ALTER TABLE alert_history ADD INDEX idx_alert_type (alert_type)"
    },
    {
        'table': 'alert_history',
        'index': 'idx_alert_identifier',
        'sql': "ALTER TABLE alert_history ADD INDEX idx_alert_identifier (alert_identifier)"
    }
]

# 执行迁移
for migration in migrations:
    try:
        # 检查字段是否已存在
        cursor.execute(f"DESC {migration['table']}")
        columns = [row[0] for row in cursor.fetchall()]

        if migration['field'] in columns:
            print(f"[跳过] {migration['table']}.{migration['field']} 已存在")
        else:
            cursor.execute(migration['sql'])
            conn.commit()
            print(f"[OK] 添加字段 {migration['table']}.{migration['field']}")
    except Exception as e:
        print(f"[错误] {migration['table']}.{migration['field']}: {e}")

# 添加索引
for idx in indexes:
    try:
        # 检查索引是否已存在
        cursor.execute(f"SHOW INDEX FROM {idx['table']} WHERE Key_name = '{idx['index']}'")
        if cursor.fetchone():
            print(f"[跳过] 索引 {idx['table']}.{idx['index']} 已存在")
        else:
            cursor.execute(idx['sql'])
            conn.commit()
            print(f"[OK] 添加索引 {idx['table']}.{idx['index']}")
    except Exception as e:
        print(f"[错误] 索引 {idx['table']}.{idx['index']}: {e}")

cursor.close()
conn.close()

print("\n" + "=" * 70)
print("迁移完成！现在可以运行 python auto_test_all.py 重新测试")
print("=" * 70)
