from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pymysql
from datetime import datetime, timedelta
import os
import json
import logging
import math
from functools import lru_cache
import time
from scripts.prometheus_client import PrometheusClient
from scripts.sql_fingerprint import SQLFingerprint
from scripts.sql_explain_analyzer import SQLExplainAnalyzer
from scripts.sqlserver_deadlock_collector import collect_all_sqlserver_deadlocks
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 尝试导入连接池，如果没有安装则使用普通连接
try:
    from DBUtils.PooledDB import PooledDB
    HAS_POOL = True
except ImportError:
    logger.warning("DBUtils未安装，使用普通数据库连接。建议安装: pip install DBUtils")
    HAS_POOL = False

app = Flask(__name__, static_folder='static', static_url_path='', template_folder='templates')
CORS(app)

# 配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# 默认配置
DEFAULT_DB_CONFIG = {
    'host': '192.168.11.85',
    'port': 3306,
    'user': 'root',
    'password': 'Root#2025Jac.Com',
    'database': 'db_monitor',
    'charset': 'utf8mb4'
}

DEFAULT_APP_CONFIG = {
    'auto_refresh_interval': 30,
    'warning_threshold': 5,
    'critical_threshold': 10,
    'default_hours': 24,
    'default_page_size': 20
}

# 配置缓存时间戳，用于手动清除缓存
_config_cache_timestamp = time.time()

