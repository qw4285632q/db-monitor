#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化和升级脚本
用于创建所有必需的表结构，并支持版本升级
"""

import pymysql
import json
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 当前数据库架构版本
CURRENT_SCHEMA_VERSION = '1.2.0'

def load_config():
    """加载配置文件"""
    config_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_db_connection(config):
    """获取数据库连接"""
    db_config = config.get('database', {})
    return pymysql.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 3306),
        user=db_config.get('user', 'root'),
        password=db_config.get('password', ''),
        database=db_config.get('database', 'db_monitor'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def check_table_exists(cursor, table_name):
    """检查表是否存在"""
    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
    return cursor.fetchone() is not None

def check_column_exists(cursor, table_name, column_name):
    """检查列是否存在"""
    cursor.execute(f"""
        SELECT COUNT(*) as count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = '{table_name}'
        AND COLUMN_NAME = '{column_name}'
    """)
    result = cursor.fetchone()
    return result['count'] > 0

def create_schema_version_table(cursor):
    """创建数据库版本表"""
    logger.info("创建数据库版本表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS db_schema_version (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            version VARCHAR(20) NOT NULL COMMENT '版本号',
            description TEXT COMMENT '版本描述',
            upgrade_sql TEXT COMMENT '升级SQL脚本',
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '应用时间',
            applied_by VARCHAR(50) DEFAULT 'system' COMMENT '执行者',
            INDEX idx_version (version),
            INDEX idx_applied_at (applied_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据库架构版本表'
    """)

def get_current_version(cursor):
    """获取当前数据库版本"""
    if not check_table_exists(cursor, 'db_schema_version'):
        return '0.0.0'

    cursor.execute("SELECT version FROM db_schema_version ORDER BY applied_at DESC LIMIT 1")
    result = cursor.fetchone()
    return result['version'] if result else '0.0.0'

def record_version(cursor, version, description):
    """记录版本升级"""
    cursor.execute("""
        INSERT INTO db_schema_version (version, description)
        VALUES (%s, %s)
    """, (version, description))

def create_db_instance_info_table(cursor):
    """创建数据库实例信息表"""
    logger.info("创建数据库实例信息表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS db_instance_info (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            db_project VARCHAR(100) NOT NULL COMMENT '项目名称',
            db_ip VARCHAR(50) NOT NULL COMMENT '数据库IP地址',
            db_port INT DEFAULT 3306 COMMENT '数据库端口',
            instance_name VARCHAR(100) COMMENT '实例名称',
            db_type VARCHAR(20) DEFAULT 'MySQL' COMMENT '数据库类型',
            db_user VARCHAR(50) COMMENT '数据库用户',
            db_password VARCHAR(200) COMMENT '数据库密码',
            db_admin VARCHAR(50) COMMENT '数据库管理员',
            db_version VARCHAR(50) COMMENT '数据库版本',
            environment VARCHAR(20) DEFAULT 'production' COMMENT '环境',
            status TINYINT DEFAULT 1 COMMENT '状态(1:启用 0:禁用)',
            description TEXT COMMENT '描述信息',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            INDEX idx_db_project (db_project),
            INDEX idx_db_ip (db_ip),
            INDEX idx_db_type (db_type),
            INDEX idx_status (status),
            UNIQUE KEY uk_db_instance (db_ip, db_port)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据库实例信息表'
    """)

def create_long_running_sql_log_table(cursor):
    """创建长时间运行SQL日志表"""
    logger.info("创建长时间运行SQL日志表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS long_running_sql_log (
            id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            db_instance_id INT NOT NULL COMMENT '数据库实例ID',
            session_id VARCHAR(50) COMMENT '会话ID',
            serial_no VARCHAR(50) COMMENT '序列号',
            sql_id VARCHAR(100) COMMENT 'SQL ID',
            sql_fingerprint VARCHAR(64) COMMENT 'SQL指纹(MD5)',
            sql_text VARCHAR(4000) COMMENT 'SQL文本(截断)',
            sql_fulltext LONGTEXT COMMENT 'SQL完整文本',
            username VARCHAR(100) COMMENT '执行用户',
            machine VARCHAR(200) COMMENT '客户端机器',
            program VARCHAR(200) COMMENT '客户端程序',
            module VARCHAR(200) COMMENT '模块名称',
            action VARCHAR(200) COMMENT '操作名称',
            elapsed_seconds DECIMAL(15,2) DEFAULT 0 COMMENT '运行秒数',
            elapsed_minutes DECIMAL(15,4) DEFAULT 0 COMMENT '运行分钟数',
            cpu_time DECIMAL(15,2) COMMENT 'CPU时间(秒)',
            wait_time DECIMAL(15,2) COMMENT '等待时间(秒)',
            logical_reads BIGINT COMMENT '逻辑读取数',
            physical_reads BIGINT COMMENT '物理读取数',
            rows_examined BIGINT COMMENT '扫描行数',
            rows_sent BIGINT COMMENT '返回行数',
            query_cost DECIMAL(15,4) COMMENT '查询成本',
            execution_plan JSON COMMENT '执行计划(JSON格式)',
            index_used VARCHAR(500) COMMENT '使用的索引',
            full_table_scan TINYINT DEFAULT 0 COMMENT '是否全表扫描',
            status VARCHAR(50) DEFAULT 'ACTIVE' COMMENT '状态',
            blocking_session VARCHAR(50) COMMENT '阻塞会话ID',
            wait_type VARCHAR(100) COMMENT '等待类型',
            wait_resource VARCHAR(200) COMMENT '等待资源',
            event VARCHAR(200) COMMENT '等待事件',
            sql_exec_start DATETIME COMMENT 'SQL执行开始时间',
            detect_time DATETIME NOT NULL COMMENT '检测时间',
            alert_sent TINYINT DEFAULT 0 COMMENT '是否已发送告警',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
            INDEX idx_db_instance_id (db_instance_id),
            INDEX idx_detect_time (detect_time),
            INDEX idx_elapsed_minutes (elapsed_minutes),
            INDEX idx_username (username),
            INDEX idx_status (status),
            INDEX idx_session_id (session_id),
            INDEX idx_sql_fingerprint (sql_fingerprint),
            INDEX idx_full_table_scan (full_table_scan),
            INDEX idx_alert_sent (alert_sent)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='长时间运行SQL日志表'
    """)

