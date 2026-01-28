"""
SQL指纹聚合API端点
将这些代码插入到app_new.py的errorhandler之后
"""

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
