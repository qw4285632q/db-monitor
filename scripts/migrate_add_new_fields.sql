-- Migration script: Add new fields for enhanced monitoring features
-- Run this script on your monitor database to add missing fields

USE mysql_monitor;

-- Check and add missing fields to long_running_sql_log table
ALTER TABLE long_running_sql_log
ADD COLUMN IF NOT EXISTS sql_fingerprint VARCHAR(64) COMMENT 'SQL指纹(MD5)' AFTER sql_id;

ALTER TABLE long_running_sql_log
ADD COLUMN IF NOT EXISTS sql_fulltext LONGTEXT COMMENT 'SQL完整文本' AFTER sql_text;

ALTER TABLE long_running_sql_log
ADD COLUMN IF NOT EXISTS execution_plan JSON COMMENT '执行计划(JSON格式)' AFTER query_cost;

ALTER TABLE long_running_sql_log
ADD COLUMN IF NOT EXISTS cpu_time DECIMAL(15,2) COMMENT 'CPU时间(秒)' AFTER elapsed_minutes;

ALTER TABLE long_running_sql_log
ADD COLUMN IF NOT EXISTS rows_examined BIGINT COMMENT '扫描行数' AFTER physical_reads;

-- Check and add missing fields to alert_history table
ALTER TABLE alert_history
ADD COLUMN IF NOT EXISTS alert_type VARCHAR(50) NOT NULL COMMENT '告警类型(slow_sql/deadlock)' AFTER db_instance_id;

ALTER TABLE alert_history
ADD COLUMN IF NOT EXISTS alert_identifier VARCHAR(200) COMMENT '告警标识符(SQL指纹/死锁时间)' AFTER alert_type;

-- Add indexes if not exist
ALTER TABLE alert_history
ADD INDEX IF NOT EXISTS idx_alert_type (alert_type);

ALTER TABLE alert_history
ADD INDEX IF NOT EXISTS idx_alert_identifier (alert_identifier);

SELECT '✓ Migration completed successfully!' as status;