def create_deadlock_log_table(cursor):
    """创建死锁监控日志表"""
    logger.info("创建死锁监控日志表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deadlock_log (
            id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            db_instance_id INT NOT NULL COMMENT '数据库实例ID',
            deadlock_time DATETIME NOT NULL COMMENT '死锁发生时间',
            victim_session_id VARCHAR(50) COMMENT '受害者会话ID',
            victim_sql TEXT COMMENT '受害者SQL',
            victim_trx_id VARCHAR(50) COMMENT '受害者事务ID',
            blocker_session_id VARCHAR(50) COMMENT '阻塞者会话ID',
            blocker_sql TEXT COMMENT '阻塞者SQL',
            blocker_trx_id VARCHAR(50) COMMENT '阻塞者事务ID',
            deadlock_graph JSON COMMENT '完整死锁图(JSON格式)',
            wait_resource VARCHAR(200) COMMENT '等待资源',
            lock_mode VARCHAR(50) COMMENT '锁模式',
            lock_type VARCHAR(50) COMMENT '锁类型',
            isolation_level VARCHAR(50) COMMENT '隔离级别',
            resolved_action VARCHAR(100) COMMENT '解决动作',
            detect_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '检测时间',
            alert_sent TINYINT DEFAULT 0 COMMENT '是否已发送告警',
            alert_sent_time DATETIME COMMENT '告警发送时间',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            INDEX idx_db_instance_id (db_instance_id),
            INDEX idx_deadlock_time (deadlock_time),
            INDEX idx_detect_time (detect_time),
            INDEX idx_alert_sent (alert_sent)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='死锁监控日志表'
    """)

def create_monitor_alert_config_table(cursor):
    """创建监控告警配置表"""
    logger.info("创建监控告警配置表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitor_alert_config (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            alert_name VARCHAR(100) NOT NULL COMMENT '告警名称',
            alert_type VARCHAR(50) NOT NULL COMMENT '告警类型',
            threshold_warning DECIMAL(10,2) DEFAULT 5.0 COMMENT '警告阈值(分钟)',
            threshold_critical DECIMAL(10,2) DEFAULT 10.0 COMMENT '严重阈值(分钟)',
            notify_email VARCHAR(500) COMMENT '通知邮箱',
            notify_webhook VARCHAR(500) COMMENT 'Webhook通知地址',
            is_enabled TINYINT DEFAULT 1 COMMENT '是否启用',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_alert_type (alert_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='监控告警配置表'
    """)

