# -*- coding: utf-8 -*-
"""教师端蓝图"""
import io

from flask import Blueprint, request, jsonify, session, send_file

from core import (CURRENT_SEMESTER, query_one, query_all, execute, get_db_connection, safe_cell,
                  fmt_rows, parse_score, calc_grade, log_operation, role_required,
                  _read_uploaded_table, export_schedule_xlsx)
from enrollment_sync import ensure_offering_enrollments

teacher_bp = Blueprint('teacher', __name__)


def _heal_offering_enrollments(offering_id):
    """教师查看名单/成绩前自愈：补齐本班统排课（非选修）学生的 enrollment。

    成绩录入/导入/名单/模板等接口只从 enrollment 取学生，而班级统排课
    （offering_class 指定班级的必修/通识/实践）可能尚未落成选课记录，
    导致教师看不到学生。这里做一次幂等补齐；失败只打印日志，不阻断正常查询。
    """
    try:
        ensure_offering_enrollments(offering_id)
    except Exception as e:
        print(f'[警告] 教师端名单自愈失败(offering_id={offering_id}): {e}')


@teacher_bp.route('/api/teacher/profile')
@role_required('teacher')
def tea_profile():
    tea = query_one("""SELECT t.*, c.name AS college_name FROM teacher t
                       LEFT JOIN college c ON t.college_id=c.id WHERE t.id=%s""", (session['user_id'],))
    tea.pop('password_hash', None)
    row = fmt_rows([tea])[0]
    if row.get('avatar'):
        row['avatar'] = f"/uploads/avatar/{row['avatar']}"
    return jsonify({'success': True, 'data': row})


@teacher_bp.route('/api/teacher/offerings')
@role_required('teacher')
def tea_offerings():
    semester = request.args.get('semester', CURRENT_SEMESTER)
    rows = query_all("""
        SELECT co.id, c.code, c.name AS course_name, c.credit, c.hours, c.type,
               co.semester, co.max_count, co.selected_count, co.status,
               co.usual_ratio, co.exam_ratio
        FROM course_offering co JOIN course c ON co.course_id=c.id
        WHERE co.teacher_id=%s AND co.semester=%s ORDER BY c.code""", (session['user_id'], semester))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


# ---------- 成绩计算辅助 ----------

def _ratio_of(offering, key, default):
    """取成绩比例：注意 0 是合法值（如"平时 0% / 考试 100%"），不能被 or 吞掉"""
    v = offering.get(key)
    return default if v is None else int(v)


def _recalc_totals(cursor, offering_id, usual_ratio, exam_ratio):
    """按新比例重算该教学班已录成绩的总评与绩点，避免存量成绩与当前比例不一致"""
    cursor.execute("""SELECT id, usual_score, exam_score FROM enrollment
                      WHERE offering_id=%s AND status='已选'
                        AND usual_score IS NOT NULL AND exam_score IS NOT NULL""", (offering_id,))
    rows = cursor.fetchall()
    for r in rows:
        total, point = calc_grade(float(r['usual_score']), float(r['exam_score']), usual_ratio, exam_ratio)
        cursor.execute("UPDATE enrollment SET total_score=%s, grade_point=%s WHERE id=%s",
                       (total, point, r['id']))
    return len(rows)