@lru_cache(maxsize=1)
def _load_config_cached(cache_key):
    """从文件加载配置（带缓存）"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"从文件加载配置 (缓存键: {cache_key})")
                return config
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
    return {'database': DEFAULT_DB_CONFIG.copy(), 'app': DEFAULT_APP_CONFIG.copy()}

def load_config():
    """从文件加载配置（自动缓存60秒）"""
    # 使用时间戳作为缓存键，每60秒自动失效
    cache_key = int(time.time() / 60)
    return _load_config_cached(cache_key)

def clear_config_cache():
    """手动清除配置缓存"""
    _load_config_cached.cache_clear()
    logger.info("配置缓存已清除")

def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        # 保存后清除缓存，确保下次读取最新配置
        clear_config_cache()
        return True
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        return False

def get_db_config():
    """获取数据库配置"""
    config = load_config()
    db_config = config.get('database', DEFAULT_DB_CONFIG)
    return {
        'host': os.getenv('DB_HOST', db_config.get('host', '127.0.0.1')),
        'port': int(os.getenv('DB_PORT', db_config.get('port', 3306))),
        'user': os.getenv('DB_USER', db_config.get('user', 'root')),
        'password': os.getenv('DB_PASSWORD', db_config.get('password', '')),
        'database': os.getenv('DB_NAME', db_config.get('database', 'db_monitor')),
        'charset': db_config.get('charset', 'utf8mb4'),
        'cursorclass': pymysql.cursors.DictCursor
    }

# 全局连接池对象
_db_pool = None

def init_db_pool():
    """初始化数据库连接池"""
    global _db_pool
    if not HAS_POOL:
        logger.info("连接池功能未启用（DBUtils未安装）")
        return

    if _db_pool is not None:
        logger.info("数据库连接池已存在")
        return

    try:
        db_config = get_db_config()
        _db_pool = PooledDB(
            creator=pymysql,
            maxconnections=20,      # 最大连接数
            mincached=2,            # 最小空闲连接数
            maxcached=10,           # 最大空闲连接数
            maxshared=0,            # 最大共享连接数（0表示不共享）
            blocking=True,          # 连接池满时是否阻塞等待
            maxusage=None,          # 单个连接最大使用次数（None表示无限制）
            setsession=[],          # 连接前执行的SQL命令
            ping=1,                 # ping MySQL服务端，检查连接是否可用（0=不检查, 1=默认, 2=使用时检查, 4=事务开始时检查, 7=总是检查）
            **db_config
        )
        logger.info(f"数据库连接池初始化成功 (最大连接数: 20, 缓存连接数: 2-10)")
    except Exception as e:
        logger.error(f"数据库连接池初始化失败: {e}")
        _db_pool = None

def get_db_connection():
    """获取数据库连接（从连接池或直接创建）"""
    try:
        # 如果连接池可用，从池中获取连接
        if HAS_POOL and _db_pool is not None:
            return _db_pool.connection()
        # 否则直接创建连接
        return pymysql.connect(**get_db_config())
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return None

# ==================== 配置管理API ====================

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置"""
    try:
        config = load_config()
        safe_config = {
            'database': {
                'host': config.get('database', {}).get('host', ''),
                'port': config.get('database', {}).get('port', 3306),
                'user': config.get('database', {}).get('user', ''),
                'password': '******' if config.get('database', {}).get('password') else '',
                'database': config.get('database', {}).get('database', ''),
                'charset': config.get('database', {}).get('charset', 'utf8mb4')
            },
            'app': config.get('app', DEFAULT_APP_CONFIG),
            'prometheus': config.get('prometheus', {}),
            'exporter_mapping': config.get('exporter_mapping', {}),
            'sqlserver_exporter_mapping': config.get('sqlserver_exporter_mapping', {})
        }
        return jsonify({'success': True, 'data': safe_config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'}), 400

        config = load_config()

        if 'database' in data:
            db_data = data['database']
            for key in ['host', 'user', 'database', 'charset']:
                if key in db_data:
                    config.setdefault('database', {})[key] = db_data[key]
            if 'port' in db_data:
                config.setdefault('database', {})['port'] = int(db_data['port'])
            if 'password' in db_data and db_data['password'] != '******':
                config.setdefault('database', {})['password'] = db_data['password']

        if 'app' in data:
            config.setdefault('app', {}).update(data['app'])

        if save_config(config):
            return jsonify({'success': True, 'message': '配置保存成功'})
        return jsonify({'success': False, 'error': '保存失败'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/test', methods=['POST'])
def test_connection():
    """测试数据库连接"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'}), 400

        password = data.get('password', '')
        if password == '******':
            config = load_config()
            password = config.get('database', {}).get('password', '')

        test_config = {
            'host': data.get('host', '127.0.0.1'),
            'port': int(data.get('port', 3306)),
            'user': data.get('user', 'root'),
            'password': password,
            'database': data.get('database', 'db_monitor'),
            'charset': 'utf8mb4',
            'connect_timeout': 5,
            'cursorclass': pymysql.cursors.DictCursor
        }

        try:
            conn = pymysql.connect(**test_config)
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION() as version")
                result = cursor.fetchone()
                db_version = result['version'] if result else 'Unknown'

                cursor.execute("""
                    SELECT COUNT(*) as count FROM information_schema.tables
                    WHERE table_schema = %s AND table_name IN ('db_instance_info', 'long_running_sql_log')
                """, (test_config['database'],))
                tables_exist = cursor.fetchone()['count'] >= 2
            conn.close()

            return jsonify({
                'success': True,
                'message': '连接成功',
                'details': {'version': db_version, 'tables_initialized': tables_exist}
            })

        except pymysql.err.OperationalError as e:
            error_msgs = {
                1045: '用户名或密码错误',
                1049: '数据库不存在',
                2003: '无法连接服务器',
                2013: '连接超时'
            }
            return jsonify({
                'success': False,
                'error': error_msgs.get(e.args[0], str(e)),
                'error_code': e.args[0]
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def check_column_exists_func(cursor, table_name, column_name):
    """检查列是否存在"""
    cursor.execute(f"""
        SELECT COUNT(*) as count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = '{table_name}'
        AND COLUMN_NAME = '{column_name}'
    """)
    result = cursor.fetchone()
    return result[0] > 0

@app.route('/api/config/init-db', methods=['POST'])
def init_database():
    """初始化数据库表"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        created_tables = []
        added_columns = []

        with conn.cursor() as cursor:
            # 表0: 数据库版本表
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
            created_tables.append('db_schema_version')
            # 表1: 数据库实例信息表
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
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据库实例信息表'
            """)

            # 表2: 长时间运行SQL日志表(增强版)
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

            # 表3: 死锁监控日志表
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

            # 表4: 监控告警配置表
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
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='监控告警配置表'
            """)

            # 表5: 告警历史记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_history (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
                    db_instance_id INT NOT NULL COMMENT '数据库实例ID',
                    sql_log_id BIGINT COMMENT '关联的SQL日志ID',
                    alert_level VARCHAR(20) NOT NULL COMMENT '告警级别',
                    alert_message TEXT COMMENT '告警消息',
                    is_acknowledged TINYINT DEFAULT 0 COMMENT '是否已确认',
                    acknowledged_by VARCHAR(50) COMMENT '确认人',
                    acknowledged_at DATETIME COMMENT '确认时间',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    INDEX idx_db_instance_id (db_instance_id),
                    INDEX idx_alert_level (alert_level),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警历史记录表'
            """)

            # 检查并添加缺失的列
            # 1. long_running_sql_log表缺失的字段
            if not check_column_exists_func(cursor, 'long_running_sql_log', 'wait_type'):
                cursor.execute("ALTER TABLE long_running_sql_log ADD COLUMN wait_type VARCHAR(100) COMMENT '等待类型' AFTER blocking_session")
                added_columns.append('long_running_sql_log.wait_type')

            if not check_column_exists_func(cursor, 'long_running_sql_log', 'wait_resource'):
                cursor.execute("ALTER TABLE long_running_sql_log ADD COLUMN wait_resource VARCHAR(200) COMMENT '等待资源' AFTER wait_type")
                added_columns.append('long_running_sql_log.wait_resource')

            if not check_column_exists_func(cursor, 'long_running_sql_log', 'query_cost'):
                cursor.execute("ALTER TABLE long_running_sql_log ADD COLUMN query_cost DECIMAL(15,4) COMMENT '查询成本' AFTER rows_sent")
                added_columns.append('long_running_sql_log.query_cost')

            # 2. alert_history表缺失的字段
            if not check_column_exists_func(cursor, 'alert_history', 'alert_type'):
                cursor.execute("ALTER TABLE alert_history ADD COLUMN alert_type VARCHAR(50) NOT NULL DEFAULT 'unknown' COMMENT '告警类型' AFTER alert_level")
                added_columns.append('alert_history.alert_type')

            if not check_column_exists_func(cursor, 'alert_history', 'alert_detail'):
                cursor.execute("ALTER TABLE alert_history ADD COLUMN alert_detail JSON COMMENT '告警详情(JSON格式)' AFTER alert_message")
                added_columns.append('alert_history.alert_detail')

            # 插入默认告警配置
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

            # 记录版本
            cursor.execute("SELECT COUNT(*) FROM db_schema_version WHERE version = '1.2.0'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO db_schema_version (version, description)
                    VALUES ('1.2.0', '完善数据库初始化，添加版本管理和缺失字段检查')
                """)

        conn.commit()
        conn.close()

        # 构建成功消息
        message = '数据库初始化成功！'
        if created_tables:
            message += f' 创建了 {len(created_tables)} 个表'
        if added_columns:
            message += f'，添加了 {len(added_columns)} 个缺失字段'

        return jsonify({
            'success': True,
            'message': message,
            'details': {
                'created_tables': created_tables,
                'added_columns': added_columns
            }
        })

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 告警配置API ====================

@app.route('/api/alert-config', methods=['GET'])
def get_alert_config():
    """获取告警配置"""
    try:
        alert_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alert_config.json')

        if os.path.exists(alert_config_file):
            with open(alert_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            # 返回默认配置
            config = {
                'wecom': {'webhook': '', 'enabled': False},
                'dingtalk': {'webhook': '', 'secret': '', 'enabled': False},
                'email': {
                    'host': '', 'port': 465, 'user': '', 'password': '',
                    'from': '', 'to': [], 'enabled': False
                },
                'alert_rules': {
                    'slow_sql_threshold_minutes': 10,
                    'deadlock_always_alert': True,
                    'alert_interval_seconds': 300
                }
            }

        # 隐藏敏感信息
        if config.get('wecom', {}).get('webhook'):
            webhook = config['wecom']['webhook']
            if len(webhook) > 20:
                config['wecom']['webhook_display'] = webhook[:20] + '...' + webhook[-10:]
            else:
                config['wecom']['webhook_display'] = webhook

        if config.get('email', {}).get('password'):
            config['email']['password'] = '******'

        return jsonify({'success': True, 'data': config})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alert-config', methods=['POST'])
def update_alert_config():
    """更新告警配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'}), 400

        alert_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alert_config.json')

        # 读取现有配置
        if os.path.exists(alert_config_file):
            with open(alert_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

        # 更新企业微信配置
        if 'wecom' in data:
            wecom = data['wecom']
            config.setdefault('wecom', {})
            if 'webhook' in wecom and wecom['webhook']:
                config['wecom']['webhook'] = wecom['webhook']
            if 'enabled' in wecom:
                config['wecom']['enabled'] = wecom['enabled']

        # 更新钉钉配置
        if 'dingtalk' in data:
            dingtalk = data['dingtalk']
            config.setdefault('dingtalk', {})
            if 'webhook' in dingtalk:
                config['dingtalk']['webhook'] = dingtalk['webhook']
            if 'secret' in dingtalk:
                config['dingtalk']['secret'] = dingtalk['secret']
            if 'enabled' in dingtalk:
                config['dingtalk']['enabled'] = dingtalk['enabled']

        # 更新邮件配置
        if 'email' in data:
            email = data['email']
            config.setdefault('email', {})
            for key in ['host', 'port', 'user', 'from']:
                if key in email:
                    config['email'][key] = email[key]
            if 'password' in email and email['password'] != '******':
                config['email']['password'] = email['password']
            if 'to' in email:
                config['email']['to'] = email['to']
            if 'enabled' in email:
                config['email']['enabled'] = email['enabled']

        # 更新告警规则
        if 'alert_rules' in data:
            config.setdefault('alert_rules', {})
            config['alert_rules'].update(data['alert_rules'])

        # 保存配置
        with open(alert_config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return jsonify({'success': True, 'message': '告警配置保存成功'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alert-config/test', methods=['POST'])
def test_alert():
    """测试告警"""
    try:
        data = request.get_json()
        channel = data.get('channel', 'wecom')  # wecom, dingtalk, email

        alert_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alert_config.json')

        if not os.path.exists(alert_config_file):
            return jsonify({'success': False, 'error': '告警配置文件不存在'}), 400

        with open(alert_config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 动态导入告警模块
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils'))
        from alert import WeComAlert, DingTalkAlert, EmailAlert

        test_title = "🧪 数据库监控系统测试"
        test_content = f"这是一条{channel}告警测试消息。\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n如果您收到此消息，说明告警配置成功！"

        if channel == 'wecom':
            webhook = config.get('wecom', {}).get('webhook', '')
            if not webhook:
                return jsonify({'success': False, 'error': '企业微信Webhook未配置'}), 400

            alert = WeComAlert(webhook)
            success = alert.send(test_title, test_content, 'INFO')

        elif channel == 'dingtalk':
            webhook = config.get('dingtalk', {}).get('webhook', '')
            secret = config.get('dingtalk', {}).get('secret', '')
            if not webhook:
                return jsonify({'success': False, 'error': '钉钉Webhook未配置'}), 400

            alert = DingTalkAlert(webhook, secret)
            success = alert.send(test_title, test_content, 'INFO')

        elif channel == 'email':
            email_config = config.get('email', {})
            if not email_config.get('host'):
                return jsonify({'success': False, 'error': '邮件配置不完整'}), 400

            alert = EmailAlert(email_config)
            success = alert.send(test_title, test_content, 'INFO')

        else:
            return jsonify({'success': False, 'error': '不支持的告警渠道'}), 400

        if success:
            return jsonify({'success': True, 'message': f'{channel}测试消息发送成功'})
        else:
            return jsonify({'success': False, 'error': '测试消息发送失败'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 采集器配置管理API ====================

@app.route('/api/collectors/config', methods=['GET'])
def get_collectors_config():
    """获取采集器配置"""
    try:
        config = load_config()
        collectors_config = config.get('collectors', {
            'mysql': {
                'enabled': True,
                'interval': 60,
                'threshold': 5,
                'description': 'MySQL Performance Schema采集器'
            },
            'sqlserver': {
                'enabled': True,
                'interval': 60,
                'threshold': 5,
                'auto_enable_querystore': False,
                'description': 'SQL Server Query Store采集器'
            }
        })

        # 获取采集器状态
        mysql_job = scheduler.get_job('mysql_collector')
        sqlserver_job = scheduler.get_job('sqlserver_collector')

        collectors_config['mysql']['status'] = 'running' if mysql_job else 'stopped'
        collectors_config['sqlserver']['status'] = 'running' if sqlserver_job else 'stopped'

        # 获取下次运行时间
        if mysql_job and mysql_job.next_run_time:
            collectors_config['mysql']['next_run'] = mysql_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        if sqlserver_job and sqlserver_job.next_run_time:
            collectors_config['sqlserver']['next_run'] = sqlserver_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')

        return jsonify({'success': True, 'data': collectors_config})
    except Exception as e:
        logger.error(f"获取采集器配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/collectors/config', methods=['POST'])
def update_collectors_config():
    """更新采集器配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'}), 400

        config = load_config()
        if 'collectors' not in config:
            config['collectors'] = {}

        # 更新配置
        for collector_type in ['mysql', 'sqlserver']:
            if collector_type in data:
                collector_data = data[collector_type]
                if collector_type not in config['collectors']:
                    config['collectors'][collector_type] = {}

                # 更新配置字段
                for key in ['enabled', 'interval', 'threshold', 'auto_enable_querystore', 'description']:
                    if key in collector_data:
                        config['collectors'][collector_type][key] = collector_data[key]

        # 保存配置
        if not save_config(config):
            return jsonify({'success': False, 'error': '保存配置失败'}), 500

        # 实时更新调度器
        for collector_type in ['mysql', 'sqlserver']:
            if collector_type in data:
                collector_config = config['collectors'][collector_type]
                update_collector_schedule(
                    collector_type,
                    collector_config.get('enabled', True),
                    collector_config.get('interval', 60)
                )

        return jsonify({'success': True, 'message': '采集器配置已更新并实时生效'})

    except Exception as e:
        logger.error(f"更新采集器配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/collectors/status', methods=['GET'])
def get_collectors_status():
    """获取采集器运行状态"""
    try:
        status = {}

        for collector_type in ['mysql', 'sqlserver']:
            job_id = f"{collector_type}_collector"
            job = scheduler.get_job(job_id)

            if job:
                status[collector_type] = {
                    'running': True,
                    'next_run': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else None,
                    'trigger': str(job.trigger)
                }
            else:
                status[collector_type] = {
                    'running': False,
                    'next_run': None,
                    'trigger': None
                }

        return jsonify({'success': True, 'data': status})
    except Exception as e:
        logger.error(f"获取采集器状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/collectors/<collector_type>/trigger', methods=['POST'])
def trigger_collector(collector_type):
    """手动触发采集器执行一次"""
    try:
        if collector_type not in ['mysql', 'sqlserver']:
            return jsonify({'success': False, 'error': '无效的采集器类型'}), 400

        # 立即执行一次
        if collector_type == 'mysql':
            run_mysql_collector()
        else:
            run_sqlserver_collector()

        return jsonify({'success': True, 'message': f'{collector_type}采集器已手动触发执行'})
    except Exception as e:
        logger.error(f"手动触发采集器失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 实例管理API ====================

@app.route('/api/instances', methods=['GET'])
def get_instances():
    """获取实例列表"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, db_project, db_ip, db_port, instance_name, db_type,
                       db_user, db_admin, environment, status, description,
                       created_at, updated_at
                FROM db_instance_info ORDER BY db_project, db_ip
            """)
            results = cursor.fetchall()
            for row in results:
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.strftime('%Y-%m-%d %H:%M:%S')
        conn.close()
        return jsonify({'success': True, 'data': results, 'total': len(results)})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/instances', methods=['POST'])
def add_instance():
    """添加实例"""
    try:
        data = request.get_json()
        if not data or not data.get('db_project') or not data.get('db_ip'):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO db_instance_info
                (db_project, db_ip, db_port, instance_name, db_type, db_user, db_password, db_admin, environment, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data.get('db_project'), data.get('db_ip'), data.get('db_port', 3306),
                data.get('instance_name', ''), data.get('db_type', 'MySQL'),
                data.get('db_user', ''), data.get('db_password', ''),
                data.get('db_admin', ''), data.get('environment', 'production'),
                data.get('description', '')
            ))
            instance_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': '添加成功', 'id': instance_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/instances/<int:id>', methods=['PUT'])
def update_instance(id):
    """更新实例"""
    logger.info(f"Update instance called with id={id}")
    try:
        data = request.get_json()
        logger.info(f"Request data: {data}")
        if not data:
            return jsonify({'success': False, 'error': '无效数据'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        fields = ['db_project', 'db_ip', 'db_port', 'instance_name', 'db_type',
                  'db_user', 'db_password', 'db_admin', 'environment', 'status', 'description']
        updates = []
        params = []
        for f in fields:
            if f in data:
                updates.append(f"{f} = %s")
                params.append(data[f])

        if not updates:
            return jsonify({'success': False, 'error': '没有更新字段'}), 400

        params.append(id)
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE db_instance_info SET {', '.join(updates)} WHERE id = %s", params)
            affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            return jsonify({'success': True, 'message': '更新成功'})
        return jsonify({'success': False, 'error': '实例不存在'}), 404

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/instances/<int:id>', methods=['DELETE'])
def delete_instance(id):
    """删除实例"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM long_running_sql_log WHERE db_instance_id = %s", (id,))
            cursor.execute("DELETE FROM db_instance_info WHERE id = %s", (id,))
            affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            return jsonify({'success': True, 'message': '删除成功'})
        return jsonify({'success': False, 'error': '实例不存在'}), 404

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/instances/<int:id>/test', methods=['POST'])
def test_instance_connection(id):
    """测试实例连接"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '管理数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT db_ip, db_port, db_type, db_user, db_password, instance_name
                FROM db_instance_info WHERE id = %s
            """, (id,))
            instance = cursor.fetchone()
        conn.close()

        if not instance:
            return jsonify({'success': False, 'error': '实例不存在'}), 404

        db_type = instance['db_type'] or 'MySQL'

        # 根据数据库类型测试连接
        if db_type == 'MySQL':
            try:
                test_conn = pymysql.connect(
                    host=instance['db_ip'],
                    port=instance['db_port'] or 3306,
                    user=instance['db_user'] or 'root',
                    password=instance['db_password'] or '',
                    connect_timeout=5,
                    cursorclass=pymysql.cursors.DictCursor
                )
                with test_conn.cursor() as cursor:
                    cursor.execute("SELECT VERSION() as version")
                    result = cursor.fetchone()
                    version = result['version'] if result else 'Unknown'
                test_conn.close()
                return jsonify({
                    'success': True,
                    'message': 'MySQL连接成功',
                    'details': {'version': version, 'type': 'MySQL'}
                })
            except pymysql.err.OperationalError as e:
                error_msgs = {
                    1045: '用户名或密码错误',
                    2003: '无法连接到服务器',
                    2013: '连接超时'
                }
                return jsonify({
                    'success': False,
                    'error': error_msgs.get(e.args[0], str(e))
                })
        elif db_type == 'SQLServer':
            try:
                import pyodbc
                # 构建连接字符串
                conn_str = (
                    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                    f"SERVER={instance['db_ip']},{instance['db_port'] or 1433};"
                    f"UID={instance['db_user'] or 'sa'};"
                    f"PWD={instance['db_password'] or ''};"
                    f"Encrypt=no;"
                    f"TrustServerCertificate=yes;"
                )
                test_conn = pyodbc.connect(conn_str, timeout=5)
                cursor = test_conn.cursor()
                cursor.execute("SELECT @@VERSION as version")
                row = cursor.fetchone()
                version = row.version.split('\n')[0] if row else 'Unknown'
                cursor.close()
                test_conn.close()
                return jsonify({
                    'success': True,
                    'message': 'SQL Server连接成功',
                    'details': {'version': version, 'type': 'SQLServer'}
                })
            except pyodbc.Error as e:
                error_msg = str(e)
                if 'Login failed' in error_msg:
                    error_msg = '用户名或密码错误'
                elif 'Cannot open' in error_msg or 'timeout' in error_msg.lower():
                    error_msg = '无法连接到服务器或连接超时'
                return jsonify({
                    'success': False,
                    'error': f'SQL Server连接失败: {error_msg}'
                })
            except ImportError:
                return jsonify({
                    'success': False,
                    'error': 'pyodbc模块未安装，请运行: pip install pyodbc'
                })
        elif db_type in ['Oracle', 'PostgreSQL']:
            return jsonify({
                'success': False,
                'error': f'{db_type} 连接测试暂未实现，请先配置相应的数据库驱动'
            })
        else:
            return jsonify({'success': False, 'error': '不支持的数据库类型'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 监控数据API ====================

@app.route('/')
def index():
    try:
        return send_from_directory('static', 'index.html')
    except:
        return '<h1>请将index.html放到static目录</h1>'

@app.route('/api/health', methods=['GET'])
def health_check():
    db_status = 'connected'
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
        else:
            db_status = 'disconnected'
    except:
        db_status = 'error'

    return jsonify({
        'status': 'healthy',
        'database': db_status,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': '1.1.0'
    })

@app.route('/api/long_sql', methods=['GET'])
def get_long_running_sql():
    try:
        hours = request.args.get('hours', 24, type=int)
        instance_id = request.args.get('instance_id', type=int)
        min_minutes = request.args.get('min_minutes', 0.0, type=float)
        page = max(1, request.args.get('page', 1, type=int))
        page_size = min(100, max(1, request.args.get('page_size', 20, type=int)))
        offset = (page - 1) * page_size

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            where = ["l.detect_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)", "l.elapsed_minutes >= %s"]
            params = [hours, min_minutes]

            if instance_id:
                where.append("l.db_instance_id = %s")
                params.append(instance_id)

            where_clause = " AND ".join(where)

            cursor.execute(f"SELECT COUNT(*) as cnt FROM long_running_sql_log l WHERE {where_clause}", params)
            total = cursor.fetchone()['cnt']
            total_pages = math.ceil(total / page_size) if page_size > 0 else 1

            cursor.execute(f"""
                SELECT l.*, i.db_project, i.db_ip, i.db_port, i.instance_name
                FROM long_running_sql_log l
                LEFT JOIN db_instance_info i ON l.db_instance_id = i.id
                WHERE {where_clause}
                ORDER BY l.detect_time DESC LIMIT %s OFFSET %s
            """, params + [page_size, offset])
            results = cursor.fetchall()

            for row in results:
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(v, timedelta):
                        row[k] = str(v)

        conn.close()
        return jsonify({
            'success': True, 'data': results,
            'pagination': {
                'current_page': page, 'page_size': page_size,
                'total_count': total, 'total_pages': total_pages,
                'has_prev': page > 1, 'has_next': page < total_pages
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/long_sql/<int:sql_id>', methods=['GET'])
def get_long_sql_detail(sql_id):
    """获取单个慢SQL详细信息"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT l.*, i.db_project, i.db_ip, i.db_port, i.instance_name, i.db_type
                FROM long_running_sql_log l
                LEFT JOIN db_instance_info i ON l.db_instance_id = i.id
                WHERE l.id = %s
            """, (sql_id,))
            result = cursor.fetchone()

            if not result:
                return jsonify({'success': False, 'error': 'SQL记录不存在'}), 404

            # 转换日期时间格式
            for k, v in result.items():
                if isinstance(v, datetime):
                    result[k] = v.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(v, timedelta):
                    result[k] = str(v)

        conn.close()
        return jsonify({'success': True, 'data': result})

    except Exception as e:
        logger.error(f"获取SQL详情失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/deadlocks', methods=['GET'])
def get_deadlocks():
    """获取死锁列表"""
    try:
        hours = request.args.get('hours', 24, type=int)
        instance_id = request.args.get('instance_id', type=int)
        page = max(1, request.args.get('page', 1, type=int))
        page_size = min(100, max(1, request.args.get('page_size', 20, type=int)))
        offset = (page - 1) * page_size

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            where = ["d.detect_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)"]
            params = [hours]

            if instance_id:
                where.append("d.db_instance_id = %s")
                params.append(instance_id)

            where_clause = " AND ".join(where)

            cursor.execute(f"SELECT COUNT(*) as cnt FROM deadlock_log d WHERE {where_clause}", params)
            total = cursor.fetchone()['cnt']
            total_pages = math.ceil(total / page_size) if page_size > 0 else 1

            cursor.execute(f"""
                SELECT d.*, i.db_project, i.db_ip, i.db_port, i.instance_name, i.db_type
                FROM deadlock_log d
                LEFT JOIN db_instance_info i ON d.db_instance_id = i.id
                WHERE {where_clause}
                ORDER BY d.detect_time DESC LIMIT %s OFFSET %s
            """, params + [page_size, offset])
            results = cursor.fetchall()

            for row in results:
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.strftime('%Y-%m-%d %H:%M:%S')

        conn.close()
        return jsonify({
            'success': True, 'data': results,
            'pagination': {
                'current_page': page, 'page_size': page_size,
                'total_count': total, 'total_pages': total_pages,
                'has_prev': page > 1, 'has_next': page < total_pages
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    try:
        hours = request.args.get('hours', 24, type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            # 统计启用的实例总数
            cursor.execute("SELECT COUNT(*) as total_instances FROM db_instance_info WHERE status = 1")
            instance_stat = cursor.fetchone()
            total_instances = instance_stat.get('total_instances', 0) if instance_stat else 0

            # 死锁统计
            cursor.execute("""
                SELECT COUNT(*) as deadlock_count
                FROM deadlock_log WHERE detect_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            """, (hours,))
            deadlock_stat = cursor.fetchone()

            # 慢SQL统计
            cursor.execute("""
                SELECT COUNT(*) as total_sql_count, AVG(elapsed_minutes) as avg_duration,
                       MAX(elapsed_minutes) as max_duration,
                       SUM(CASE WHEN elapsed_minutes > 10 THEN 1 ELSE 0 END) as critical_count,
                       SUM(CASE WHEN elapsed_minutes > 5 AND elapsed_minutes <= 10 THEN 1 ELSE 0 END) as warning_count,
                       SUM(CASE WHEN elapsed_minutes <= 5 THEN 1 ELSE 0 END) as normal_count
                FROM long_running_sql_log WHERE detect_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            """, (hours,))
            summary = cursor.fetchone()

            # 添加实例总数到summary
            if summary:
                summary['instance_count'] = total_instances

            cursor.execute("""
                SELECT i.db_project, i.db_ip, i.instance_name, COUNT(l.id) as sql_count,
                       AVG(l.elapsed_minutes) as avg_duration, MAX(l.elapsed_minutes) as max_duration
                FROM db_instance_info i
                LEFT JOIN long_running_sql_log l ON i.id = l.db_instance_id
                    AND l.detect_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY i.id ORDER BY sql_count DESC
            """, (hours,))
            instances = cursor.fetchall()

            cursor.execute("""
                SELECT DATE_FORMAT(detect_time, '%%Y-%%m-%%d %%H:00') as hour_time,
                       COUNT(*) as sql_count, AVG(elapsed_minutes) as avg_duration
                FROM long_running_sql_log WHERE detect_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY hour_time ORDER BY hour_time
            """, (hours,))
            trend = cursor.fetchall()

        conn.close()

        # 合并死锁统计到summary
        summary_with_deadlock = summary or {}
        summary_with_deadlock['deadlock_count'] = deadlock_stat.get('deadlock_count', 0) if deadlock_stat else 0

        return jsonify({
            'success': True,
            'summary': summary_with_deadlock,
            'instances': instances or [],
            'trend': trend or []
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/performance_metrics', methods=['GET'])
def get_performance_metrics():
    """获取性能指标：QPS、TPS、连接数、缓存命中率等"""
    try:
        instance_id = request.args.get('instance_id', type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '监控数据库连接失败'}), 500

        # 获取实例列表
        with conn.cursor() as cursor:
            if instance_id:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE id = %s AND status = 1
                """, (instance_id,))
                instances = [cursor.fetchone()]
            else:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE status = 1 LIMIT 10
                """)
                instances = cursor.fetchall()

        conn.close()

        metrics_list = []
        for instance in instances:
            if not instance or instance['db_type'] != 'MySQL':
                continue

            try:
                # 连接目标MySQL实例
                target_conn = pymysql.connect(
                    host=instance['db_ip'],
                    port=instance['db_port'],
                    user=instance['db_user'],
                    password=instance['db_password'],
                    connect_timeout=3,
                    cursorclass=pymysql.cursors.DictCursor
                )

                with target_conn.cursor() as cursor:
                    metrics = {
                        'instance_id': instance['id'],
                        'db_project': instance['db_project'],
                        'db_ip': instance['db_ip'],
                        'db_port': instance['db_port'],
                        'instance_name': instance['instance_name'] or f"{instance['db_ip']}:{instance['db_port']}"
                    }

                    # QPS/TPS计算
                    cursor.execute("SHOW GLOBAL STATUS WHERE variable_name IN ('Questions', 'Com_commit', 'Com_rollback', 'Uptime')")
                    status_vars = {row['Variable_name']: int(row['Value']) for row in cursor.fetchall()}

                    uptime = status_vars.get('Uptime', 1)
                    if uptime > 0:
                        metrics['qps'] = round(status_vars.get('Questions', 0) / uptime, 2)
                        metrics['tps'] = round((status_vars.get('Com_commit', 0) + status_vars.get('Com_rollback', 0)) / uptime, 2)
                    else:
                        metrics['qps'] = 0
                        metrics['tps'] = 0

                    # 连接数统计
                    cursor.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
                    threads_result = cursor.fetchone()
                    current_connections = int(threads_result['Value']) if threads_result else 0

                    cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
                    max_result = cursor.fetchone()
                    max_connections = int(max_result['Value']) if max_result else 1

                    metrics['current_connections'] = current_connections
                    metrics['max_connections'] = max_connections
                    metrics['connection_usage'] = round(current_connections / max_connections * 100, 2)
                    metrics['connection_warning'] = metrics['connection_usage'] > 80  # >80%告警

                    # 缓存命中率
                    cursor.execute("SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%'")
                    cache_stats = {row['Variable_name']: int(row['Value']) for row in cursor.fetchall()}

                    read_requests = cache_stats.get('Innodb_buffer_pool_read_requests', 0)
                    read_disk = cache_stats.get('Innodb_buffer_pool_reads', 0)

                    if read_requests + read_disk > 0:
                        metrics['cache_hit_rate'] = round(read_requests / (read_requests + read_disk) * 100, 2)
                        metrics['cache_warning'] = metrics['cache_hit_rate'] < 95  # <95%告警
                    else:
                        metrics['cache_hit_rate'] = 100
                        metrics['cache_warning'] = False

                    # 慢查询统计
                    cursor.execute("SHOW GLOBAL STATUS LIKE 'Slow_queries'")
                    slow_result = cursor.fetchone()
                    metrics['slow_queries'] = int(slow_result['Value']) if slow_result else 0

                    metrics_list.append(metrics)

                target_conn.close()

            except Exception as e:
                logger.error(f"获取实例{instance['db_project']}性能指标失败: {e}")
                continue

        return jsonify({'success': True, 'data': metrics_list})

    except Exception as e:
        logger.error(f"获取性能指标失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sqlserver/performance_metrics', methods=['GET'])
def get_sqlserver_performance_metrics():
    """获取SQL Server性能指标：Batch Requests/sec、TPS、连接数、缓存命中率等"""
    try:
        instance_id = request.args.get('instance_id', type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '监控数据库连接失败'}), 500

        # 获取SQL Server实例列表
        with conn.cursor() as cursor:
            if instance_id:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE id = %s AND status = 1
                """, (instance_id,))
                instances = [cursor.fetchone()]
            else:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE status = 1 AND db_type = 'SQL Server' LIMIT 10
                """)
                instances = cursor.fetchall()

        conn.close()

        metrics_list = []
        for instance in instances:
            if not instance or instance['db_type'] != 'SQL Server':
                continue

            try:
                # 连接目标SQL Server实例
                conn_str = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                    f"SERVER={instance['db_ip']},{instance['db_port']};"
                    f"UID={instance['db_user']};"
                    f"PWD={instance['db_password']};"
                    f"Timeout=3;"
                )
                target_conn = pyodbc.connect(conn_str)
                cursor = target_conn.cursor()

                metrics = {
                    'instance_id': instance['id'],
                    'db_project': instance['db_project'],
                    'db_ip': instance['db_ip'],
                    'db_port': instance['db_port'],
                    'instance_name': instance['instance_name'] or f"{instance['db_ip']}:{instance['db_port']}"
                }

                # 获取性能计数器
                perf_query = """
                SELECT
                    counter_name,
                    cntr_value,
                    cntr_type
                FROM sys.dm_os_performance_counters
                WHERE (object_name LIKE '%General Statistics%' AND counter_name = 'User Connections')
                   OR (object_name LIKE '%SQL Statistics%' AND counter_name IN ('Batch Requests/sec', 'SQL Compilations/sec'))
                   OR (object_name LIKE '%Buffer Manager%' AND counter_name IN ('Buffer cache hit ratio', 'Page life expectancy', 'Buffer cache hit ratio base'))
                   OR (object_name LIKE '%Databases%' AND counter_name = 'Transactions/sec' AND instance_name = '_Total')
                """
                cursor.execute(perf_query)
                perf_counters = {row.counter_name: row.cntr_value for row in cursor.fetchall()}

                # 连接数
                metrics['current_connections'] = int(perf_counters.get('User Connections', 0))

                # 获取最大连接数
                cursor.execute("SELECT @@MAX_CONNECTIONS as max_conn")
                max_conn_row = cursor.fetchone()
                max_connections = max_conn_row.max_conn if max_conn_row else 32767
                metrics['max_connections'] = max_connections
                metrics['connection_usage'] = round(metrics['current_connections'] / max_connections * 100, 2) if max_connections > 0 else 0
                metrics['connection_warning'] = metrics['connection_usage'] > 80

                # Batch Requests/sec (类似QPS)
                metrics['batch_requests_per_sec'] = round(float(perf_counters.get('Batch Requests/sec', 0)), 2)

                # TPS
                metrics['tps'] = round(float(perf_counters.get('Transactions/sec', 0)), 2)

                # SQL编译次数/秒
                metrics['sql_compilations_per_sec'] = round(float(perf_counters.get('SQL Compilations/sec', 0)), 2)

                # Buffer Cache Hit Ratio (缓存命中率)
                buffer_hit = float(perf_counters.get('Buffer cache hit ratio', 0))
                buffer_hit_base = float(perf_counters.get('Buffer cache hit ratio base', 1))
                if buffer_hit_base > 0:
                    metrics['cache_hit_rate'] = round(buffer_hit / buffer_hit_base * 100, 2)
                else:
                    metrics['cache_hit_rate'] = 100
                metrics['cache_warning'] = metrics['cache_hit_rate'] < 90

                # Page Life Expectancy (页面生存期，秒)
                metrics['page_life_expectancy'] = int(perf_counters.get('Page life expectancy', 0))
                metrics['ple_warning'] = metrics['page_life_expectancy'] < 300  # <5分钟告警

                # CPU使用率
                cpu_query = """
                SELECT TOP 1
                    SQLProcessUtilization as sql_cpu,
                    100 - SystemIdle as total_cpu
                FROM (
                    SELECT
                        record.value('(./Record/@id)[1]', 'int') AS record_id,
                        record.value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int') AS SystemIdle,
                        record.value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]', 'int') AS SQLProcessUtilization,
                        DATEADD(ms, -1 * ((SELECT ms_ticks FROM sys.dm_os_sys_info) - timestamp), GETDATE()) AS EventTime
                    FROM (
                        SELECT timestamp, CONVERT(xml, record) AS record
                        FROM sys.dm_os_ring_buffers
                        WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
                        AND record LIKE '%<SystemHealth>%'
                    ) AS x
                ) AS y
                ORDER BY record_id DESC
                """
                cursor.execute(cpu_query)
                cpu_row = cursor.fetchone()
                if cpu_row:
                    metrics['sql_cpu_percent'] = cpu_row.sql_cpu
                    metrics['total_cpu_percent'] = cpu_row.total_cpu
                    metrics['cpu_warning'] = cpu_row.sql_cpu > 80
                else:
                    metrics['sql_cpu_percent'] = 0
                    metrics['total_cpu_percent'] = 0
                    metrics['cpu_warning'] = False

                # 内存使用情况
                memory_query = """
                SELECT
                    (total_physical_memory_kb / 1024) as total_memory_mb,
                    (available_physical_memory_kb / 1024) as available_memory_mb,
                    (total_physical_memory_kb - available_physical_memory_kb) * 100.0 / total_physical_memory_kb as memory_usage_percent
                FROM sys.dm_os_sys_memory
                """
                cursor.execute(memory_query)
                mem_row = cursor.fetchone()
                if mem_row:
                    metrics['total_memory_mb'] = int(mem_row.total_memory_mb)
                    metrics['available_memory_mb'] = int(mem_row.available_memory_mb)
                    metrics['memory_usage_percent'] = round(mem_row.memory_usage_percent, 2)
                    metrics['memory_warning'] = mem_row.memory_usage_percent > 90
                else:
                    metrics['total_memory_mb'] = 0
                    metrics['available_memory_mb'] = 0
                    metrics['memory_usage_percent'] = 0
                    metrics['memory_warning'] = False

                # 等待统计（Top 5）
                wait_query = """
                SELECT TOP 5
                    wait_type,
                    wait_time_ms / 1000.0 as wait_time_sec,
                    waiting_tasks_count
                FROM sys.dm_os_wait_stats
                WHERE wait_type NOT IN (
                    'CLR_SEMAPHORE', 'LAZYWRITER_SLEEP', 'RESOURCE_QUEUE', 'SLEEP_TASK',
                    'SLEEP_SYSTEMTASK', 'SQLTRACE_BUFFER_FLUSH', 'WAITFOR', 'LOGMGR_QUEUE',
                    'CHECKPOINT_QUEUE', 'REQUEST_FOR_DEADLOCK_SEARCH', 'XE_TIMER_EVENT',
                    'BROKER_TO_FLUSH', 'BROKER_TASK_STOP', 'CLR_MANUAL_EVENT',
                    'CLR_AUTO_EVENT', 'DISPATCHER_QUEUE_SEMAPHORE', 'FT_IFTS_SCHEDULER_IDLE_WAIT',
                    'XE_DISPATCHER_WAIT', 'XE_DISPATCHER_JOIN', 'SQLTRACE_INCREMENTAL_FLUSH_SLEEP'
                )
                ORDER BY wait_time_ms DESC
                """
                cursor.execute(wait_query)
                wait_stats = []
                for row in cursor.fetchall():
                    wait_stats.append({
                        'wait_type': row.wait_type,
                        'wait_time_sec': round(row.wait_time_sec, 2),
                        'waiting_tasks': row.waiting_tasks_count
                    })
                metrics['top_waits'] = wait_stats

                # 阻塞会话数量
                blocking_query = """
                SELECT COUNT(DISTINCT blocked.session_id) as blocked_count
                FROM sys.dm_exec_requests blocked
                WHERE blocked.blocking_session_id > 0
                """
                cursor.execute(blocking_query)
                blocked_row = cursor.fetchone()
                metrics['blocked_sessions'] = blocked_row.blocked_count if blocked_row else 0
                metrics['blocking_warning'] = metrics['blocked_sessions'] > 0

                metrics_list.append(metrics)

                cursor.close()
                target_conn.close()

            except Exception as e:
                logger.error(f"获取SQL Server实例{instance['db_project']}性能指标失败: {e}")
                continue

        return jsonify({'success': True, 'data': metrics_list})

    except Exception as e:
        logger.error(f"获取SQL Server性能指标失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/blocking_queries', methods=['GET'])
def get_blocking_queries():
    """获取阻塞查询（使用sys.innodb_lock_waits）"""
    try:
        instance_id = request.args.get('instance_id', type=int)
        min_wait_seconds = request.args.get('min_wait_seconds', 10, type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '监控数据库连接失败'}), 500

        # 获取实例列表
        with conn.cursor() as cursor:
            if instance_id:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE id = %s AND status = 1
                """, (instance_id,))
                instances = [cursor.fetchone()]
            else:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE status = 1
                """)
                instances = cursor.fetchall()

        conn.close()

        blocking_list = []
        for instance in instances:
            if not instance or instance['db_type'] != 'MySQL':
                continue

            try:
                target_conn = pymysql.connect(
                    host=instance['db_ip'],
                    port=instance['db_port'],
                    user=instance['db_user'],
                    password=instance['db_password'],
                    connect_timeout=3,
                    cursorclass=pymysql.cursors.DictCursor
                )

                with target_conn.cursor() as cursor:
                    # 检查MySQL版本，使用sys.innodb_lock_waits (MySQL 5.7+)
                    cursor.execute("SELECT VERSION() as version")
                    version_result = cursor.fetchone()
                    version = version_result['version'] if version_result else ''

                    # 尝试使用sys schema (MySQL 5.7+推荐方式)
                    try:
                        cursor.execute(f"""
                            SELECT
                                waiting_pid as blocked_thread,
                                waiting_query as blocked_sql,
                                blocking_pid as blocking_thread,
                                blocking_query as blocking_sql,
                                wait_age as wait_time,
                                sql_kill_blocking_query as kill_command
                            FROM sys.innodb_lock_waits
                            WHERE TIMESTAMPDIFF(SECOND, wait_started, NOW()) >= {min_wait_seconds}
                        """)
                        results = cursor.fetchall()

                        for row in results:
                            blocking_list.append({
                                'instance_id': instance['id'],
                                'db_project': instance['db_project'],
                                'db_ip': instance['db_ip'],
                                'db_port': instance['db_port'],
                                'blocked_thread': row['blocked_thread'],
                                'blocked_sql': row['blocked_sql'] or '',
                                'blocking_thread': row['blocking_thread'],
                                'blocking_sql': row['blocking_sql'] or '',
                                'wait_time': row['wait_time'],
                                'kill_command': row['kill_command'],
                                'detection_method': 'sys.innodb_lock_waits'
                            })

                    except Exception:
                        # 如果sys schema不可用，使用传统方式 (MySQL 5.6及以下)
                        cursor.execute(f"""
                            SELECT
                                r.trx_id waiting_trx_id,
                                r.trx_mysql_thread_id waiting_thread,
                                r.trx_query waiting_query,
                                b.trx_id blocking_trx_id,
                                b.trx_mysql_thread_id blocking_thread,
                                b.trx_query blocking_query,
                                TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) as wait_seconds
                            FROM information_schema.innodb_lock_waits w
                            INNER JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_trx_id
                            INNER JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_trx_id
                            WHERE TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) >= {min_wait_seconds}
                        """)
                        results = cursor.fetchall()

                        for row in results:
                            blocking_list.append({
                                'instance_id': instance['id'],
                                'db_project': instance['db_project'],
                                'db_ip': instance['db_ip'],
                                'db_port': instance['db_port'],
                                'blocked_thread': row['waiting_thread'],
                                'blocked_sql': row['waiting_query'] or '',
                                'blocking_thread': row['blocking_thread'],
                                'blocking_sql': row['blocking_query'] or '',
                                'wait_time': f"{row['wait_seconds']}秒",
                                'kill_command': f"KILL {row['blocking_thread']}",
                                'detection_method': 'information_schema.innodb_lock_waits'
                            })

                target_conn.close()

            except Exception as e:
                logger.error(f"获取实例{instance['db_project']}阻塞查询失败: {e}")
                continue

        return jsonify({
            'success': True,
            'data': blocking_list,
            'total_count': len(blocking_list)
        })

    except Exception as e:
        logger.error(f"获取阻塞查询失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/replication_status', methods=['GET'])
def get_replication_status():
    """获取主从复制状态"""
    try:
        instance_id = request.args.get('instance_id', type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '监控数据库连接失败'}), 500

        # 获取实例列表
        with conn.cursor() as cursor:
            if instance_id:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE id = %s AND status = 1
                """, (instance_id,))
                instances = [cursor.fetchone()]
            else:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE status = 1
                """)
                instances = cursor.fetchall()

        conn.close()

        replication_list = []
        for instance in instances:
            if not instance or instance['db_type'] != 'MySQL':
                continue

            try:
                target_conn = pymysql.connect(
                    host=instance['db_ip'],
                    port=instance['db_port'],
                    user=instance['db_user'],
                    password=instance['db_password'],
                    connect_timeout=3,
                    cursorclass=pymysql.cursors.DictCursor
                )

                with target_conn.cursor() as cursor:
                    # 检查是否配置了主从复制
                    cursor.execute("SHOW SLAVE STATUS")
                    slave_status = cursor.fetchone()

                    if slave_status:
                        replication_list.append({
                            'instance_id': instance['id'],
                            'db_project': instance['db_project'],
                            'db_ip': instance['db_ip'],
                            'db_port': instance['db_port'],
                            'master_host': slave_status.get('Master_Host'),
                            'master_port': slave_status.get('Master_Port'),
                            'slave_io_running': slave_status.get('Slave_IO_Running'),
                            'slave_sql_running': slave_status.get('Slave_SQL_Running'),
                            'seconds_behind_master': slave_status.get('Seconds_Behind_Master'),
                            'last_io_error': slave_status.get('Last_IO_Error') or '',
                            'last_sql_error': slave_status.get('Last_SQL_Error') or '',
                            'replication_healthy': (
                                slave_status.get('Slave_IO_Running') == 'Yes' and
                                slave_status.get('Slave_SQL_Running') == 'Yes' and
                                (slave_status.get('Seconds_Behind_Master') is not None and
                                 slave_status.get('Seconds_Behind_Master') < 60)
                            ),
                            'lag_warning': (
                                slave_status.get('Seconds_Behind_Master') is not None and
                                slave_status.get('Seconds_Behind_Master') > 10
                            )
                        })

                target_conn.close()

            except Exception as e:
                logger.error(f"获取实例{instance['db_project']}复制状态失败: {e}")
                continue

        return jsonify({
            'success': True,
            'data': replication_list,
            'total_count': len(replication_list)
        })

    except Exception as e:
        logger.error(f"获取复制状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alwayson_status', methods=['GET'])
def get_alwayson_status():
    """获取SQL Server Always On可用性组状态"""
    try:
        instance_id = request.args.get('instance_id', type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '监控数据库连接失败'}), 500

        # 获取实例列表
        with conn.cursor() as cursor:
            if instance_id:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE id = %s AND status = 1
                """, (instance_id,))
                instances = [cursor.fetchone()]
            else:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type, instance_name
                    FROM db_instance_info WHERE status = 1
                """)
                instances = cursor.fetchall()

        conn.close()

        alwayson_list = []
        for instance in instances:
            if not instance or instance['db_type'] not in ['SQLServer', 'SQL Server']:
                continue

            try:
                # 导入SQL Server采集器
                import sys
                sys.path.insert(0, 'scripts')
                from sqlserver_collector import SQLServerCollector

                collector = SQLServerCollector(instance)
                status_list = collector.get_alwayson_status()

                for status in status_list:
                    alwayson_list.append({
                        'instance_id': instance['id'],
                        'db_project': instance['db_project'],
                        'db_ip': instance['db_ip'],
                        'db_port': instance['db_port'],
                        'ag_name': status['ag_name'],
                        'replica_server': status['replica_server'],
                        'availability_mode': status['availability_mode'],
                        'failover_mode': status['failover_mode'],
                        'role': status['role'],
                        'connected_state': status['connected_state'],
                        'sync_health': status['sync_health'],
                        'database_name': status['database_name'],
                        'sync_state': status['sync_state'],
                        'db_sync_health': status['db_sync_health'],
                        'log_send_queue_kb': status['log_send_queue_kb'],
                        'log_send_rate_kb': status['log_send_rate_kb'],
                        'redo_queue_kb': status['redo_queue_kb'],
                        'redo_rate_kb': status['redo_rate_kb'],
                        'lag_seconds': status['lag_seconds'],
                        'is_suspended': status['is_suspended'],
                        'suspend_reason': status['suspend_reason'],
                        'is_healthy': status['is_healthy'],
                        'lag_warning': status['lag_seconds'] > 10  # 延迟超过10秒告警
                    })

            except Exception as e:
                logger.error(f"获取实例{instance['db_project']} Always On状态失败: {e}")
                continue

        return jsonify({
            'success': True,
            'data': alwayson_list,
            'total_count': len(alwayson_list)
        })

    except Exception as e:
        logger.error(f"获取Always On状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/realtime_sql', methods=['GET'])
def get_realtime_sql():
    """获取当前正在运行的SQL（实时）"""
    try:
        instance_id = request.args.get('instance_id', type=int)
        min_seconds = request.args.get('min_seconds', 5, type=int)

        # 获取监控数据库连接
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '监控数据库连接失败'}), 500

        # 获取实例列表
        with conn.cursor() as cursor:
            if instance_id:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type
                    FROM db_instance_info WHERE id = %s AND status = 1
                """, (instance_id,))
                instances = [cursor.fetchone()]
            else:
                cursor.execute("""
                    SELECT id, db_project, db_ip, db_port, db_user, db_password, db_type
                    FROM db_instance_info WHERE status = 1
                """)
                instances = cursor.fetchall()

        conn.close()

        # 收集所有实例的实时SQL
        all_sqls = []
        for instance in instances:
            if not instance:
                continue

            try:
                if instance['db_type'] == 'MySQL':
                    # 连接目标MySQL实例
                    target_conn = pymysql.connect(
                        host=instance['db_ip'],
                        port=instance['db_port'],
                        user=instance['db_user'],
                        password=instance['db_password'],
                        connect_timeout=3,
                        cursorclass=pymysql.cursors.DictCursor
                    )

                    with target_conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT
                                id as session_id,
                                user as username,
                                host as machine,
                                db as database_name,
                                command,
                                time as elapsed_seconds,
                                state,
                                info as sql_text
                            FROM information_schema.processlist
                            WHERE command != 'Sleep'
                              AND time >= %s
                              AND info IS NOT NULL
                              AND id != CONNECTION_ID()
                            ORDER BY time DESC
                        """, (min_seconds,))

                        results = cursor.fetchall()

                        for row in results:
                            all_sqls.append({
                                'session_id': str(row['session_id']),
                                'db_instance_id': instance['id'],
                                'db_project': instance['db_project'],
                                'db_ip': instance['db_ip'],
                                'db_port': instance['db_port'],
                                'db_type': instance['db_type'],
                                'username': row['username'],
                                'machine': row['machine'],
                                'database_name': row['database_name'],
                                'elapsed_seconds': row['elapsed_seconds'] or 0,
                                'status': row['state'] or 'ACTIVE',
                                'sql_text': row['sql_text'] or ''
                            })

                    target_conn.close()

                elif instance['db_type'] in ['SQLServer', 'SQL Server']:
                    # 连接目标SQL Server实例
                    import pyodbc
                    conn_str = (
                        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                        f"SERVER={instance['db_ip']},{instance['db_port']};"
                        f"UID={instance['db_user']};"
                        f"PWD={instance['db_password']};"
                        f"Encrypt=no;"
                        f"TrustServerCertificate=yes;"
                        f"Timeout=5;"
                    )
                    target_conn = pyodbc.connect(conn_str)
                    cursor = target_conn.cursor()

                    # 查询SQL Server的慢SQL（排除CDC和系统作业）
                    cursor.execute(f"""
                        SELECT
                            r.session_id,
                            DATEDIFF(SECOND, r.start_time, GETDATE()) as elapsed_seconds,
                            r.status,
                            r.command,
                            s.login_name as username,
                            s.host_name as machine,
                            DB_NAME(r.database_id) as database_name,
                            t.text as sql_text
                        FROM sys.dm_exec_requests r
                        LEFT JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
                        CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
                        WHERE r.session_id != @@SPID
                          AND DATEDIFF(SECOND, r.start_time, GETDATE()) >= {min_seconds}
                          AND t.text IS NOT NULL
                          AND t.text NOT LIKE '%sp_server_diagnostics%'
                          AND t.text NOT LIKE '%sp_cdc_%'
                          AND (s.program_name NOT LIKE '%SQLAgent%' OR s.program_name IS NULL)
                        ORDER BY elapsed_seconds DESC
                    """)

                    results = cursor.fetchall()

                    for row in results:
                        all_sqls.append({
                            'session_id': str(row.session_id),
                            'db_instance_id': instance['id'],
                            'db_project': instance['db_project'],
                            'db_ip': instance['db_ip'],
                            'db_port': instance['db_port'],
                            'db_type': instance['db_type'],
                            'username': row.username or '',
                            'machine': row.machine or '',
                            'database_name': row.database_name or '',
                            'elapsed_seconds': row.elapsed_seconds or 0,
                            'status': row.status or 'ACTIVE',
                            'sql_text': row.sql_text or ''
                        })

                    cursor.close()
                    target_conn.close()

            except Exception as e:
                logger.error(f"获取实例{instance['db_project']}实时SQL失败: {e}")
                continue

        # 统计信息
        total_count = len(all_sqls)
        max_seconds = max([sql['elapsed_seconds'] for sql in all_sqls]) if all_sqls else 0
        blocked_count = 0  # 暂不统计阻塞会话

        return jsonify({
            'success': True,
            'data': all_sqls,
            'stats': {
                'total_count': total_count,
                'max_seconds': max_seconds,
                'blocked_count': blocked_count
            }
        })

    except Exception as e:
        logger.error(f"获取实时SQL失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/kill_session', methods=['POST'])
def kill_session():
    """终止会话"""
    try:
        data = request.get_json()
        instance_id = data.get('instance_id')
        session_id = data.get('session_id')
        db_type = data.get('db_type', 'MySQL')

        if not instance_id or not session_id:
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400

        # 获取实例连接信息
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '监控数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT db_ip, db_port, db_user, db_password, db_type
                FROM db_instance_info WHERE id = %s
            """, (instance_id,))
            instance = cursor.fetchone()

        conn.close()

        if not instance:
            return jsonify({'success': False, 'error': '实例不存在'}), 404

        # 连接目标数据库并执行KILL
        if instance['db_type'] == 'MySQL':
            import pymysql
            target_conn = pymysql.connect(
                host=instance['db_ip'],
                port=instance['db_port'],
                user=instance['db_user'],
                password=instance['db_password'],
                connect_timeout=5
            )

            try:
                with target_conn.cursor() as cursor:
                    cursor.execute(f"KILL {session_id}")
                    target_conn.commit()

                logger.info(f"成功终止会话: {instance['db_ip']}:{instance['db_port']} Session#{session_id}")
                return jsonify({'success': True, 'message': f'会话 {session_id} 已成功终止'})
            finally:
                target_conn.close()

        elif instance['db_type'] == 'SQL Server':
            import pyodbc
            conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={instance['db_ip']},{instance['db_port']};UID={instance['db_user']};PWD={instance['db_password']};Encrypt=no;TrustServerCertificate=yes"
            target_conn = pyodbc.connect(conn_str, timeout=5)

            try:
                cursor = target_conn.cursor()
                cursor.execute(f"KILL {session_id}")
                target_conn.commit()

                logger.info(f"成功终止会话: {instance['db_ip']}:{instance['db_port']} SPID#{session_id}")
                return jsonify({'success': True, 'message': f'会话 {session_id} 已成功终止'})
            finally:
                target_conn.close()

        else:
            return jsonify({'success': False, 'error': f'不支持的数据库类型: {instance["db_type"]}'}), 400

    except Exception as e:
        logger.error(f"终止会话失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ Prometheus API ============
@app.route('/api/prometheus/metrics/<instance_ip>')
def prometheus_metrics(instance_ip):
    """获取指定实例的Prometheus指标"""
    try:
        config = load_config()
        prom_config = config.get('prometheus', {})

        # 检查Prometheus是否启用
        if not prom_config.get('enabled', False):
            return jsonify({'success': False, 'error': 'Prometheus未启用'}), 400

        # 创建Prometheus客户端
        prom_url = prom_config.get('url', 'http://192.168.98.4:9090')
        timeout = prom_config.get('timeout', 5)
        prom = PrometheusClient(prom_url, timeout)

        # 检查健康状态
        if not prom.check_health():
            return jsonify({'success': False, 'error': 'Prometheus服务不可用'}), 503

        # 获取实例指标
        metrics = prom.get_instance_metrics(instance_ip)

        return jsonify({
            'success': True,
            'data': metrics
        })

    except Exception as e:
        logger.error(f"获取Prometheus指标失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prometheus/trends/<instance_ip>')
def prometheus_trends(instance_ip):
    """获取指定实例的趋势数据"""
    try:
        config = load_config()
        prom_config = config.get('prometheus', {})

        if not prom_config.get('enabled', False):
            return jsonify({'success': False, 'error': 'Prometheus未启用'}), 400

        # 获取查询参数
        hours = request.args.get('hours', type=int, default=24)

        # 创建Prometheus客户端
        prom_url = prom_config.get('url', 'http://192.168.98.4:9090')
        timeout = prom_config.get('timeout', 5)
        prom = PrometheusClient(prom_url, timeout)

        # 获取趋势数据
        trends = prom.get_instance_trends(instance_ip, hours)

        return jsonify({
            'success': True,
            'data': trends
        })

    except Exception as e:
        logger.error(f"获取Prometheus趋势数据失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prometheus/query', methods=['POST'])
def prometheus_query():
    """执行自定义PromQL查询"""
    try:
        config = load_config()
        prom_config = config.get('prometheus', {})

        if not prom_config.get('enabled', False):
            return jsonify({'success': False, 'error': 'Prometheus未启用'}), 400

        # 获取查询参数
        data = request.get_json()
        promql = data.get('query')
        query_type = data.get('type', 'instant')  # instant 或 range

        if not promql:
            return jsonify({'success': False, 'error': '缺少查询语句'}), 400

        # 创建Prometheus客户端
        prom_url = prom_config.get('url', 'http://192.168.98.4:9090')
        timeout = prom_config.get('timeout', 5)
        prom = PrometheusClient(prom_url, timeout)

        # 执行查询
        if query_type == 'range':
            start = data.get('start')
            end = data.get('end')
            step = data.get('step', '15s')

            if not start or not end:
                return jsonify({'success': False, 'error': '范围查询需要start和end参数'}), 400

            result = prom.query_range(promql, start, end, step)
        else:
            result = prom.query(promql)

        if result:
            return jsonify({
                'success': True,
                'data': result
            })
        else:
            return jsonify({'success': False, 'error': '查询失败'}), 500

    except Exception as e:
        logger.error(f"执行Prometheus查询失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prometheus/health')
def prometheus_health():
    """检查Prometheus服务健康状态"""
    try:
        config = load_config()
        prom_config = config.get('prometheus', {})

        if not prom_config.get('enabled', False):
            return jsonify({
                'success': True,
                'enabled': False,
                'healthy': False,
                'message': 'Prometheus未启用'
            })

        prom_url = prom_config.get('url', 'http://192.168.98.4:9090')
        timeout = prom_config.get('timeout', 5)
        prom = PrometheusClient(prom_url, timeout)

        healthy = prom.check_health()

        return jsonify({
            'success': True,
            'enabled': True,
            'healthy': healthy,
            'url': prom_url
        })

    except Exception as e:
        logger.error(f"检查Prometheus健康状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prometheus/sqlserver/metrics/<instance_ip>')
def prometheus_sqlserver_metrics(instance_ip):
    """获取SQL Server实例的Prometheus指标"""
    try:
        config = load_config()
        prom_config = config.get('prometheus', {})

        # 检查Prometheus是否启用
        if not prom_config.get('enabled', False):
            return jsonify({'success': False, 'error': 'Prometheus未启用'}), 400

        # 创建Prometheus客户端
        prom_url = prom_config.get('url', 'http://192.168.98.4:9090')
        timeout = prom_config.get('timeout', 5)
        prom = PrometheusClient(prom_url, timeout)

        # 检查健康状态
        if not prom.check_health():
            return jsonify({'success': False, 'error': 'Prometheus服务不可用'}), 503

        # 获取SQL Server实例指标
        metrics = prom.get_sqlserver_instance_metrics(instance_ip)

        return jsonify({
            'success': True,
            'data': metrics
        })

    except Exception as e:
        logger.error(f"获取SQL Server Prometheus指标失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== DBA核心功能API ====================


# ==================== SQL指纹聚合API ====================

@app.route('/api/sql-fingerprint/stats')
def get_sql_fingerprint_stats():
    """获取SQL指纹统计数据"""
    try:
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 20, type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            # 获取指定时间范围内的SQL指纹统计
            sql = """
                SELECT
                    fps.fingerprint,
                    fps.sql_template,
                    fps.sql_type,
                    fps.tables_involved,
                    fps.occurrence_count,
                    fps.avg_elapsed_seconds,
                    fps.max_elapsed_seconds,
                    fps.avg_rows_examined,
                    fps.full_scan_count,
                    fps.has_index_suggestion,
                    fps.last_seen
                FROM sql_fingerprint_stats fps
                WHERE fps.last_seen >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY fps.occurrence_count DESC, fps.avg_elapsed_seconds DESC
                LIMIT %s
            """

            cursor.execute(sql, (hours, limit))
            results = cursor.fetchall()

            # 格式化日期时间
            for row in results:
                if isinstance(row.get('last_seen'), datetime):
                    row['last_seen'] = row['last_seen'].strftime('%Y-%m-%d %H:%M:%S')

            return jsonify({
                'success': True,
                'data': results,
                'total': len(results)
            })

    except Exception as e:
        logger.error(f"获取SQL指纹统计失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/sql-fingerprint/<fingerprint>/detail')
def get_fingerprint_detail(fingerprint):
    """获取特定SQL指纹的详细信息"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            # 获取指纹统计信息
            cursor.execute("""
                SELECT * FROM sql_fingerprint_stats
                WHERE fingerprint = %s
            """, (fingerprint,))
            stats = cursor.fetchone()

            if not stats:
                return jsonify({'success': False, 'error': '指纹不存在'}), 404

            # 获取最近的执行实例
            cursor.execute("""
                SELECT
                    l.id,
                    l.sql_text,
                    l.elapsed_seconds,
                    l.rows_examined,
                    l.detect_time,
                    i.db_project
                FROM long_running_sql_log l
                LEFT JOIN db_instance_info i ON l.db_instance_id = i.id
                WHERE l.sql_fingerprint = %s
                ORDER BY l.detect_time DESC
                LIMIT 10
            """, (fingerprint,))
            recent_sqls = cursor.fetchall()

            # 获取索引建议
            cursor.execute("""
                SELECT * FROM index_suggestion
                WHERE sql_fingerprint = %s AND status = 'pending'
                ORDER BY benefit_score DESC
            """, (fingerprint,))
            suggestions = cursor.fetchall()

            # 获取执行计划
            cursor.execute("""
                SELECT * FROM sql_execution_plan
                WHERE sql_fingerprint = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (fingerprint,))
            plan = cursor.fetchone()

            # 格式化日期时间
            for row in [stats] + recent_sqls + suggestions + ([plan] if plan else []):
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.strftime('%Y-%m-%d %H:%M:%S')

            return jsonify({
                'success': True,
                'data': {
                    'stats': stats,
                    'recent_sqls': recent_sqls,
                    'index_suggestions': suggestions,
                    'execution_plan': plan
                }
            })

    except Exception as e:
        logger.error(f"获取SQL指纹详情失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/sql-fingerprint/update', methods=['POST'])
def update_sql_fingerprint():
    """更新SQL指纹统计（由后台采集任务调用）"""
    try:
        data = request.get_json()
        sql_id = data.get('sql_id')

        if not sql_id:
            return jsonify({'success': False, 'error': '缺少sql_id参数'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            # 获取SQL信息
            cursor.execute("""
                SELECT sql_text, elapsed_seconds, rows_examined, full_table_scan
                FROM long_running_sql_log
                WHERE id = %s
            """, (sql_id,))
            sql_info = cursor.fetchone()

            if not sql_info:
                return jsonify({'success': False, 'error': 'SQL记录不存在'}), 404

            # 生成指纹
            sql_text = sql_info['sql_text']
            fingerprint = SQLFingerprint.generate(sql_text)
            sql_template = SQLFingerprint.normalize(sql_text)
            metadata = SQLFingerprint.extract_metadata(sql_text)

            # 更新long_running_sql_log表的指纹字段
            cursor.execute("""
                UPDATE long_running_sql_log
                SET sql_fingerprint = %s
                WHERE id = %s
            """, (fingerprint, sql_id))

            # 更新或插入指纹统计
            cursor.execute("""
                INSERT INTO sql_fingerprint_stats (
                    fingerprint, sql_template, sql_type, tables_involved,
                    first_seen, last_seen, occurrence_count,
                    total_elapsed_seconds, avg_elapsed_seconds,
                    max_elapsed_seconds, min_elapsed_seconds,
                    total_rows_examined, avg_rows_examined,
                    full_scan_count
                ) VALUES (
                    %s, %s, %s, %s, NOW(), NOW(), 1,
                    %s, %s, %s, %s, %s, %s, %s
                ) ON DUPLICATE KEY UPDATE
                    last_seen = NOW(),
                    occurrence_count = occurrence_count + 1,
                    total_elapsed_seconds = total_elapsed_seconds + %s,
                    avg_elapsed_seconds = (total_elapsed_seconds + %s) / (occurrence_count + 1),
                    max_elapsed_seconds = GREATEST(max_elapsed_seconds, %s),
                    min_elapsed_seconds = LEAST(min_elapsed_seconds, %s),
                    total_rows_examined = total_rows_examined + %s,
                    avg_rows_examined = (total_rows_examined + %s) / (occurrence_count + 1),
                    full_scan_count = full_scan_count + %s
            """, (
                fingerprint, sql_template, metadata['sql_type'],
                ','.join(metadata['tables']),
                sql_info['elapsed_seconds'], sql_info['elapsed_seconds'],
                sql_info['elapsed_seconds'], sql_info['elapsed_seconds'],
                sql_info['rows_examined'] or 0, sql_info['rows_examined'] or 0,
                1 if sql_info['full_table_scan'] else 0,
                # ON DUPLICATE KEY UPDATE部分
                sql_info['elapsed_seconds'], sql_info['elapsed_seconds'],
                sql_info['elapsed_seconds'], sql_info['elapsed_seconds'],
                sql_info['rows_examined'] or 0, sql_info['rows_examined'] or 0,
                1 if sql_info['full_table_scan'] else 0
            ))

            conn.commit()

            return jsonify({
                'success': True,
                'fingerprint': fingerprint,
                'sql_template': sql_template
            })

    except Exception as e:
        logger.error(f"更新SQL指纹失败: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()




# ==================== SQL执行计划分析API ====================

@app.route('/api/sql-explain/analyze', methods=['POST'])
def analyze_sql_explain():
    """分析SQL执行计划"""
    conn = None
    target_conn = None
    try:
        data = request.get_json()
        sql_text = data.get('sql_text')
        db_instance_id = data.get('db_instance_id')

        if not sql_text or not db_instance_id:
            return jsonify({'success': False, 'error': '缺少必需参数'}), 400

        # 获取实例信息
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM db_instance_info WHERE id = %s
            """, (db_instance_id,))
            instance = cursor.fetchone()

            if not instance:
                return jsonify({'success': False, 'error': '实例不存在'}), 404

        # 连接到目标数据库
        # 如果没有指定数据库，MySQL连接到information_schema，SQLServer连接到master
        db_name = instance.get('db_name') or ('information_schema' if instance['db_type'] == 'MySQL' else 'master')
        target_conn = pymysql.connect(
            host=instance['db_ip'],
            port=instance['db_port'],
            user=instance['db_user'],
            password=instance['db_password'],
            database=db_name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        try:
            # 执行分析
            analyzer = SQLExplainAnalyzer(target_conn)
            result = analyzer.analyze_sql(sql_text, instance['db_type'])

            if result['success']:
                # 保存分析结果
                fingerprint = SQLFingerprint.generate(sql_text)

                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO sql_execution_plan (
                            sql_fingerprint, db_instance_id,
                            plan_json, has_full_scan, has_temp_table, has_filesort,
                            estimated_rows, analysis_result
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        fingerprint, db_instance_id,
                        json.dumps(result.get('plan_json', {})),
                        1 if result['has_full_scan'] else 0,
                        1 if result['has_temp_table'] else 0,
                        1 if result['has_filesort'] else 0,
                        sum(i.get('rows', 0) for i in result.get('issues', [])),
                        json.dumps(result.get('issues', []))
                    ))

                    plan_id = cursor.lastrowid

                    # 保存索引建议
                    for suggestion in result.get('index_suggestions', []):
                        cursor.execute("""
                            INSERT INTO index_suggestion (
                                sql_fingerprint, db_instance_id,
                                table_name, suggested_columns,
                                create_statement, benefit_score
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            fingerprint, db_instance_id,
                            suggestion.get('table', ''),
                            ','.join(suggestion.get('columns', [])),
                            suggestion.get('create_statement', ''),
                            80.0 if suggestion['type'] == 'CREATE_INDEX' else 60.0
                        ))

                    conn.commit()

                # 生成报告
                report = analyzer.generate_optimization_report(result)

                return jsonify({
                    'success': True,
                    'plan_id': plan_id,
                    'analysis': result,
                    'report': report
                })
            else:
                return jsonify(result), 500

        finally:
            if target_conn:
                target_conn.close()

    except Exception as e:
        logger.error(f"分析SQL执行计划失败: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/sql-explain/batch-analyze', methods=['POST'])
def batch_analyze_sql_explain():
    """批量分析慢SQL的执行计划"""
    try:
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 50, type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            # 获取未分析的慢SQL
            cursor.execute("""
                SELECT DISTINCT
                    l.id, l.sql_text, l.sql_fingerprint, l.db_instance_id
                FROM long_running_sql_log l
                LEFT JOIN sql_execution_plan p ON l.sql_fingerprint = p.sql_fingerprint
                WHERE l.detect_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                  AND l.elapsed_seconds > 1
                  AND p.id IS NULL
                ORDER BY l.elapsed_seconds DESC
                LIMIT %s
            """, (hours, limit))

            sqls = cursor.fetchall()

        analyzed_count = 0
        failed_count = 0
        results = []

        for sql_record in sqls:
            try:
                # 调用单个分析API
                analyze_result = analyze_sql_explain_internal(
                    sql_record['sql_text'],
                    sql_record['db_instance_id']
                )

                if analyze_result['success']:
                    analyzed_count += 1
                    results.append({
                        'sql_id': sql_record['id'],
                        'fingerprint': sql_record['sql_fingerprint'],
                        'status': 'success',
                        'issues_count': len(analyze_result.get('analysis', {}).get('issues', []))
                    })
                else:
                    failed_count += 1
                    results.append({
                        'sql_id': sql_record['id'],
                        'status': 'failed',
                        'error': analyze_result.get('error')
                    })

            except Exception as e:
                failed_count += 1
                results.append({
                    'sql_id': sql_record['id'],
                    'status': 'failed',
                    'error': str(e)
                })

        return jsonify({
            'success': True,
            'total': len(sqls),
            'analyzed': analyzed_count,
            'failed': failed_count,
            'results': results
        })

    except Exception as e:
        logger.error(f"批量分析SQL执行计划失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def analyze_sql_explain_internal(sql_text, db_instance_id):
    """内部调用的分析函数（不返回Flask Response）"""
    conn = None
    target_conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return {'success': False, 'error': '数据库连接失败'}

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM db_instance_info WHERE id = %s", (db_instance_id,))
            instance = cursor.fetchone()

        if not instance:
            return {'success': False, 'error': '实例不存在'}

        # 如果没有指定数据库，MySQL连接到information_schema，SQLServer连接到master
        db_name = instance.get('db_name') or ('information_schema' if instance['db_type'] == 'MySQL' else 'master')
        target_conn = pymysql.connect(
            host=instance['db_ip'],
            port=instance['db_port'],
            user=instance['db_user'],
            password=instance['db_password'],
            database=db_name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        analyzer = SQLExplainAnalyzer(target_conn)
        result = analyzer.analyze_sql(sql_text, instance['db_type'])

        if result['success']:
            # 保存结果到数据库...
            pass

        return result

    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        if target_conn:
            target_conn.close()
        if conn:
            conn.close()


@app.route('/api/index-suggestions')
def get_index_suggestions():
    """获取索引建议列表"""
    try:
        status = request.args.get('status', 'pending')
        limit = request.args.get('limit', 20, type=int)

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    s.*,
                    i.db_project,
                    fps.occurrence_count,
                    fps.avg_elapsed_seconds
                FROM index_suggestion s
                LEFT JOIN db_instance_info i ON s.db_instance_id = i.id
                LEFT JOIN sql_fingerprint_stats fps ON s.sql_fingerprint = fps.fingerprint
                WHERE s.status = %s
                ORDER BY s.benefit_score DESC, fps.occurrence_count DESC
                LIMIT %s
            """, (status, limit))

            suggestions = cursor.fetchall()

            # 格式化日期时间
            for row in suggestions:
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.strftime('%Y-%m-%d %H:%M:%S')

            return jsonify({
                'success': True,
                'data': suggestions,
                'total': len(suggestions)
            })

    except Exception as e:
        logger.error(f"获取索引建议失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/index-suggestions/<int:suggestion_id>/apply', methods=['POST'])
def apply_index_suggestion(suggestion_id):
    """应用索引建议（执行CREATE INDEX语句）"""
    conn = None
    target_conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': '数据库连接失败'}), 500

        with conn.cursor() as cursor:
            # 获取索引建议
            cursor.execute("""
                SELECT s.*, i.* FROM index_suggestion s
                LEFT JOIN db_instance_info i ON s.db_instance_id = i.id
                WHERE s.id = %s
            """, (suggestion_id,))
            suggestion = cursor.fetchone()

            if not suggestion:
                return jsonify({'success': False, 'error': '建议不存在'}), 404

            if suggestion['status'] != 'pending':
                return jsonify({'success': False, 'error': '该建议已处理'}), 400

        # 连接到目标数据库执行CREATE INDEX
        # 如果没有指定数据库，MySQL连接到information_schema，SQLServer连接到master
        db_name = suggestion.get('db_name') or ('information_schema' if suggestion['db_type'] == 'MySQL' else 'master')
        target_conn = pymysql.connect(
            host=suggestion['db_ip'],
            port=suggestion['db_port'],
            user=suggestion['db_user'],
            password=suggestion['db_password'],
            database=db_name,
            charset='utf8mb4'
        )

        try:
            with target_conn.cursor() as target_cursor:
                # 执行CREATE INDEX
                create_statement = suggestion['create_statement']
                target_cursor.execute(create_statement)
                target_conn.commit()

            # 更新状态
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE index_suggestion
                    SET status = 'applied', applied_at = NOW()
                    WHERE id = %s
                """, (suggestion_id,))
                conn.commit()

            return jsonify({
                'success': True,
                'message': '索引创建成功',
                'create_statement': create_statement
            })

        finally:
            if target_conn:
                target_conn.close()

    except Exception as e:
        logger.error(f"应用索引建议失败: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Not Found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 后台采集器定时任务 ====================

def run_mysql_collector():
    """MySQL Performance Schema 采集器"""
    try:
        config = load_config()
        mysql_config = config.get('collectors', {}).get('mysql', {})

        if not mysql_config.get('enabled', True):
            logger.debug("MySQL采集器已禁用，跳过本次采集")
            return

        threshold = mysql_config.get('threshold', 5)

        from scripts.mysql_perfschema_collector import MySQLPerfSchemaCollector, get_mysql_instances

        instances = get_mysql_instances()
        total_saved = 0

        for instance in instances:
            try:
                collector = MySQLPerfSchemaCollector(instance, threshold_seconds=threshold)
                saved = collector.collect()
                total_saved += saved
            except Exception as e:
                logger.error(f"MySQL采集失败 {instance.get('db_project')}: {e}")

        if total_saved > 0:
            logger.info(f"MySQL采集完成: {total_saved} 条慢SQL (阈值: {threshold}秒)")
    except Exception as e:
        logger.error(f"MySQL采集器异常: {e}")


def run_sqlserver_collector():
    """SQL Server Query Store 采集器 (过滤CDC作业)"""
    try:
        config = load_config()
        sqlserver_config = config.get('collectors', {}).get('sqlserver', {})

        if not sqlserver_config.get('enabled', True):
            logger.debug("SQL Server采集器已禁用，跳过本次采集")
            return

        threshold = sqlserver_config.get('threshold', 5)
        auto_enable = sqlserver_config.get('auto_enable_querystore', False)

        from scripts.sqlserver_querystore_collector import SQLServerQueryStoreCollector, get_sqlserver_instances

        instances = get_sqlserver_instances()
        total_saved = 0

        for instance in instances:
            try:
                collector = SQLServerQueryStoreCollector(instance, threshold_seconds=threshold)
                saved = collector.collect(auto_enable_querystore=auto_enable)
                total_saved += saved
            except Exception as e:
                logger.error(f"SQL Server采集失败 {instance.get('db_project')}: {e}")

        if total_saved > 0:
            logger.info(f"SQL Server采集完成: {total_saved} 条慢SQL (阈值: {threshold}秒)")
    except Exception as e:
        logger.error(f"SQL Server采集器异常: {e}")


def run_deadlock_collector():
    """SQL Server死锁检测器"""
    try:
        config = load_config()
        deadlock_config = config.get('collectors', {}).get('deadlock', {})

        if not deadlock_config.get('enabled', True):
            logger.debug("死锁检测器已禁用，跳过本次检测")
            return

        logger.info("开始SQL Server死锁检测...")
        collect_all_sqlserver_deadlocks(config['database'])
        logger.info("SQL Server死锁检测完成")

    except Exception as e:
        logger.error(f"死锁检测器异常: {e}")


# 创建后台调度器
scheduler = BackgroundScheduler()

def init_scheduler():
    """初始化调度器，从配置读取间隔"""
    config = load_config()
    collectors_config = config.get('collectors', {})

    mysql_config = collectors_config.get('mysql', {})
    if mysql_config.get('enabled', True):
        interval = mysql_config.get('interval', 60)
        scheduler.add_job(func=run_mysql_collector, trigger="interval", seconds=interval,
                         id="mysql_collector", replace_existing=True)
        logger.info(f"MySQL采集器已启动，间隔: {interval}秒")

    sqlserver_config = collectors_config.get('sqlserver', {})
    if sqlserver_config.get('enabled', True):
        interval = sqlserver_config.get('interval', 60)
        scheduler.add_job(func=run_sqlserver_collector, trigger="interval", seconds=interval,
                         id="sqlserver_collector", replace_existing=True)
        logger.info(f"SQL Server采集器已启动，间隔: {interval}秒")

    deadlock_config = collectors_config.get('deadlock', {})
    if deadlock_config.get('enabled', True):
        interval = deadlock_config.get('interval', 300)  # 默认5分钟
        scheduler.add_job(func=run_deadlock_collector, trigger="interval", seconds=interval,
                         id="deadlock_collector", replace_existing=True)
        logger.info(f"死锁检测器已启动，间隔: {interval}秒")

def update_collector_schedule(collector_type, enabled, interval):
    """动态更新采集器调度"""
    job_id = f"{collector_type}_collector"

    if not enabled:
        # 禁用采集器 - 移除任务
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"{collector_type}采集器已禁用")
    else:
        # 启用采集器 - 添加或更新任务
        func = run_mysql_collector if collector_type == 'mysql' else run_sqlserver_collector
        scheduler.add_job(func=func, trigger="interval", seconds=interval,
                         id=job_id, replace_existing=True)
        logger.info(f"{collector_type}采集器已更新，间隔: {interval}秒")

# 注册退出时关闭调度器
atexit.register(lambda: scheduler.shutdown())


if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    os.makedirs('templates', exist_ok=True)

    # 初始化数据库连接池
    init_db_pool()

    print("=" * 50)
    print("数据库SQL监控系统 v1.3.0")
    print("=" * 50)
    print(f"访问: http://localhost:5000")
    print(f"配置: {CONFIG_FILE}")
    print("=" * 50)
    print("优化特性:")
    print("  [OK] 数据库连接池 (最大20个连接)")
    print("  [OK] 配置缓存 (60秒自动刷新)")
    print("  [OK] Prometheus监控 (MySQL + SQL Server)")
    print("=" * 50)
    print("后台采集器:")
    print("  [OK] MySQL Performance Schema 采集器 (60秒/次)")
    print("  [OK] SQL Server Query Store 采集器 (60秒/次)")
    print("  [OK] 自动过滤CDC作业和系统SQL")
    print("=" * 50)

    # 初始化并启动后台采集调度器
    init_scheduler()
    scheduler.start()
    logger.info("后台采集调度器已启动")

    # 立即执行一次采集
    config = load_config()
    collectors_config = config.get('collectors', {})
    logger.info("执行首次采集...")
    if collectors_config.get('mysql', {}).get('enabled', True):
        run_mysql_collector()
    if collectors_config.get('sqlserver', {}).get('enabled', True):
        run_sqlserver_collector()

    # 启动Flask应用
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