def create_alert_history_table(cursor):
    """创建告警历史记录表"""
    logger.info("创建告警历史记录表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            db_instance_id INT NOT NULL COMMENT '数据库实例ID',
            sql_log_id BIGINT COMMENT '关联的SQL日志ID',
            alert_level VARCHAR(20) NOT NULL COMMENT '告警级别',
            alert_type VARCHAR(50) NOT NULL COMMENT '告警类型',
            alert_message TEXT COMMENT '告警消息',
            alert_detail JSON COMMENT '告警详情(JSON格式)',
            is_acknowledged TINYINT DEFAULT 0 COMMENT '是否已确认',
            acknowledged_by VARCHAR(50) COMMENT '确认人',
            acknowledged_at DATETIME COMMENT '确认时间',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            INDEX idx_db_instance_id (db_instance_id),
            INDEX idx_alert_level (alert_level),
            INDEX idx_alert_type (alert_type),
            INDEX idx_created_at (created_at),
            INDEX idx_is_acknowledged (is_acknowledged)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警历史记录表'
    """)

def insert_default_alert_config(cursor):
    """插入默认告警配置"""
    logger.info("插入默认告警配置...")
    cursor.execute("""
        INSERT IGNORE INTO monitor_alert_config
        (id, alert_name, alert_type, threshold_warning, threshold_critical, is_enabled)
        VALUES
        (1, '长时间SQL告警', 'long_running_sql', 5.0, 10.0, 1),
        (2, '会话阻塞告警', 'session_blocking', 3.0, 5.0, 1),
        (3, '死锁告警', 'deadlock', 0.0, 0.0, 1),
        (4, '连接数告警', 'connection_usage', 80.0, 90.0, 1),
        (5, '缓存命中率告警', 'cache_hit_rate', 95.0, 90.0, 1),
        (6, '复制延迟告警', 'replication_lag', 10.0, 60.0, 1)
    """)

def add_missing_columns(cursor):
    """添加缺失的列（用于数据库升级）"""
    logger.info("检查并添加缺失的列...")

    # 检查long_running_sql_log表的必需字段
    required_columns = {
        'long_running_sql_log': [
            ('wait_type', "VARCHAR(100) COMMENT '等待类型'"),
            ('wait_resource', "VARCHAR(200) COMMENT '等待资源'"),
            ('query_cost', "DECIMAL(15,4) COMMENT '查询成本'")
        ],
        'alert_history': [
            ('alert_type', "VARCHAR(50) NOT NULL DEFAULT 'unknown' COMMENT '告警类型'"),
            ('alert_detail', "JSON COMMENT '告警详情(JSON格式)'")
        ]
    }

    for table_name, columns in required_columns.items():
        if not check_table_exists(cursor, table_name):
            logger.warning(f"表 {table_name} 不存在，跳过字段检查")
            continue

        for column_name, column_def in columns:
            if not check_column_exists(cursor, table_name, column_name):
                logger.info(f"  添加缺失字段: {table_name}.{column_name}")
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
                except Exception as e:
                    logger.error(f"  添加字段失败: {e}")

def create_sql_fingerprint_stats_table(cursor):
    """创建SQL指纹统计表"""
    logger.info("创建SQL指纹统计表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sql_fingerprint_stats (
            fingerprint VARCHAR(64) PRIMARY KEY COMMENT 'SQL指纹(MD5)',
            sql_template TEXT COMMENT 'SQL模板',
            sql_type VARCHAR(20) COMMENT 'SQL类型(SELECT/UPDATE/DELETE等)',
            tables_involved VARCHAR(500) COMMENT '涉及的表',
            first_seen DATETIME COMMENT '首次发现时间',
            last_seen DATETIME COMMENT '最后发现时间',
            occurrence_count INT DEFAULT 0 COMMENT '出现次数',
            total_elapsed_seconds DECIMAL(20,2) DEFAULT 0 COMMENT '总运行秒数',
            avg_elapsed_seconds DECIMAL(15,4) DEFAULT 0 COMMENT '平均运行秒数',
            max_elapsed_seconds DECIMAL(15,2) DEFAULT 0 COMMENT '最大运行秒数',
            min_elapsed_seconds DECIMAL(15,2) DEFAULT 0 COMMENT '最小运行秒数',
            total_rows_examined BIGINT DEFAULT 0 COMMENT '总扫描行数',
            avg_rows_examined BIGINT DEFAULT 0 COMMENT '平均扫描行数',
            full_scan_count INT DEFAULT 0 COMMENT '全表扫描次数',
            has_index_suggestion TINYINT DEFAULT 0 COMMENT '是否有索引建议',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            INDEX idx_sql_type (sql_type),
            INDEX idx_occurrence (occurrence_count DESC),
            INDEX idx_avg_elapsed (avg_elapsed_seconds DESC),
            INDEX idx_last_seen (last_seen DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SQL指纹统计表'
    """)

