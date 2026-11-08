# -*- coding: utf-8 -*-
"""学生端蓝图"""
import io
import re

import pymysql
from flask import Blueprint, request, jsonify, session, send_file

from core import (CURRENT_SEMESTER, query_one, query_all, execute, get_db_connection, encrypt_and_mask_id_card,
                  fmt_rows, role_required, export_schedule_xlsx, parse_int, log_operation)

student_bp = Blueprint('student', __name__)


def current_student():
    return query_one("""SELECT s.*, cl.name AS class_name, m.name AS major_name, c.name AS college_name
                        FROM student s
                        LEFT JOIN class cl ON s.class_id = cl.id
                        LEFT JOIN major m ON cl.major_id = m.id
                        LEFT JOIN college c ON m.college_id = c.id
                        WHERE s.id = %s""", (session['user_id'],))


@student_bp.route('/api/student/profile')
@role_required('student')
def stu_profile():
    stu = current_student()
    if not stu:
        return jsonify({'success': False, 'message': '学生信息不存在，请重新登录'}), 401
    stu.pop('password_hash', None)
    # 身份证号属敏感个人信息：解密后脱敏展示（520***********1234）
    if 'id_card' in stu:
        stu['id_card'] = encrypt_and_mask_id_card(stu['id_card'])
    row = fmt_rows([stu])[0]
    if row.get('avatar'):
        row['avatar'] = f"/uploads/avatar/{row['avatar']}"
    return jsonify({'success': True, 'data': row})


@student_bp.route('/api/student/profile', methods=['PUT'])
@role_required('student')
def stu_update_profile():
    data = request.get_json(silent=True) or {}

    def _txt(key, maxlen, label):
        v = data.get(key)
        v = '' if v is None else str(v).strip()
        if len(v) > maxlen:
            raise ValueError(f'{label}长度不能超过 {maxlen} 个字符')
        return v or None

    try:
        phone = _txt('phone', 20, '手机号')
        email = _txt('email', 100, '邮箱')
        address = _txt('address', 255, '地址')
        political = _txt('political_status', 20, '政治面貌')
        native = _txt('native_place', 100, '籍贯')
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    if phone and not re.fullmatch(r'[0-9+\-\s()]{6,20}', phone):
        return jsonify({'success': False, 'message': '手机号格式不正确'})
    # 邮箱字符白名单：拒绝引号/尖括号等，防止存储型 XSS 经由个人资料注入管理端页面
    if email and not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', email):
        return jsonify({'success': False, 'message': '邮箱格式不正确'})
    execute("""UPDATE student SET phone=%s, email=%s, address=%s, political_status=%s, native_place=%s WHERE id=%s""",
            (phone, email, address, political, native, session['user_id']))
    return jsonify({'success': True, 'message': '个人信息已更新'})


@student_bp.route('/api/student/schedule')
@role_required('student')
def stu_schedule():
    """个人课表：自己选的课（含选修）+ 本班指定的非选修课（必修/通识/实践，直接排课，无需选）"""
    semester = request.args.get('semester', CURRENT_SEMESTER)
    rows = query_all("""
        SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name, c.credit, t.real_name AS teacher_name,
               cr.building, cr.room, co.semester
        FROM (
            SELECT e.offering_id FROM enrollment e
            WHERE e.student_id = %s AND e.status = '已选'
            UNION
            SELECT oc.offering_id FROM offering_class oc
            JOIN course_offering co2 ON co2.id = oc.offering_id
            JOIN course c2 ON c2.id = co2.course_id
            JOIN student s ON s.class_id = oc.class_id
            WHERE s.id = %s AND c2.type != '选修'
        ) mine
        JOIN course_offering co ON mine.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        JOIN course_schedule cs ON cs.offering_id = co.id
        LEFT JOIN classroom cr ON cs.classroom_id = cr.id
        WHERE co.semester = %s
        ORDER BY cs.weekday, cs.start_section""", (session['user_id'], session['user_id'], semester))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/class-schedule')
@role_required('student')
def stu_class_schedule():
    """班级课表：按「开课指定的班级」展示本班全部课程安排（无需学生选课）"""
    semester = request.args.get('semester', CURRENT_SEMESTER)
    stu = current_student()
    if not stu['class_id']:
        return jsonify({'success': False, 'message': '未分配班级'})
    rows = query_all("""
        SELECT DISTINCT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name, t.real_name AS teacher_name, cr.building, cr.room
        FROM offering_class oc
        JOIN course_offering co ON oc.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        JOIN course_schedule cs ON cs.offering_id = co.id
        LEFT JOIN classroom cr ON cs.classroom_id = cr.id
        WHERE oc.class_id = %s AND co.semester = %s
        ORDER BY cs.weekday, cs.start_section""", (stu['class_id'], semester))
    return jsonify({'success': True, 'data': fmt_rows(rows), 'class_name': stu['class_name']})


