-- ============================================
-- 数据库Long SQL监控系统 - 数据库初始化脚本
-- ============================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS db_monitor
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE db_monitor;

-- ============================================
-- 表1: 数据库实例信息表
-- ============================================
DROP TABLE IF EXISTS db_instance_info;
CREATE TABLE db_instance_info (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    db_project VARCHAR(100) NOT NULL COMMENT '项目名称',
    db_ip VARCHAR(50) NOT NULL COMMENT '数据库IP地址',
    db_port INT DEFAULT 3306 COMMENT '数据库端口',
    instance_name VARCHAR(100) COMMENT '实例名称',
    db_type VARCHAR(20) DEFAULT 'MySQL' COMMENT '数据库类型(Oracle/MySQL/PostgreSQL)',
    db_user VARCHAR(50) COMMENT '数据库用户',
    db_password VARCHAR(200) COMMENT '数据库密码(加密存储)',
    db_admin VARCHAR(50) COMMENT '数据库管理员',
    db_version VARCHAR(50) COMMENT '数据库版本',
    environment VARCHAR(20) DEFAULT 'production' COMMENT '环境(production/staging/development)',
    status TINYINT DEFAULT 1 COMMENT '状态(1:启用 0:禁用)',
    description TEXT COMMENT '描述信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    INDEX idx_db_project (db_project),
    INDEX idx_db_ip (db_ip),
    INDEX idx_db_type (db_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据库实例信息表';

-- ============================================
-- 表2: 长时间运行SQL日志表
-- ============================================
DROP TABLE IF EXISTS long_running_sql_log;
CREATE TABLE long_running_sql_log (
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
    full_table_scan TINYINT DEFAULT 0 COMMENT '是否全表扫描(0:否 1:是)',
    status VARCHAR(50) DEFAULT 'ACTIVE' COMMENT '状态(ACTIVE/INACTIVE/KILLED)',
    blocking_session VARCHAR(50) COMMENT '阻塞会话ID',
    wait_type VARCHAR(100) COMMENT '等待类型',
    wait_resource VARCHAR(200) COMMENT '等待资源',
    event VARCHAR(200) COMMENT '等待事件',
    sql_exec_start DATETIME COMMENT 'SQL执行开始时间',
    detect_time DATETIME NOT NULL COMMENT '检测时间',
    alert_sent TINYINT DEFAULT 0 COMMENT '是否已发送告警(0:否 1:是)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',

    INDEX idx_db_instance_id (db_instance_id),
    INDEX idx_detect_time (detect_time),
    INDEX idx_elapsed_minutes (elapsed_minutes),
    INDEX idx_username (username),
    INDEX idx_status (status),
    INDEX idx_session_id (session_id),
    INDEX idx_sql_fingerprint (sql_fingerprint),
    INDEX idx_full_table_scan (full_table_scan),
    INDEX idx_alert_sent (alert_sent),

    FOREIGN KEY (db_instance_id) REFERENCES db_instance_info(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='长时间运行SQL日志表';

-- ============================================
-- 表2.5: 死锁监控日志表
-- ============================================
DROP TABLE IF EXISTS deadlock_log;
CREATE TABLE deadlock_log (
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
    resolved_action VARCHAR(100) COMMENT '解决动作(ROLLBACK/KILLED/TIMEOUT)',
    detect_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '检测时间',
    alert_sent TINYINT DEFAULT 0 COMMENT '是否已发送告警',
    alert_sent_time DATETIME COMMENT '告警发送时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    INDEX idx_db_instance_id (db_instance_id),
    INDEX idx_deadlock_time (deadlock_time),
    INDEX idx_detect_time (detect_time),
    INDEX idx_alert_sent (alert_sent),

    FOREIGN KEY (db_instance_id) REFERENCES db_instance_info(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='死锁监控日志表';

-- ============================================
-- 表3: 监控告警配置表
-- ============================================
DROP TABLE IF EXISTS monitor_alert_config;
CREATE TABLE monitor_alert_config (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控告警配置表';

-- ============================================
-- 表4: 告警历史记录表
-- ============================================
DROP TABLE IF EXISTS alert_history;
CREATE TABLE alert_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    db_instance_id INT NOT NULL COMMENT '数据库实例ID',
    alert_type VARCHAR(50) NOT NULL COMMENT '告警类型(slow_sql/deadlock)',
    alert_identifier VARCHAR(200) COMMENT '告警标识符(SQL指纹/死锁时间)',
    sql_log_id BIGINT COMMENT '关联的SQL日志ID',
    alert_level VARCHAR(20) NOT NULL COMMENT '告警级别(WARNING/CRITICAL)',
    alert_message TEXT COMMENT '告警消息',
    is_acknowledged TINYINT DEFAULT 0 COMMENT '是否已确认',
    acknowledged_by VARCHAR(50) COMMENT '确认人',
    acknowledged_at DATETIME COMMENT '确认时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    INDEX idx_db_instance_id (db_instance_id),
    INDEX idx_alert_type (alert_type),
    INDEX idx_alert_identifier (alert_identifier),
    INDEX idx_alert_level (alert_level),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='告警历史记录表';

-- ============================================
-- 插入默认告警配置
-- ============================================
INSERT INTO monitor_alert_config (alert_name, alert_type, threshold_warning, threshold_critical, is_enabled)
VALUES
('长时间SQL告警', 'long_running_sql', 5.0, 10.0, 1),
('会话阻塞告警', 'session_blocking', 3.0, 5.0, 1);

-- ============================================
-- 创建清理历史数据的存储过程
-- ============================================
DELIMITER //

CREATE PROCEDURE IF NOT EXISTS cleanup_old_data(IN days_to_keep INT)
BEGIN
    DECLARE deleted_count INT DEFAULT 0;

    -- 删除旧的SQL日志
    DELETE FROM long_running_sql_log
    WHERE detect_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    SET deleted_count = ROW_COUNT();

    -- 删除旧的死锁日志
    DELETE FROM deadlock_log
    WHERE detect_time < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    SET deleted_count = deleted_count + ROW_COUNT();

    -- 删除旧的告警历史
    DELETE FROM alert_history
    WHERE created_at < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);

    SET deleted_count = deleted_count + ROW_COUNT();

    SELECT CONCAT('清理完成，共删除 ', deleted_count, ' 条记录') AS result;
END //

DELIMITER ;

-- ============================================
-- 创建统计视图
-- ============================================
CREATE OR REPLACE VIEW v_sql_statistics AS
SELECT
    i.id AS instance_id,
    i.db_project,
    i.db_ip,
    i.instance_name,
    COUNT(l.id) AS total_sql_count,
    AVG(l.elapsed_minutes) AS avg_duration,
    MAX(l.elapsed_minutes) AS max_duration,
    SUM(CASE WHEN l.elapsed_minutes > 10 THEN 1 ELSE 0 END) AS critical_count,
    SUM(CASE WHEN l.elapsed_minutes > 5 AND l.elapsed_minutes <= 10 THEN 1 ELSE 0 END) AS warning_count,
    SUM(CASE WHEN l.elapsed_minutes <= 5 THEN 1 ELSE 0 END) AS normal_count
FROM db_instance_info i
LEFT JOIN long_running_sql_log l ON i.id = l.db_instance_id
    AND l.detect_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
WHERE i.status = 1
GROUP BY i.id, i.db_project, i.db_ip, i.instance_name;

-- 显示创建结果
SELECT 'Database initialization completed successfully!' AS status;
SHOW TABLES;