@teacher_bp.route('/api/teacher/offering/<int:offering_id>/ratio', methods=['PUT'])
@role_required('teacher')
def tea_offering_ratio(offering_id):
    """教师设置自己开课的成绩比例（已有成绩会按新比例重算）"""
    offering = query_one("SELECT id FROM course_offering WHERE id=%s AND teacher_id=%s",
                         (offering_id, session['user_id']))
    if not offering:
        return jsonify({'success': False, 'message': '无权操作该课程'}), 403
    data = request.get_json(silent=True) or {}
    usual_ratio = data.get('usual_ratio')
    exam_ratio = data.get('exam_ratio')
    try:
        usual_ratio = int(usual_ratio)
        exam_ratio = int(exam_ratio)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '比例必须为整数'}), 400
    if usual_ratio < 0 or exam_ratio < 0 or usual_ratio + exam_ratio != 100:
        return jsonify({'success': False, 'message': '平时占比与考试占比之和须为 100%'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE course_offering SET usual_ratio=%s, exam_ratio=%s WHERE id=%s",
                       (usual_ratio, exam_ratio, offering_id))
        affected = _recalc_totals(cursor, offering_id, usual_ratio, exam_ratio)
        conn.commit()
    except Exception:
        conn.rollback()
        return jsonify({'success': False, 'message': '成绩比例更新失败，请稍后重试'})
    finally:
        cursor.close()
        conn.close()

    log_operation('UPDATE', 'course_offering', offering_id,
                  f'教师设置成绩比例 {usual_ratio}:{exam_ratio}，重算 {affected} 条总评')
    msg = '成绩比例已更新'
    if affected:
        msg += f'，已按新比例重算 {affected} 名学生的总评'
    return jsonify({'success': True, 'message': msg})


@teacher_bp.route('/api/teacher/offering/<int:offering_id>/students')
@role_required('teacher')
def tea_offering_students(offering_id):
    offering = query_one("SELECT * FROM course_offering WHERE id=%s AND teacher_id=%s", (offering_id, session['user_id']))
    if not offering:
        return jsonify({'success': False, 'message': '无权查看该课程'}), 403
    _heal_offering_enrollments(offering_id)
    rows = query_all("""
        SELECT s.username, s.real_name, s.gender, cl.name AS class_name, e.select_time, e.status,
               e.usual_score, e.exam_score, e.total_score
        FROM enrollment e JOIN student s ON e.student_id=s.id
        LEFT JOIN class cl ON s.class_id=cl.id
        WHERE e.offering_id=%s AND e.status='已选' ORDER BY s.username""", (offering_id,))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@teacher_bp.route('/api/teacher/offering/<int:offering_id>/students/export')
@role_required('teacher')
def tea_offering_students_export(offering_id):
    """导出选课名单（Excel）"""
    offering = query_one("""SELECT co.id, c.name AS course_name, co.semester
                            FROM course_offering co JOIN course c ON co.course_id=c.id
                            WHERE co.id=%s AND co.teacher_id=%s""", (offering_id, session['user_id']))
    if not offering:
        return jsonify({'success': False, 'message': '无权查看该课程'}), 403

    _heal_offering_enrollments(offering_id)
    rows = query_all("""
        SELECT s.username, s.real_name, s.gender, cl.name AS class_name,
               e.select_time, e.status, e.usual_score, e.exam_score, e.total_score
        FROM enrollment e JOIN student s ON e.student_id=s.id
        LEFT JOIN class cl ON s.class_id=cl.id
        WHERE e.offering_id=%s AND e.status='已选' ORDER BY s.username""", (offering_id,))

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = '选课名单'

    center = Alignment(horizontal='center', vertical='center')
    head_fill = PatternFill('solid', fgColor='1F6FEB')
    head_font = Font(color='FFFFFF', bold=True, size=11)
    thin = Side(style='thin', color='D0D7DE')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells('A1:H1')
    ws['A1'] = f"选课名单 - {offering['course_name']}"
    ws['A1'].font = Font(size=14, bold=True)
    ws['A1'].alignment = center
    ws.merge_cells('A2:H2')
    ws['A2'] = f"学期：{offering['semester']}　共 {len(rows)} 人"
    ws['A2'].alignment = center
    ws['A2'].font = Font(size=10, color='666666')

    headers = ['序号', '学号', '姓名', '性别', '班级', '选课时间', '平时成绩', '考试成绩']
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=3, column=i, value=h)
        c.fill = head_fill
        c.font = head_font
        c.alignment = center
        c.border = border

    for idx, r in enumerate(rows, start=1):
        vals = [idx, safe_cell(r['username']), safe_cell(r['real_name']), safe_cell(r['gender']), safe_cell(r['class_name'] or ''),
                str(r['select_time'] or ''), r['usual_score'], r['exam_score']]
        for col, v in enumerate(vals, start=1):
            c = ws.cell(row=3 + idx, column=col, value=v)
            c.alignment = center
            c.border = border
            c.font = Font(size=10)

    widths = [6, 14, 12, 8, 14, 20, 12, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 24

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"选课名单-{offering['course_name']}-{offering['semester']}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@teacher_bp.route('/api/teacher/offering/<int:offering_id>/grades', methods=['GET', 'POST'])
@role_required('teacher')
def tea_grades(offering_id):
    offering = query_one("SELECT * FROM course_offering WHERE id=%s AND teacher_id=%s", (offering_id, session['user_id']))
    if not offering:
        return jsonify({'success': False, 'message': '无权操作该课程'}), 403

    # GET（成绩列表）与 POST（保存成绩）前都先自愈名单：确保统排课学生已落成 enrollment
    _heal_offering_enrollments(offering_id)
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        items = data.get('grades') or []
        if not isinstance(items, list):
            return jsonify({'success': False, 'message': '参数格式错误'})
        usual_ratio = _ratio_of(offering, 'usual_ratio', 40)
        exam_ratio = _ratio_of(offering, 'exam_ratio', 60)
        conn = get_db_connection()
        cursor = conn.cursor()
        changed = 0
        try:
            for item in items:
                sid = item.get('student_id')
                if not sid:
                    continue
                has_u = 'usual_score' in item
                has_e = 'exam_score' in item
                if not has_u and not has_e:
                    continue
                try:
                    usual = parse_score(item.get('usual_score')) if has_u else None
                    exam = parse_score(item.get('exam_score')) if has_e else None
                except ValueError as e:
                    conn.rollback()
                    return jsonify({'success': False, 'message': f'保存失败: {e}'})
                # 读取现有成绩：只提交一项时，另一项保持原值，避免被静默清空
                cursor.execute("""SELECT usual_score, exam_score FROM enrollment
                                  WHERE offering_id=%s AND student_id=%s AND status='已选'""",
                               (offering_id, sid))
                cur_row = cursor.fetchone()
                if not cur_row:
                    continue
                cur_u = usual if has_u else (float(cur_row['usual_score']) if cur_row['usual_score'] is not None else None)
                cur_e = exam if has_e else (float(cur_row['exam_score']) if cur_row['exam_score'] is not None else None)
                total = point = None
                if cur_u is not None and cur_e is not None:
                    total, point = calc_grade(cur_u, cur_e, usual_ratio, exam_ratio)
                cursor.execute("""UPDATE enrollment SET usual_score=%s, exam_score=%s, total_score=%s, grade_point=%s
                                  WHERE offering_id=%s AND student_id=%s AND status='已选'""",
                               (cur_u, cur_e, total, point, offering_id, sid))
                changed += cursor.rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            return jsonify({'success': False, 'message': '成绩保存失败，请稍后重试'})
        finally:
            cursor.close()
            conn.close()
        # 成绩写入留痕（成绩属于强审计数据，改分必须有记录）
        if changed:
            log_operation('UPDATE', 'enrollment', offering_id, f'教师录入/修改成绩 {changed} 条记录')
        return jsonify({'success': True, 'message': f'成绩已保存（{changed} 条）'})

    rows = query_all("""
        SELECT s.id AS student_id, s.username, s.real_name, cl.name AS class_name,
               e.usual_score, e.exam_score, e.total_score
        FROM enrollment e JOIN student s ON e.student_id=s.id
        LEFT JOIN class cl ON s.class_id=cl.id
        WHERE e.offering_id=%s AND e.status='已选' ORDER BY s.username""", (offering_id,))
    return jsonify({'success': True, 'data': fmt_rows(rows),
                    'ratio': {'usual_ratio': _ratio_of(offering, 'usual_ratio', 40),
                              'exam_ratio': _ratio_of(offering, 'exam_ratio', 60)}})


@teacher_bp.route('/api/teacher/offering/<int:offering_id>/grades/template')
@role_required('teacher')
def tea_grades_template(offering_id):
    """下载成绩录入模板（含选课学生名单 + 空成绩列）"""
    offering = query_one("""SELECT co.id, c.name AS course_name FROM course_offering co
                            JOIN course c ON co.course_id=c.id
                            WHERE co.id=%s AND co.teacher_id=%s""", (offering_id, session['user_id']))
    if not offering:
        return jsonify({'success': False, 'message': '无权操作该课程'}), 403

    _heal_offering_enrollments(offering_id)
    students = query_all("""
        SELECT s.username, s.real_name, cl.name AS class_name
        FROM enrollment e JOIN student s ON e.student_id=s.id
        LEFT JOIN class cl ON s.class_id=cl.id
        WHERE e.offering_id=%s AND e.status='已选' ORDER BY s.username""", (offering_id,))

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = '成绩录入'
    ws.append(['学号', '姓名', '班级', '平时成绩', '考试成绩'])
    for s in students:
        ws.append([safe_cell(s['username']), safe_cell(s['real_name']), safe_cell(s['class_name'] or ''), None, None])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f'成绩录入-{offering["course_name"]}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@teacher_bp.route('/api/teacher/offering/<int:offering_id>/grades/import', methods=['POST'])
@role_required('teacher')
def tea_grades_import(offering_id):
    """批量导入成绩：按学号匹配"""
    offering = query_one("SELECT * FROM course_offering WHERE id=%s AND teacher_id=%s", (offering_id, session['user_id']))
    if not offering:
        return jsonify({'success': False, 'message': '无权操作该课程'}), 403

    _heal_offering_enrollments(offering_id)
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'message': '请上传文件'})

    try:
        header, body = _read_uploaded_table(file)
    except Exception as e:
        print(f'成绩导入文件解析失败: {e}')
        return jsonify({'success': False, 'message': '文件解析失败，请使用系统提供的模板（xlsx/csv）'})

    # 定位列
    def find_col(title):
        for i, h in enumerate(header):
            if h and str(h).strip() == title:
                return i
        return None

    col_username = find_col('学号')
    col_usual = find_col('平时成绩')
    col_exam = find_col('考试成绩')
    if col_username is None:
        return jsonify({'success': False, 'message': '缺少「学号」列'})
    if col_usual is None and col_exam is None:
        return jsonify({'success': False, 'message': '缺少成绩列（「平时成绩」「考试成绩」至少需要一列）'})

    # 预取该教学班学生
    enrolled = query_all("""SELECT e.student_id, s.username FROM enrollment e
                            JOIN student s ON e.student_id=s.id
                            WHERE e.offering_id=%s AND e.status='已选'""", (offering_id,))
    valid_usernames = {e['username']: e['student_id'] for e in enrolled}
    usual_ratio = _ratio_of(offering, 'usual_ratio', 40)
    exam_ratio = _ratio_of(offering, 'exam_ratio', 60)

    conn = get_db_connection()
    cursor = conn.cursor()
    ok_count = 0
    errors = []

    def _cell(row, idx):
        """取单元格值；缺列 / 空单元格返回 None（表示"不修改该字段"）"""
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None or str(v).strip() == '':
            return None
        return v

    try:
        for lineno, row in enumerate(body, start=2):
            username = str(row[col_username]).strip() if col_username < len(row) and row[col_username] is not None else ''
            if username not in valid_usernames:
                errors.append(f'第{lineno}行：学号「{username}」不在本课程名单中')
                continue
            sid = valid_usernames[username]
            cursor.execute("""SELECT usual_score, exam_score FROM enrollment
                              WHERE offering_id=%s AND student_id=%s AND status='已选'""", (offering_id, sid))
            cur_row = cursor.fetchone()
            if not cur_row:
                errors.append(f'第{lineno}行：该学生当前不在本课程名单中')
                continue
            try:
                usual = parse_score(_cell(row, col_usual))
                exam = parse_score(_cell(row, col_exam))
            except (ValueError, TypeError) as e:
                errors.append(f'第{lineno}行：{e}')
                continue
            # 空单元格保持原值：避免只填部分列时把已有成绩清空
            new_u = usual if usual is not None else (float(cur_row['usual_score']) if cur_row['usual_score'] is not None else None)
            new_e = exam if exam is not None else (float(cur_row['exam_score']) if cur_row['exam_score'] is not None else None)
            total = point = None
            if new_u is not None and new_e is not None:
                total, point = calc_grade(new_u, new_e, usual_ratio, exam_ratio)
            cursor.execute("""UPDATE enrollment SET usual_score=%s, exam_score=%s, total_score=%s, grade_point=%s
                              WHERE offering_id=%s AND student_id=%s AND status='已选'""",
                           (new_u, new_e, total, point, offering_id, sid))
            if cursor.rowcount:
                ok_count += 1
        conn.commit()
        log_operation('IMPORT', 'enrollment', offering_id,
                      f'教师导入成绩: 成功{ok_count}条，失败{len(errors)}条')
    except Exception:
        conn.rollback()
        return jsonify({'success': False, 'message': '导入失败，请稍后重试'})
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': True,
                    'message': f'成绩导入完成：成功 {ok_count} 条，失败 {len(errors)} 条',
                    'success_count': ok_count, 'fail_count': len(errors), 'errors': errors[:20]})