@student_bp.route('/api/student/schedule/export')
@role_required('student')
def stu_schedule_export():
    """导出个人课表（Excel）"""
    semester = request.args.get('semester', CURRENT_SEMESTER)
    rows = query_all("""
        SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name, t.real_name AS teacher_name, cr.building, cr.room
        FROM (
            SELECT e.offering_id FROM enrollment e
            WHERE e.student_id = %s AND e.status = '已选'
            UNION
            SELECT oc.offering_id FROM offering_class oc
            JOIN course_offering co2 ON co2.id = oc.offering_id
            JOIN course c2 ON c2.id = co2.course_id
            JOIN student s ON s.class_id = oc.class_id
            WHERE s.id = %s AND c2.type != '选修'
        ) mine
        JOIN course_offering co ON mine.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        JOIN course_schedule cs ON cs.offering_id = co.id
        LEFT JOIN classroom cr ON cs.classroom_id = cr.id
        WHERE co.semester = %s
        ORDER BY cs.weekday, cs.start_section""", (session['user_id'], session['user_id'], semester))

    stu = current_student() or {}
    subtitle = f"{stu.get('real_name') or ''}　{stu.get('class_name') or ''}　学期：{semester}"
    buf = export_schedule_xlsx(rows, '个人课表', subtitle)
    return send_file(buf, as_attachment=True,
                     download_name=f"个人课表-{stu.get('real_name') or session['username']}-{semester}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@student_bp.route('/api/student/class-schedule/export')
@role_required('student')
def stu_class_schedule_export():
    """导出班级课表（Excel）"""
    semester = request.args.get('semester', CURRENT_SEMESTER)
    stu = current_student()
    if not stu or not stu['class_id']:
        return jsonify({'success': False, 'message': '未分配班级'})
    rows = query_all("""
        SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name, t.real_name AS teacher_name, cr.building, cr.room
        FROM offering_class oc
        JOIN course_offering co ON oc.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        JOIN course_schedule cs ON cs.offering_id = co.id
        LEFT JOIN classroom cr ON cs.classroom_id = cr.id
        WHERE oc.class_id = %s AND co.semester = %s
        ORDER BY cs.weekday, cs.start_section""", (stu['class_id'], semester))

    subtitle = f"{stu.get('class_name') or ''}　学期：{semester}"
    buf = export_schedule_xlsx(rows, '班级课表', subtitle)
    return send_file(buf, as_attachment=True,
                     download_name=f"班级课表-{stu.get('class_name') or ''}-{semester}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@student_bp.route('/api/student/free-classrooms')
@role_required('student')
def stu_free_classrooms():
    """查询空闲教室"""
    weekday = request.args.get('weekday', type=int)
    section = request.args.get('section', type=int)
    sql = """SELECT cr.id, cr.building, cr.room, cr.capacity FROM classroom cr"""
    params = []
    if weekday and section:
        sql += """ WHERE cr.id NOT IN (
                    SELECT cs.classroom_id FROM course_schedule cs
                    JOIN course_offering co ON cs.offering_id = co.id
                    WHERE co.semester = %s AND cs.weekday = %s AND cs.start_section <= %s AND cs.end_section >= %s
                    AND cs.classroom_id IS NOT NULL)"""
        params = [CURRENT_SEMESTER, weekday, section, section]
    sql += " ORDER BY cr.building, cr.room"
    rows = query_all(sql, params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/enrollments')
@role_required('student')
def stu_enrollments():
    """选课情况确认"""
    semester = request.args.get('semester', CURRENT_SEMESTER)
    rows = query_all("""
        SELECT e.id, e.status, e.select_time, e.is_retake, c.code, c.name AS course_name, c.credit, c.type,
               t.real_name AS teacher_name, co.semester, co.max_count, co.selected_count
        FROM enrollment e
        JOIN course_offering co ON e.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        WHERE e.student_id = %s AND co.semester = %s
        ORDER BY e.select_time DESC""", (session['user_id'], semester))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/offering-students')
@role_required('student')
def stu_offering_students():
    """选课名单查询：查看自己所选课程的同班同学名单"""
    offering_id = request.args.get('offering_id', type=int)
    offerings = query_all("""
        SELECT co.id, c.name AS course_name, co.semester FROM enrollment e
        JOIN course_offering co ON e.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        WHERE e.student_id = %s AND e.status = '已选'""", (session['user_id'],))
    students = []
    if offering_id:
        # 越权防护：只能查看自己已选修课程的名单
        own = query_one("SELECT id FROM enrollment WHERE student_id=%s AND offering_id=%s AND status='已选'",
                        (session['user_id'], offering_id))
        if not own:
            return jsonify({'success': False, 'message': '无权查看该课程名单'}), 403
        students = query_all("""
            SELECT s.username, s.real_name, s.gender, cl.name AS class_name
            FROM enrollment e JOIN student s ON e.student_id = s.id
            LEFT JOIN class cl ON s.class_id = cl.id
            WHERE e.offering_id = %s AND e.status = '已选' ORDER BY s.username""", (offering_id,))
    return jsonify({'success': True, 'offerings': fmt_rows(offerings), 'students': fmt_rows(students)})


@student_bp.route('/api/student/retake-courses')
@role_required('student')
def stu_retake_courses():
    """重修课程查询：不及格课程 + 本学期可报的开班"""
    failed = query_all("""
        SELECT c.id AS course_id, c.code, c.name, c.credit, e.total_score, co.semester
        FROM enrollment e
        JOIN course_offering co ON e.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        WHERE e.student_id = %s AND e.total_score IS NOT NULL AND e.total_score < 60""", (session['user_id'],))
    available = query_all("""
        SELECT co.id, c.name AS course_name, c.credit, t.real_name AS teacher_name, co.max_count, co.selected_count
        FROM course_offering co JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        WHERE co.semester = %s AND co.status = '开放'""", (CURRENT_SEMESTER,))
    applies = query_all("""
        SELECT r.id, c.name AS course_name, r.semester, r.status, r.reason, r.review_remark, r.created_at
        FROM retake_apply r JOIN course c ON r.course_id = c.id
        WHERE r.student_id = %s ORDER BY r.created_at DESC""", (session['user_id'],))
    return jsonify({'success': True, 'failed': fmt_rows(failed), 'available': fmt_rows(available), 'applies': fmt_rows(applies)})


@student_bp.route('/api/student/grades')
@role_required('student')
def stu_grades():
    """成绩查询"""
    semester = request.args.get('semester')
    sql = """
        SELECT c.code, c.name AS course_name, c.credit, c.type, co.semester,
               e.usual_score, e.exam_score, e.total_score, e.grade_point, e.is_retake,
               t.real_name AS teacher_name
        FROM enrollment e
        JOIN course_offering co ON e.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        WHERE e.student_id = %s AND e.status = '已选'"""
    params = [session['user_id']]
    if semester:
        sql += " AND co.semester = %s"
        params.append(semester)
    sql += " ORDER BY co.semester DESC, c.code"
    rows = query_all(sql, params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/grade-report')
@role_required('student')
def stu_grade_report():
    """成绩总表（打印用）：含汇总统计"""
    rows = query_all("""
        SELECT c.code, c.name AS course_name, COALESCE(c.credit, 0) AS credit, c.type, co.semester,
               e.total_score, e.grade_point
        FROM enrollment e
        JOIN course_offering co ON e.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        WHERE e.student_id = %s AND e.status = '已选' AND e.total_score IS NOT NULL
        ORDER BY co.semester, c.code""", (session['user_id'],))

    # 统计口径：同一门课多次修读（重修 / 同学期多教学班）只取最高分一次，
    # 否则不及格的历史尝试会永久拉低平均分，学分与绩点还会被重复累加。
    best = {}
    for r in rows:
        k = r['code']
        if k not in best or (r['total_score'] or 0) > (best[k]['total_score'] or 0):
            best[k] = r
    counted = list(best.values())

    def _credit(r):
        return float(r['credit'] or 0)

    total_credit = sum(_credit(r) for r in counted if (r['total_score'] or 0) >= 60)
    avg = round(sum(float(r['total_score']) for r in counted) / len(counted), 1) if counted else 0
    credit_sum = sum(_credit(r) for r in counted)
    gpa = round(sum(float(r['grade_point'] or 0) * _credit(r) for r in counted) / credit_sum, 2) if credit_sum > 0 else 0
    stu = current_student()
    if not stu:
        return jsonify({'success': False, 'message': '学生信息不存在，请重新登录'}), 401
    stu.pop('password_hash', None)
    return jsonify({'success': True, 'data': fmt_rows(rows), 'student': fmt_rows([stu])[0],
                    'summary': {'total_credit': float(total_credit), 'avg_score': avg, 'gpa': gpa}})


@student_bp.route('/api/student/exams')
@role_required('student')
def stu_exams():
    rows = query_all("""
        SELECT c.name AS course_name, ex.exam_date, ex.start_time, ex.end_time, ex.exam_type,
               cr.building, cr.room, co.semester
        FROM exam ex
        JOIN course_offering co ON ex.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        JOIN enrollment e ON e.offering_id = co.id AND e.student_id = %s AND e.status = '已选'
        LEFT JOIN classroom cr ON ex.classroom_id = cr.id
        ORDER BY ex.exam_date""", (session['user_id'],))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/certificates')
@role_required('student')
def stu_certificates():
    rows = query_all("SELECT * FROM certificate WHERE student_id = %s ORDER BY issue_date DESC", (session['user_id'],))
    stu = current_student()
    stu.pop('password_hash', None)
    return jsonify({'success': True, 'data': fmt_rows(rows), 'student': fmt_rows([stu])[0]})


@student_bp.route('/api/student/teaching-plan')
@role_required('student')
def stu_teaching_plan():
    """教学执行计划：按本专业"""
    stu = current_student()
    major_id = None
    if stu['class_id']:
        cl = query_one("SELECT major_id FROM class WHERE id = %s", (stu['class_id'],))
        major_id = cl['major_id'] if cl else None
    rows = []
    if major_id:
        rows = query_all("""
            SELECT tp.semester_no, tp.category, c.code, c.name AS course_name, c.credit, c.hours, c.type
            FROM teaching_plan tp JOIN course c ON tp.course_id = c.id
            WHERE tp.major_id = %s ORDER BY tp.semester_no, c.code""", (major_id,))
    return jsonify({'success': True, 'data': fmt_rows(rows),
                    'major_name': stu.get('major_name'), 'class_name': stu.get('class_name')})


@student_bp.route('/api/student/course-select/list')
@role_required('student')
def stu_selectable():
    """自主选课：本学期开放的【选修】课列表（必修/通识/实践由班级指定直接排课，无需选）"""
    rows = query_all("""
        SELECT co.id, c.code, c.name AS course_name, c.credit, c.type, c.hours,
               t.real_name AS teacher_name, co.max_count, co.selected_count,
               (SELECT GROUP_CONCAT(cl.name ORDER BY cl.name SEPARATOR '、')
                FROM offering_class oc JOIN class cl ON oc.class_id=cl.id
                WHERE oc.offering_id=co.id) AS class_names,
               (SELECT COUNT(*) FROM enrollment e WHERE e.offering_id = co.id AND e.student_id = %s AND e.status = '已选') AS enrolled
        FROM course_offering co
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        WHERE co.semester = %s AND co.status = '开放' AND c.type = '选修'
        ORDER BY c.code""", (session['user_id'], CURRENT_SEMESTER))
    for r in rows:
        r['schedules'] = query_all("""
            SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type, cr.building, cr.room
            FROM course_schedule cs LEFT JOIN classroom cr ON cs.classroom_id = cr.id
            WHERE cs.offering_id = %s ORDER BY cs.weekday, cs.start_section""", (r['id'],))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


# ---------- 选课校验辅助：周次解析 / 时间冲突 / 同课程重复 ----------

def _parse_weeks(s):
    """把 '1-16' / '1-8,10-16' 之类的周次字符串解析为周次集合"""
    weeks = set()
    for part in str(s or '').replace('，', ',').split(','):
        part = part.strip()
        if not part:
            continue
        lo, sep, hi = part.partition('-')
        try:
            if sep:
                weeks.update(range(int(lo), int(hi) + 1))
            else:
                weeks.add(int(part))
        except ValueError:
            continue
    return weeks


def _effective_weeks(weeks, week_type):
    ws = _parse_weeks(weeks)
    if week_type == '单周':
        ws = {w for w in ws if w % 2 == 1}
    elif week_type == '双周':
        ws = {w for w in ws if w % 2 == 0}
    return ws


def _slot_conflict(a, b):
    """两段排课是否在星期 / 节次 / 周次上重叠"""
    try:
        if int(a['weekday']) != int(b['weekday']):
            return False
        if int(a['start_section']) > int(b['end_section']) or int(b['start_section']) > int(a['end_section']):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return bool(_effective_weeks(a.get('weeks'), a.get('week_type'))
                & _effective_weeks(b.get('weeks'), b.get('week_type')))


def _occupied_schedules(student_id, class_id, semester):
    """学生当前已占用的课表：本人已选课程 + 本班指定必修/通识/实践课"""
    return query_all("""
        SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name
        FROM (
            SELECT e.offering_id FROM enrollment e
            WHERE e.student_id = %s AND e.status = '已选'
            UNION
            SELECT oc.offering_id FROM offering_class oc
            JOIN course_offering co2 ON co2.id = oc.offering_id
            JOIN course c2 ON c2.id = co2.course_id
            WHERE oc.class_id = %s AND c2.type != '选修'
        ) mine
        JOIN course_offering co ON mine.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        JOIN course_schedule cs ON cs.offering_id = co.id
        WHERE co.semester = %s""", (student_id, class_id, semester))


@student_bp.route('/api/student/course-select/enroll', methods=['POST'])
@role_required('student')
def stu_enroll():
    data = request.get_json(silent=True) or {}
    offering_id = data.get('offering_id')
    offering = query_one("SELECT * FROM course_offering WHERE id = %s", (offering_id,))
    if not offering or offering['status'] != '开放':
        return jsonify({'success': False, 'message': '该课程不可选'})
    # 仅允许选当前学期的课：历史学期开课可能仍残留「开放」状态
    if offering['semester'] != CURRENT_SEMESTER:
        return jsonify({'success': False, 'message': '只能选择本学期开放的课程'})
    # 仅选修课需自主选课；必修/通识/实践由学校统一排课
    course = query_one("SELECT c.type, c.name FROM course_offering co JOIN course c ON co.course_id=c.id WHERE co.id=%s", (offering_id,))
    if not course or course['type'] != '选修':
        return jsonify({'success': False, 'message': '该课程由学校统一排课，无需自主选课'})
    # 班级限制：指定了授课班级的开课，仅限这些班级的学生选课
    stu = query_one("SELECT class_id FROM student WHERE id=%s", (session['user_id'],))
    if not stu:
        return jsonify({'success': False, 'message': '学生信息不存在，请重新登录'}), 401
    has_limit = query_one("SELECT id FROM offering_class WHERE offering_id=%s", (offering_id,))
    if has_limit:
        allowed = query_one("SELECT id FROM offering_class WHERE offering_id=%s AND class_id=%s",
                            (offering_id, stu['class_id']))
        if not allowed:
            return jsonify({'success': False, 'message': '该课程不对您所在班级开放'})
    exist = query_one("SELECT * FROM enrollment WHERE student_id = %s AND offering_id = %s", (session['user_id'], offering_id))
    if exist and exist['status'] == '已选':
        return jsonify({'success': False, 'message': '已选过该课程'})

    # 同一学期内同一门课程只能选一个教学班，否则学分与绩点会被重复计算
    # （跨学期允许：不及格课程可在后续学期重修）
    dup = query_one("""SELECT c.name FROM enrollment e
                       JOIN course_offering co ON e.offering_id = co.id
                       JOIN course c ON co.course_id = c.id
                       WHERE e.student_id=%s AND e.status='已选'
                         AND co.course_id=%s AND co.semester=%s LIMIT 1""",
                    (session['user_id'], offering['course_id'], offering['semester']))
    if dup:
        return jsonify({'success': False,
                        'message': f'本学期已选过《{dup["name"]}》的其他教学班，同一课程不能重复选修'})

    # 上课时间冲突校验（与已选课程、本班指定课程比对星期/节次/周次）
    target_slots = query_all("""SELECT cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type
                                FROM course_schedule cs WHERE cs.offering_id=%s""", (offering_id,))
    if target_slots:
        occupied = _occupied_schedules(session['user_id'], stu['class_id'], offering['semester'])
        for t in target_slots:
            for o in occupied:
                if _slot_conflict(t, o):
                    return jsonify({'success': False,
                                    'message': f'上课时间与已选课程《{o["course_name"]}》冲突'})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 原子抢占名额：仅当未满员时才 +1，避免并发超卖
        cursor.execute("""UPDATE course_offering SET selected_count = selected_count + 1
                          WHERE id=%s AND status='开放' AND selected_count < max_count""", (offering_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({'success': False, 'message': '该课程人数已满'})
        if exist:
            # 状态守卫：仅当记录仍是「退选」才恢复，避免并发重选造成名额虚增
            cursor.execute("UPDATE enrollment SET status='已选', select_time=NOW() WHERE id=%s AND status='退选'",
                           (exist['id'],))
            if cursor.rowcount != 1:
                conn.rollback()
                return jsonify({'success': False, 'message': '选课状态已变化，请刷新后重试'})
        else:
            cursor.execute("INSERT INTO enrollment (student_id, offering_id) VALUES (%s,%s)", (session['user_id'], offering_id))
        conn.commit()
    except pymysql.err.IntegrityError:
        conn.rollback()
        return jsonify({'success': False, 'message': '已选过该课程'})
    except Exception:
        conn.rollback()
        return jsonify({'success': False, 'message': '选课失败，请稍后重试'})
    finally:
        cursor.close()
        conn.close()
    return jsonify({'success': True, 'message': '选课成功'})


@student_bp.route('/api/student/course-select/drop', methods=['POST'])
@role_required('student')
def stu_drop():
    offering_id = request.get_json().get('offering_id')
    record = query_one("SELECT * FROM enrollment WHERE student_id=%s AND offering_id=%s AND status='已选'",
                       (session['user_id'], offering_id))
    if not record:
        return jsonify({'success': False, 'message': '未找到选课记录'})
    if record['total_score'] is not None:
        return jsonify({'success': False, 'message': '已有成绩的课程不能退选'})

    # 统排课守卫：offering_class 指定了本班且课程类型非选修（必修/通识/实践）的课程
    # 由学校统一排课，学生无需自主选课、也不能退选（否则教师端名单/成绩会缺人）。
    # 学生未分配班级时不拦截。
    stu = query_one("SELECT class_id FROM student WHERE id=%s", (session['user_id'],))
    if stu and stu['class_id']:
        fixed = query_one("""
            SELECT 1 AS x
            FROM course_offering co
            JOIN course c ON c.id = co.course_id
            JOIN offering_class oc ON oc.offering_id = co.id AND oc.class_id = %s
            WHERE co.id = %s AND c.type <> '选修'
            LIMIT 1""", (stu['class_id'], offering_id))
        if fixed:
            return jsonify({'success': False,
                            'message': '该课程由学校统一排课（必修/通识/实践），不能退选'})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 状态守卫：仅当仍为「已选」才退选，防止并发/重复提交造成名额双扣
        cursor.execute("UPDATE enrollment SET status='退选' WHERE id=%s AND status='已选'", (record['id'],))
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({'success': False, 'message': '该课程已退选，请刷新后重试'})
        cursor.execute("UPDATE course_offering SET selected_count = GREATEST(selected_count - 1, 0) WHERE id=%s", (offering_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        return jsonify({'success': False, 'message': '退选失败，请稍后重试'})
    finally:
        cursor.close()
        conn.close()
    return jsonify({'success': True, 'message': '退选成功'})


@student_bp.route('/api/student/evaluations')
@role_required('student')
def stu_evaluations():
    """评教列表：本学期已选课程及评价状态"""
    eval_type = request.args.get('type', 'final')
    rows = query_all("""
        SELECT co.id AS offering_id, c.name AS course_name, t.real_name AS teacher_name, co.semester,
               ev.id AS evaluation_id, ev.total_score, ev.comment, ev.created_at AS eval_time
        FROM enrollment e
        JOIN course_offering co ON e.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        LEFT JOIN evaluation ev ON ev.offering_id = co.id AND ev.student_id = e.student_id AND ev.type = %s
        WHERE e.student_id = %s AND e.status = '已选' AND co.semester = %s
        ORDER BY c.code""", (eval_type, session['user_id'], CURRENT_SEMESTER))
    return jsonify({'success': True, 'data': fmt_rows(rows), 'type': eval_type})


@student_bp.route('/api/student/evaluations', methods=['POST'])
@role_required('student')
def stu_submit_evaluation():
    data = request.get_json(silent=True) or {}
    offering_id = data.get('offering_id')
    eval_type = data.get('type', 'final')
    if eval_type not in ('final', 'process'):
        return jsonify({'success': False, 'message': '无效的评价类型'})
    scores = [data.get('score_teaching'), data.get('score_content'), data.get('score_method'), data.get('score_effect')]
    # 注意：bool 是 int 的子类，True/False 会被当作 1/0 放行，需显式排除
    if not all(isinstance(s, int) and not isinstance(s, bool) and 1 <= s <= 5 for s in scores):
        return jsonify({'success': False, 'message': '请完成全部评分项（1-5分）'})

    enrolled = query_one("""SELECT e.id FROM enrollment e JOIN course_offering co ON e.offering_id=co.id
                            WHERE e.student_id=%s AND e.offering_id=%s AND e.status='已选'
                              AND co.semester=%s""",
                         (session['user_id'], offering_id, CURRENT_SEMESTER))
    if not enrolled:
        return jsonify({'success': False, 'message': '未选修该课程，无法评价'})

    total = round(sum(scores) / 4 * 20, 1)  # 折算百分制
    try:
        execute("""INSERT INTO evaluation (student_id, offering_id, type, score_teaching, score_content, score_method, score_effect, total_score, comment)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE score_teaching=VALUES(score_teaching), score_content=VALUES(score_content),
                   score_method=VALUES(score_method), score_effect=VALUES(score_effect), total_score=VALUES(total_score), comment=VALUES(comment)""",
                (session['user_id'], offering_id, eval_type, scores[0], scores[1], scores[2], scores[3], total, str(data.get('comment') or '')[:500]))
    except Exception as e:
        print(f'评教提交失败: {e}')
        return jsonify({'success': False, 'message': '提交失败，请稍后重试'})
    return jsonify({'success': True, 'message': '评价提交成功'})


@student_bp.route('/api/student/apply/status-change', methods=['POST'])
@role_required('student')
def stu_apply_status_change():
    data = request.get_json(silent=True) or {}
    change_type = data.get('change_type')
    if change_type not in ('休学', '复学', '转专业', '退学'):
        return jsonify({'success': False, 'message': '无效的异动类型'})
    # 防重复：同类型申请仍在待审核时不允许再提交
    pending = query_one("""SELECT id FROM status_change_apply
                           WHERE student_id=%s AND change_type=%s AND status='待审核'""",
                        (session['user_id'], change_type))
    if pending:
        return jsonify({'success': False, 'message': f'您已有一条「{change_type}」申请正在审核中，请勿重复提交'})
    rid = execute("INSERT INTO status_change_apply (student_id, change_type, reason, apply_date) VALUES (%s,%s,%s,CURDATE())",
                  (session['user_id'], change_type, str(data.get('reason') or '')[:2000]))
    return jsonify({'success': True, 'message': '学籍异动申请已提交', 'id': rid})


@student_bp.route('/api/student/apply/retake', methods=['POST'])
@role_required('student')
def stu_apply_retake():
    data = request.get_json(silent=True) or {}
    try:
        course_id = parse_int(data.get('course_id'), label='课程')
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    if not course_id:
        return jsonify({'success': False, 'message': '请选择重修课程'})
    course = query_one("SELECT id, name FROM course WHERE id=%s", (course_id,))
    if not course:
        return jsonify({'success': False, 'message': '课程不存在'})
    # 已通过的课程无需重修
    passed = query_one("""SELECT e.id FROM enrollment e JOIN course_offering co ON e.offering_id=co.id
                          WHERE e.student_id=%s AND co.course_id=%s AND e.status='已选'
                            AND e.total_score >= 60 LIMIT 1""",
                       (session['user_id'], course_id))
    if passed:
        return jsonify({'success': False, 'message': f'《{course["name"]}》已通过，无需重修'})
    # 防重复：同课程待审核的申请只允许一条
    pending = query_one("""SELECT id FROM retake_apply
                           WHERE student_id=%s AND course_id=%s AND status='待审核'""",
                        (session['user_id'], course_id))
    if pending:
        return jsonify({'success': False, 'message': '该课程的重修申请正在审核中，请勿重复提交'})
    rid = execute("INSERT INTO retake_apply (student_id, course_id, semester, reason) VALUES (%s,%s,%s,%s)",
                  (session['user_id'], course_id, CURRENT_SEMESTER, str(data.get('reason') or '')[:200]))
    return jsonify({'success': True, 'message': '重修报名已提交，等待审核', 'id': rid})


@student_bp.route('/api/student/apply/project', methods=['POST'])
@role_required('student')
def stu_apply_project():
    data = request.get_json() or {}
    project_id = data.get('project_id')
    project = query_one("SELECT * FROM project WHERE id=%s AND is_open=1", (project_id,))
    if not project:
        return jsonify({'success': False, 'message': '该项目不可报名'})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 原子抢占名额，避免并发超卖
        cursor.execute("""UPDATE project SET apply_count = apply_count + 1
                          WHERE id=%s AND is_open=1 AND apply_count < max_count""", (project_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({'success': False, 'message': '该项目名额已满'})
        cursor.execute("INSERT INTO project_apply (project_id, student_id, reason) VALUES (%s,%s,%s)",
                       (project_id, session['user_id'], data.get('reason', '')))
        conn.commit()
    except pymysql.err.IntegrityError:
        conn.rollback()
        return jsonify({'success': False, 'message': '已报名过该项目'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'报名失败: {e}'})
    finally:
        cursor.close()
        conn.close()
    return jsonify({'success': True, 'message': '项目报名已提交'})


@student_bp.route('/api/student/apply/credit-substitute', methods=['POST'])
@role_required('student')
def stu_apply_credit_substitute():
    data = request.get_json(silent=True) or {}
    school = str(data.get('external_school') or '').strip()
    ext_course = str(data.get('external_course') or '').strip()
    if not school or not ext_course:
        return jsonify({'success': False, 'message': '请填写完整的校外课程信息'})
    # 校外学分：可空，非空时必须是 0-999.9 的数字（对应 DECIMAL(4,1)）
    credit = data.get('external_credit')
    if credit in (None, ''):
        credit = None
    else:
        try:
            credit = round(float(credit), 1)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '校外学分必须是数字'})
        if credit < 0 or credit > 999.9:
            return jsonify({'success': False, 'message': '校外学分应在 0-999.9 之间'})
    # 替代课程：可空，非空时必须真实存在（否则插入会触发外键错误）
    sub_id = data.get('substitute_course_id')
    if sub_id in (None, ''):
        sub_id = None
    else:
        sub = query_one("SELECT id FROM course WHERE id=%s", (sub_id,))
        if not sub:
            return jsonify({'success': False, 'message': '替代的本校课程不存在'})
    # 防重复：同一门校外课程只允许一条待审核申请
    pending = query_one("""SELECT id FROM credit_substitute_apply
                           WHERE student_id=%s AND external_course=%s AND status='待审核'""",
                        (session['user_id'], ext_course))
    if pending:
        return jsonify({'success': False, 'message': '该课程的学分替代申请正在审核中，请勿重复提交'})
    rid = execute("""INSERT INTO credit_substitute_apply (student_id, external_school, external_course, external_credit, substitute_course_id, reason)
                     VALUES (%s,%s,%s,%s,%s,%s)""",
                  (session['user_id'], school[:200], ext_course[:200], credit, sub_id,
                   str(data.get('reason') or '')[:200]))
    return jsonify({'success': True, 'message': '学分替代申请已提交', 'id': rid})


@student_bp.route('/api/student/applies')
@role_required('student')
def stu_my_applies():
    """我的各类申请记录"""
    sid = session['user_id']
    status_changes = query_all("SELECT * FROM status_change_apply WHERE student_id=%s ORDER BY created_at DESC", (sid,))
    retakes = query_all("""SELECT r.*, c.name AS course_name FROM retake_apply r
                           JOIN course c ON r.course_id=c.id WHERE r.student_id=%s ORDER BY r.created_at DESC""", (sid,))
    projects = query_all("""SELECT pa.*, p.name AS project_name, p.type AS project_type FROM project_apply pa
                            JOIN project p ON pa.project_id=p.id WHERE pa.student_id=%s ORDER BY pa.created_at DESC""", (sid,))
    substitutes = query_all("""SELECT csa.*, c.name AS substitute_course_name FROM credit_substitute_apply csa
                               LEFT JOIN course c ON csa.substitute_course_id=c.id WHERE csa.student_id=%s ORDER BY csa.created_at DESC""", (sid,))
    return jsonify({'success': True, 'data': {
        'status_changes': fmt_rows(status_changes), 'retakes': fmt_rows(retakes),
        'projects': fmt_rows(projects), 'substitutes': fmt_rows(substitutes)
    }})


@student_bp.route('/api/student/projects')
@role_required('student')
def stu_projects():
    rows = query_all("""
        SELECT p.*, (SELECT COUNT(*) FROM project_apply pa WHERE pa.project_id=p.id AND pa.student_id=%s) AS applied
        FROM project p WHERE p.is_open=1 ORDER BY p.start_date DESC""", (session['user_id'],))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/courses')
@role_required('student')
def stu_courses():
    rows = query_all("SELECT id, code, name, credit FROM course ORDER BY code")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/innovation-credits')
@role_required('student')
def stu_innovation_credits():
    rows = query_all("SELECT * FROM innovation_credit WHERE student_id=%s ORDER BY obtained_date DESC", (session['user_id'],))
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@student_bp.route('/api/student/innovation-credits/confirm', methods=['POST'])
@role_required('student')
def stu_confirm_innovation():
    cid = request.get_json().get('id')
    execute("UPDATE innovation_credit SET is_confirmed=1 WHERE id=%s AND student_id=%s", (cid, session['user_id']))
    return jsonify({'success': True, 'message': '已确认'})


@student_bp.route('/api/student/registration', methods=['GET', 'POST'])
@role_required('student')
def stu_registration():
    if request.method == 'POST':
        try:
            execute("INSERT INTO registration (student_id, semester) VALUES (%s,%s)", (session['user_id'], CURRENT_SEMESTER))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '本学期已报到注册'})
        return jsonify({'success': True, 'message': f'{CURRENT_SEMESTER} 学期报到注册成功'})
    rows = query_all("SELECT * FROM registration WHERE student_id=%s ORDER BY semester DESC", (session['user_id'],))
    registered = any(r['semester'] == CURRENT_SEMESTER for r in rows)
    return jsonify({'success': True, 'data': fmt_rows(rows), 'current_semester': CURRENT_SEMESTER, 'registered': registered})


@student_bp.route('/api/student/major-diversion', methods=['GET', 'POST'])
@role_required('student')
def stu_major_diversion():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            major_id = parse_int(data.get('major_id'), label='专业')
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})
        if not major_id:
            return jsonify({'success': False, 'message': '请选择分流专业'})
        major = query_one("SELECT id, name FROM major WHERE id=%s", (major_id,))
        if not major:
            return jsonify({'success': False, 'message': '专业不存在'})
        stu = current_student()
        if not stu:
            return jsonify({'success': False, 'message': '学生信息不存在，请重新登录'}), 401
        # 已确认后不允许自行反复修改（需联系教务处调整）
        if stu['diversion_status'] == '已确认':
            return jsonify({'success': False, 'message': '分流专业已确认，如需修改请联系教务处'})
        execute("UPDATE student SET diversion_major_id=%s, diversion_status='已确认' WHERE id=%s",
                (major_id, session['user_id']))
        log_operation('UPDATE', 'student', session['user_id'], f'专业分流确认: {major["name"]}')
        return jsonify({'success': True, 'message': f'分流专业已确认为「{major["name"]}」'})
    stu = current_student()
    majors = query_all("SELECT m.id, m.name, c.name AS college_name FROM major m JOIN college c ON m.college_id=c.id")
    diversion_major = query_one("SELECT name FROM major WHERE id=%s", (stu['diversion_major_id'],)) if stu['diversion_major_id'] else None
    return jsonify({'success': True, 'data': {
        'status': stu['diversion_status'], 'majors': fmt_rows(majors),
        'diversion_major': diversion_major['name'] if diversion_major else None,
        'current_major': stu.get('major_name')
    }})
