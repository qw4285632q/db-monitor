"""
SQL执行计划分析API端点
将这些代码插入到app_new.py中
"""

from scripts.sql_explain_analyzer import SQLExplainAnalyzer

# ==================== SQL执行计划分析API ====================

@app.route('/api/sql-explain/analyze', methods=['POST'])
def analyze_sql_explain():
    """分析SQL执行计划"""
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
        target_conn = pymysql.connect(
            host=instance['db_ip'],
            port=instance['db_port'],
            user=instance['db_user'],
            password=instance['db_password'],
            database=instance['db_name'],
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
            target_conn.close()

    except Exception as e:
        logger.error(f"分析SQL执行计划失败: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/sql-explain/batch-analyze', methods='POST'])
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
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM db_instance_info WHERE id = %s", (db_instance_id,))
            instance = cursor.fetchone()

        if not instance:
            return {'success': False, 'error': '实例不存在'}

        target_conn = pymysql.connect(
            host=instance['db_ip'],
            port=instance['db_port'],
            user=instance['db_user'],
            password=instance['db_password'],
            database=instance['db_name'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        analyzer = SQLExplainAnalyzer(target_conn)
        result = analyzer.analyze_sql(sql_text, instance['db_type'])
        target_conn.close()

        if result['success']:
            # 保存结果到数据库...
            pass

        return result

    except Exception as e:
        return {'success': False, 'error': str(e)}


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
        target_conn = pymysql.connect(
            host=suggestion['db_ip'],
            port=suggestion['db_port'],
            user=suggestion['db_user'],
            password=suggestion['db_password'],
            database=suggestion['db_name'],
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
            target_conn.close()

    except Exception as e:
        logger.error(f"应用索引建议失败: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()
