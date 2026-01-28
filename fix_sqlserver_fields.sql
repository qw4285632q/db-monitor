-- 为SQL Server监控添加缺失的字段

USE db_monitor;

-- 添加 wait_type 字段
ALTER TABLE long_running_sql_log
ADD COLUMN wait_type VARCHAR(100) COMMENT '等待类型' AFTER blocking_session;

-- 添加 wait_resource 字段
ALTER TABLE long_running_sql_log
ADD COLUMN wait_resource VARCHAR(200) COMMENT '等待资源' AFTER wait_type;

-- 添加 query_cost 字段
ALTER TABLE long_running_sql_log
ADD COLUMN query_cost DECIMAL(15,4) COMMENT '查询成本' AFTER rows_sent;

-- 为这些字段添加索引
ALTER TABLE long_running_sql_log ADD INDEX idx_wait_type (wait_type);

SELECT 'SQL Server监控字段添加完成' as result;