@teacher_bp.route('/api/teacher/schedule')
@role_required('teacher')
def tea_schedule():
    semester = request.args.get('semester', CURRENT_SEMESTER)
    rows = query_all("""
        SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name, cr.building, cr.room, co.selected_count
        FROM course_schedule cs
        JOIN course_offering co ON cs.offering_id=co.id
        JOIN course c ON co.course_id=c.id
        LEFT JOIN classroom cr ON cs.classroom_id=cr.id
        WHERE co.teacher_id=%s AND co.semester=%s
        ORDER BY cs.weekday, cs.start_section""", (session['user_id'], semester))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@teacher_bp.route('/api/teacher/schedule/export')
@role_required('teacher')
def tea_schedule_export():
    """导出我的课表（Excel）"""
    semester = request.args.get('semester', CURRENT_SEMESTER)
    rows = query_all("""
        SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name, cr.building, cr.room
        FROM course_schedule cs
        JOIN course_offering co ON cs.offering_id=co.id
        JOIN course c ON co.course_id=c.id
        LEFT JOIN classroom cr ON cs.classroom_id=cr.id
        WHERE co.teacher_id=%s AND co.semester=%s
        ORDER BY cs.weekday, cs.start_section""", (session['user_id'], semester))

    tea = query_one("""SELECT t.real_name, c.name AS college_name FROM teacher t
                       LEFT JOIN college c ON t.college_id=c.id WHERE t.id=%s""", (session['user_id'],)) or {}
    subtitle = f"{tea.get('real_name') or ''}　{tea.get('college_name') or ''}　学期：{semester}"
    buf = export_schedule_xlsx(rows, '教师课表', subtitle)
    return send_file(buf, as_attachment=True,
                     download_name=f"教师课表-{tea.get('real_name') or session['username']}-{semester}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@teacher_bp.route('/api/teacher/evaluations')
@role_required('teacher')
def tea_evaluations():
    rows = query_all("""
        SELECT c.name AS course_name, co.semester, ev.type,
               COUNT(ev.id) AS eval_count, AVG(ev.total_score) AS avg_score
        FROM evaluation ev
        JOIN course_offering co ON ev.offering_id=co.id
        JOIN course c ON co.course_id=c.id
        WHERE co.teacher_id=%s
        GROUP BY co.id, ev.type ORDER BY co.semester DESC""", (session['user_id'],))
    comments = query_all("""
        SELECT c.name AS course_name, ev.comment, ev.total_score, ev.created_at
        FROM evaluation ev
        JOIN course_offering co ON ev.offering_id=co.id
        JOIN course c ON co.course_id=c.id
        WHERE co.teacher_id=%s AND ev.comment IS NOT NULL AND ev.comment != ''
        ORDER BY ev.created_at DESC LIMIT 50""", (session['user_id'],))
    return jsonify({'success': True, 'summary': fmt_rows(rows), 'comments': fmt_rows(comments)})


@teacher_bp.route('/api/teacher/dashboard')
@role_required('teacher')
def tea_dashboard():
    tid = session['user_id']
    offering_count = query_one("SELECT COUNT(*) c FROM course_offering WHERE teacher_id=%s AND semester=%s", (tid, CURRENT_SEMESTER))['c']
    student_count = query_one("""SELECT COUNT(*) c FROM enrollment e JOIN course_offering co ON e.offering_id=co.id
                                 WHERE co.teacher_id=%s AND co.semester=%s AND e.status='已选'""", (tid, CURRENT_SEMESTER))['c']
    ungraded = query_one("""SELECT COUNT(*) c FROM enrollment e JOIN course_offering co ON e.offering_id=co.id
                            WHERE co.teacher_id=%s AND co.semester=%s AND e.status='已选' AND e.total_score IS NULL""",
                         (tid, CURRENT_SEMESTER))['c']
    # 只统计正式学生评价（type='final'），过程评价不计入工作台平均分
    avg_eval = query_one("""SELECT AVG(ev.total_score) s FROM evaluation ev
                            JOIN course_offering co ON ev.offering_id=co.id
                            WHERE co.teacher_id=%s AND ev.type='final'""", (tid,))['s']
    return jsonify({'success': True, 'data': {
        'offering_count': offering_count, 'student_count': student_count,
        'ungraded_count': ungraded, 'avg_evaluation': round(float(avg_eval), 1) if avg_eval else None
    }})