def create_sql_execution_plan_table(cursor):
    """创建SQL执行计划表"""
    logger.info("创建SQL执行计划表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sql_execution_plan (
            id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            sql_fingerprint VARCHAR(64) COMMENT 'SQL指纹',
            longsql_id BIGINT COMMENT '关联的long_running_sql_log ID',
            db_instance_id INT COMMENT '数据库实例ID',
            plan_type VARCHAR(20) DEFAULT 'EXPLAIN' COMMENT '执行计划类型',
            plan_json JSON COMMENT '执行计划JSON',
            plan_text TEXT COMMENT '执行计划文本',
            has_full_scan TINYINT DEFAULT 0 COMMENT '是否有全表扫描',
            has_temp_table TINYINT DEFAULT 0 COMMENT '是否使用临时表',
            has_filesort TINYINT DEFAULT 0 COMMENT '是否使用文件排序',
            estimated_rows BIGINT COMMENT '预估扫描行数',
            analysis_result JSON COMMENT '分析结果(问题列表)',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            INDEX idx_fingerprint (sql_fingerprint),
            INDEX idx_longsql (longsql_id),
            INDEX idx_instance (db_instance_id),
            INDEX idx_created (created_at DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SQL执行计划表'
    """)

def create_index_suggestion_table(cursor):
    """创建索引建议表"""
    logger.info("创建索引建议表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS index_suggestion (
            id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
            sql_fingerprint VARCHAR(64) COMMENT 'SQL指纹',
            db_instance_id INT COMMENT '数据库实例ID',
            table_name VARCHAR(100) COMMENT '表名',
            schema_name VARCHAR(100) COMMENT '库名',
            suggested_columns VARCHAR(500) COMMENT '建议的索引列',
            index_type VARCHAR(20) DEFAULT 'BTREE' COMMENT '索引类型',
            create_statement TEXT COMMENT '创建索引语句',
            benefit_score DECIMAL(5,2) DEFAULT 0 COMMENT '收益评分(0-100)',
            estimated_improvement DECIMAL(5,2) COMMENT '预估性能提升(%)',
            status VARCHAR(20) DEFAULT 'pending' COMMENT '状态(pending/applied/rejected)',
            applied_at DATETIME COMMENT '应用时间',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            INDEX idx_fingerprint (sql_fingerprint),
            INDEX idx_table (schema_name, table_name),
            INDEX idx_status (status),
            INDEX idx_benefit (benefit_score DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='索引建议表'
    """)

def create_all_tables(cursor):
    """创建所有表"""
    create_schema_version_table(cursor)
    create_db_instance_info_table(cursor)
    create_long_running_sql_log_table(cursor)
    create_deadlock_log_table(cursor)
    create_monitor_alert_config_table(cursor)
    create_alert_history_table(cursor)
    # 新增表
    create_sql_fingerprint_stats_table(cursor)
    create_sql_execution_plan_table(cursor)
    create_index_suggestion_table(cursor)

def verify_tables(cursor):
    """验证所有必需的表是否存在"""
    required_tables = [
        'db_schema_version',
        'db_instance_info',
        'long_running_sql_log',
        'deadlock_log',
        'monitor_alert_config',
        'alert_history'
    ]

    missing_tables = []
    for table in required_tables:
        if not check_table_exists(cursor, table):
            missing_tables.append(table)

    return missing_tables

def init_database():
    """初始化数据库"""
    try:
        logger.info("=" * 60)
        logger.info("数据库初始化开始...")
        logger.info("=" * 60)

        # 加载配置
        config = load_config()

        # 连接数据库
        conn = get_db_connection(config)
        cursor = conn.cursor()

        # 获取当前版本
        current_version = get_current_version(cursor)
        logger.info(f"当前数据库版本: {current_version}")
        logger.info(f"目标数据库版本: {CURRENT_SCHEMA_VERSION}")

        # 创建所有表
        create_all_tables(cursor)

        # 添加缺失的列（升级功能）
        add_missing_columns(cursor)

        # 插入默认配置
        insert_default_alert_config(cursor)

        # 验证表结构
        missing_tables = verify_tables(cursor)
        if missing_tables:
            logger.error(f"以下表创建失败: {', '.join(missing_tables)}")
            raise Exception(f"表创建失败: {', '.join(missing_tables)}")

        # 记录版本（如果是新版本）
        if current_version != CURRENT_SCHEMA_VERSION:
            record_version(cursor, CURRENT_SCHEMA_VERSION, f"数据库架构升级: {current_version} -> {CURRENT_SCHEMA_VERSION}")
            logger.info(f"数据库版本已更新: {current_version} -> {CURRENT_SCHEMA_VERSION}")

        # 提交
        conn.commit()

        # 显示表结构摘要
        logger.info("\n" + "=" * 60)
        logger.info("数据库表结构:")
        logger.info("=" * 60)
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        for i, table in enumerate(tables, 1):
            table_name = list(table.values())[0]
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()['count']
            logger.info(f"{i}. {table_name} ({count} 条记录)")

        logger.info("=" * 60)
        logger.info("✅ 数据库初始化成功！")
        logger.info("=" * 60)

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    init_database()
