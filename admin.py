# -*- coding: utf-8 -*-
"""管理端蓝图"""
import io

import bcrypt
import pymysql
from flask import Blueprint, request, jsonify, send_file

from config import Config
from core import (CURRENT_SEMESTER, query_one, query_all, execute, get_db_connection,
                  fmt_rows, parse_score, parse_int, calc_grade, log_operation, role_required,
                  perm_required, _read_uploaded_table, export_schedule_xlsx, safe_cell,
                  validate_name)

admin_bp = Blueprint('admin', __name__)

REVIEW_TABLES = {
    'retake': ('retake_apply', "SELECT r.*, s.username, s.real_name AS student_name, c.name AS course_name FROM retake_apply r JOIN student s ON r.student_id=s.id JOIN course c ON r.course_id=c.id", 'r'),
    'status_change': ('status_change_apply', "SELECT a.*, s.username, s.real_name AS student_name FROM status_change_apply a JOIN student s ON a.student_id=s.id", 'a'),
    'project': ('project_apply', "SELECT pa.*, s.username, s.real_name AS student_name, p.name AS project_name FROM project_apply pa JOIN student s ON pa.student_id=s.id JOIN project p ON pa.project_id=p.id", 'pa'),
    'credit_substitute': ('credit_substitute_apply', "SELECT csa.*, s.username, s.real_name AS student_name, c.name AS substitute_course_name FROM credit_substitute_apply csa JOIN student s ON csa.student_id=s.id LEFT JOIN course c ON csa.substitute_course_id=c.id", 'csa'),
}

IMPORT_SCHEMAS = {
    'student': [
        ('username', '学号', True), ('real_name', '姓名', True), ('gender', '性别', False),
        ('class_name', '班级名称', False), ('phone', '联系电话', False), ('email', '电子邮箱', False),
        ('enrollment_date', '入学日期', False), ('status', '学籍状态', False),
        ('password', '初始密码', False),
    ],
    'teacher': [
        ('username', '工号', True), ('real_name', '姓名', True), ('gender', '性别', False),
        ('college_name', '所属学院', False), ('title', '职称', False), ('phone', '联系电话', False),
        ('email', '电子邮箱', False), ('password', '初始密码', False),
    ],
    'course': [
        ('code', '课程号', True), ('name', '课程名称', True), ('credit', '学分', False),
        ('hours', '学时', False), ('type', '课程性质', False), ('college_name', '开课学院', False),
        ('description', '课程简介', False),
    ],
    'class': [
        ('name', '班级名称', True), ('major_name', '专业名称', True), ('grade_year', '入学年份', False),
    ],
}

IMPORT_LABELS = {'student': '学生', 'teacher': '教师', 'course': '课程', 'class': '班级'}

# 单次导入行数上限：导入需要逐行 bcrypt 生成密码哈希（cost=12，约 0.2-0.3s/条），
# 行数过多会超过 gunicorn 的 60s 超时被强杀，导致整批回滚。分批导入更安全。
MAX_IMPORT_ROWS = 500
# 相同初始密码复用同一哈希，避免批量默认密码时逐行 bcrypt 造成导入超时
_PW_HASH_CACHE = {}


def _hash_password_cached(pw):
    """带缓存的 bcrypt 哈希（批量导入场景，同一密码只计算一次）"""
    h = _PW_HASH_CACHE.get(pw)
    if h is None:
        h = bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        if len(_PW_HASH_CACHE) >= 500:
            _PW_HASH_CACHE.clear()
        _PW_HASH_CACHE[pw] = h
    return h


# ==================== 班级课程继承同步（失败只记日志，不影响主流程） ====================

def _sync_student_enrollments_best_effort(student_id, class_id, cursor=None):
    """补齐单个学生本班本学期统排课（非选修）的选课记录，返回新增/恢复条数。

    统排课（必修/通识/实践）由班级指定直接排课、学生无需自主选课，
    这里把「课表已继承」同步成 enrollment 记录，教师端成绩名单才能看到该生。
    """
    try:
        from enrollment_sync import sync_student_enrollments
        stats = sync_student_enrollments(student_id, class_id, cursor=cursor) or {}
        return int(stats.get('added', 0)) + int(stats.get('restored', 0))
    except Exception as e:
        print(f'同步学生班级课程失败(student_id={student_id}): {e}')
        return 0


def _resync_student_class_best_effort(student_id, old_class_id, new_class_id):
    """学生转班后同步课程：先撤销原班未录成绩的统排课，再补齐新班统排课。"""
    try:
        from enrollment_sync import drop_stale_class_enrollments, sync_student_enrollments
        removed = 0
        if old_class_id:
            stats = drop_stale_class_enrollments(student_id, old_class_id, new_class_id) or {}
            removed = int(stats.get('removed', 0))
        stats2 = sync_student_enrollments(student_id, new_class_id) or {}
        return removed + int(stats2.get('added', 0)) + int(stats2.get('restored', 0))
    except Exception as e:
        print(f'转班同步课程失败(student_id={student_id}): {e}')
        return 0


def _sync_offering_enrollments_best_effort(offering_id):
    """开课指定班级后，把该班学生补齐进教学班（仅非选修统排课），返回新增人数。"""
    try:
        from enrollment_sync import ensure_offering_enrollments
        stats = ensure_offering_enrollments(offering_id) or {}
        return int(stats.get('added', 0))
    except Exception as e:
        print(f'同步教学班学生失败(offering_id={offering_id}): {e}')
        return 0


def _sync_offering_classes_best_effort(offering_id, added_class_ids, removed_class_ids):
    """开课修改授课班级后同步学生（仅非选修统排课），返回 (新增, 移除)。"""
    try:
        from enrollment_sync import sync_offering_classes
        stats = sync_offering_classes(offering_id, added_class_ids, removed_class_ids) or {}
        return int(stats.get('added', 0)), int(stats.get('removed', 0))
    except Exception as e:
        print(f'同步教学班班级变更失败(offering_id={offering_id}): {e}')
        return 0, 0


def _repair_selected_count_best_effort():
    """把教学班冗余的 selected_count 拉回 enrollment 实际人数。

    删除学生/级联删除选课记录后 selected_count 不会自动减少，需顺带重算，
    否则教学班「已选人数」与名单不一致、容量校验也会失真。
    """
    try:
        from enrollment_sync import recompute_selected_count
        recompute_selected_count()
    except Exception as e:
        print(f'重算教学班已选人数失败: {e}')


@admin_bp.route('/api/admin/dashboard')
@role_required('admin')
def adm_dashboard():
    return jsonify({'success': True, 'data': {
        'student_count': query_one("SELECT COUNT(*) c FROM student")['c'],
        'teacher_count': query_one("SELECT COUNT(*) c FROM teacher")['c'],
        'course_count': query_one("SELECT COUNT(*) c FROM course")['c'],
        'offering_count': query_one("SELECT COUNT(*) c FROM course_offering WHERE semester=%s", (CURRENT_SEMESTER,))['c'],
        'pending_applies': (query_one("SELECT COUNT(*) c FROM retake_apply WHERE status='待审核'")['c']
                            + query_one("SELECT COUNT(*) c FROM status_change_apply WHERE status='待审核'")['c']
                            + query_one("SELECT COUNT(*) c FROM project_apply WHERE status='待审核'")['c']
                            + query_one("SELECT COUNT(*) c FROM credit_substitute_apply WHERE status='待审核'")['c']),
        'eval_count': query_one("SELECT COUNT(*) c FROM evaluation")['c']
    }})


# ---- 组织架构：学院/专业/班级 ----
@admin_bp.route('/api/admin/colleges', methods=['GET', 'POST'])
@role_required('admin')
def adm_colleges():
    if request.method == 'POST':
        data = request.get_json() or {}
        try:
            rid = execute("INSERT INTO college (code, name) VALUES (%s,%s)", (data.get('code'), data['name']))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '学院代码已存在'})
        log_operation('INSERT', 'college', rid, f"新增学院: {data['name']}")
        return jsonify({'success': True, 'message': '学院已添加', 'id': rid})
    rows = query_all("SELECT * FROM college ORDER BY id")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/colleges/<int:cid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_college_detail(cid):
    if request.method == 'DELETE':
        execute("DELETE FROM college WHERE id=%s", (cid,))
        log_operation('DELETE', 'college', cid, '删除学院')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'success': False, 'message': '学院名称不能为空'})
    execute("UPDATE college SET code=%s, name=%s WHERE id=%s", (data.get('code'), data['name'], cid))
    log_operation('UPDATE', 'college', cid, f"修改学院: {data['name']}")
    return jsonify({'success': True, 'message': '已更新'})


@admin_bp.route('/api/admin/majors', methods=['GET', 'POST'])
@role_required('admin')
def adm_majors():
    if request.method == 'POST':
        data = request.get_json() or {}
        try:
            rid = execute("INSERT INTO major (college_id, code, name) VALUES (%s,%s,%s)",
                          (data['college_id'], data.get('code'), data['name']))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '专业代码已存在'})
        log_operation('INSERT', 'major', rid, f"新增专业: {data['name']}")
        return jsonify({'success': True, 'message': '专业已添加', 'id': rid})
    rows = query_all("""SELECT m.*, c.name AS college_name FROM major m
                        JOIN college c ON m.college_id=c.id ORDER BY m.id""")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/majors/<int:mid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_major_detail(mid):
    if request.method == 'DELETE':
        execute("DELETE FROM major WHERE id=%s", (mid,))
        log_operation('DELETE', 'major', mid, '删除专业')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    if not data.get('college_id') or not data.get('name'):
        return jsonify({'success': False, 'message': '所属学院与专业名称不能为空'})
    execute("UPDATE major SET college_id=%s, code=%s, name=%s WHERE id=%s",
            (data['college_id'], data.get('code'), data['name'], mid))
    log_operation('UPDATE', 'major', mid, f"修改专业: {data['name']}")
    return jsonify({'success': True, 'message': '已更新'})


@admin_bp.route('/api/admin/classes', methods=['GET', 'POST'])
@role_required('admin')
def adm_classes():
    if request.method == 'POST':
        data = request.get_json() or {}
        rid = execute("INSERT INTO class (major_id, name, grade_year) VALUES (%s,%s,%s)",
                      (data['major_id'], data['name'], data['grade_year']))
        log_operation('INSERT', 'class', rid, f"新增班级: {data['name']}")
        return jsonify({'success': True, 'message': '班级已添加', 'id': rid})
    rows = query_all("""SELECT cl.*, m.name AS major_name, c.name AS college_name,
                        (SELECT COUNT(*) FROM student s WHERE s.class_id=cl.id) AS student_count
                        FROM class cl JOIN major m ON cl.major_id=m.id JOIN college c ON m.college_id=c.id
                        ORDER BY cl.grade_year DESC, cl.name""")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/classes/<int:cid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_class_detail(cid):
    if request.method == 'DELETE':
        execute("DELETE FROM class WHERE id=%s", (cid,))
        log_operation('DELETE', 'class', cid, '删除班级')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    if not data.get('major_id') or not data.get('name'):
        return jsonify({'success': False, 'message': '所属专业与班级名称不能为空'})
    execute("UPDATE class SET major_id=%s, name=%s, grade_year=%s WHERE id=%s",
            (data['major_id'], data['name'], data['grade_year'], cid))
    log_operation('UPDATE', 'class', cid, f"修改班级: {data['name']}")
    return jsonify({'success': True, 'message': '已更新'})


# ---- 学生管理 ----
@admin_bp.route('/api/admin/students', methods=['GET', 'POST'])
@role_required('admin')
def adm_students():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            username = validate_name(data.get('username'), '学号', 32)
            real_name = validate_name(data.get('real_name'), '姓名', 64)
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})
        # 管理员指定/默认的初始密码：默认 123456（业务约定：初始密码允许弱口令，
        # 且不强制首次改密，学生登录后可在个人信息维护里自行修改）
        pw = (data.get('password') or '').strip() or Config.DEFAULT_INITIAL_PASSWORD
        if len(pw) > 72:   # bcrypt 只使用前 72 字节，超长会被静默截断
            return jsonify({'success': False, 'message': '初始密码长度不能超过 72 位'})
        pw_hash = bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        try:
            rid = execute("""INSERT INTO student (username, password_hash, real_name, gender, class_id, phone, email, enrollment_date, status, must_change_pwd)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0)""",
                          (username, pw_hash, real_name, data.get('gender', '男'),
                           data.get('class_id'), data.get('phone'), data.get('email'),
                           data.get('enrollment_date'), data.get('status', '在读')))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '学号已存在'})
        inherited = _sync_student_enrollments_best_effort(rid, data.get('class_id'))
        log_operation('INSERT', 'student', rid, f"新增学生: {real_name}({username})")
        msg = f'学生已添加，初始密码：{pw}'
        if inherited:
            msg += f'；已自动继承本班 {inherited} 门课程'
        return jsonify({'success': True, 'id': rid, 'message': msg})

    keyword = request.args.get('keyword', '').strip()
    class_id = request.args.get('class_id', type=int)
    page = max(request.args.get('page', 1, type=int), 1)
    page_size = min(max(request.args.get('page_size', 20, type=int), 1), 100)

    where = " WHERE 1=1"
    params = []
    if keyword:
        where += " AND (s.username LIKE %s OR s.real_name LIKE %s)"
        params += [f'%{keyword}%', f'%{keyword}%']
    if class_id:
        where += " AND s.class_id = %s"
        params.append(class_id)

    total = query_one("SELECT COUNT(*) c FROM student s" + where, params)['c']
    sql = """SELECT s.id, s.username, s.real_name, s.gender, s.phone, s.email, s.status, s.is_frozen,
                    s.enrollment_date, s.class_id, s.avatar, cl.name AS class_name, m.name AS major_name
             FROM student s LEFT JOIN class cl ON s.class_id=cl.id LEFT JOIN major m ON cl.major_id=m.id""" + where
    sql += " ORDER BY s.username LIMIT %s OFFSET %s"
    rows = query_all(sql, params + [page_size, (page - 1) * page_size])
    for r in rows:
        if r.get('avatar'):
            r['avatar'] = f"/uploads/avatar/{r['avatar']}"
    return jsonify({'success': True, 'data': fmt_rows(rows), 'total': total, 'page': page, 'page_size': page_size})


@admin_bp.route('/api/admin/students/<int:sid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_student_detail(sid):
    if request.method == 'DELETE':
        execute("DELETE FROM student WHERE id=%s", (sid,))
        # 学生级联删除 enrollment 后，同步修正各教学班冗余的已选人数
        _repair_selected_count_best_effort()
        log_operation('DELETE', 'student', sid, '删除学生')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json(silent=True) or {}
    if 'real_name' in data:
        try:
            data['real_name'] = validate_name(data.get('real_name'), '姓名', 64)
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})
    allowed = ('real_name', 'gender', 'class_id', 'phone', 'email', 'status', 'is_frozen')
    sets, params = [], []
    for key in allowed:
        if key in data:
            sets.append(f"{key}=%s")   # 列名来自固定白名单
            params.append(data[key])
    if not sets:
        return jsonify({'success': False, 'message': '没有需要更新的字段'})
    params.append(sid)
    # 只更新提交的字段：避免前端漏传 is_frozen 时把已冻结学生静默解冻
    old = query_one("SELECT class_id FROM student WHERE id=%s", (sid,))
    execute(f"UPDATE student SET {', '.join(sets)} WHERE id=%s", params)
    reset_pw = None
    if data.get('reset_password'):
        # 重置密码 = 重置为默认初始密码（业务约定 123456），不再强制首次改密
        reset_pw = Config.DEFAULT_INITIAL_PASSWORD
        pw_hash = bcrypt.hashpw(reset_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        execute("UPDATE student SET password_hash=%s, must_change_pwd=0 WHERE id=%s", (pw_hash, sid))
        log_operation('UPDATE', 'student', sid, f'重置学生密码为 {reset_pw}')
    # 班级变更后同步班级统排课：撤销原班未录成绩的课，补齐新班课程
    class_changed = ('class_id' in data and old is not None
                     and (old.get('class_id') or None) != (data.get('class_id') or None))
    if class_changed:
        _resync_student_class_best_effort(sid, old.get('class_id'), data.get('class_id'))
    log_operation('UPDATE', 'student', sid, f"修改学生: {data.get('real_name') or sid}")
    msg = '已更新'
    if class_changed:
        msg += '（已按新班级同步课程）'
    if reset_pw:
        msg += f'，新密码为：{reset_pw}'
    return jsonify({'success': True, 'message': msg})


# ---- 教师管理 ----
@admin_bp.route('/api/admin/teachers', methods=['GET', 'POST'])
@role_required('admin')
def adm_teachers():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            username = validate_name(data.get('username'), '工号', 32)
            real_name = validate_name(data.get('real_name'), '姓名', 64)
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})
        # 初始密码默认 123456（同学生端业务约定：允许弱初始密码、不强制首次改密）
        pw = (data.get('password') or '').strip() or Config.DEFAULT_INITIAL_PASSWORD
        if len(pw) > 72:
            return jsonify({'success': False, 'message': '初始密码长度不能超过 72 位'})
        pw_hash = bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        try:
            rid = execute("""INSERT INTO teacher (username, password_hash, real_name, gender, college_id, title, phone, email, must_change_pwd)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)""",
                          (username, pw_hash, real_name, data.get('gender', '男'),
                           data.get('college_id'), data.get('title'), data.get('phone'), data.get('email')))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '工号已存在'})
        log_operation('INSERT', 'teacher', rid, f"新增教师: {real_name}")
        return jsonify({'success': True, 'id': rid,
                        'message': f'教师已添加，初始密码：{pw}'})

    keyword = request.args.get('keyword', '').strip()
    page = max(request.args.get('page', 1, type=int), 1)
    page_size = min(max(request.args.get('page_size', 20, type=int), 1), 100)

    where = " WHERE 1=1"
    params = []
    if keyword:
        where += " AND (t.username LIKE %s OR t.real_name LIKE %s)"
        params += [f'%{keyword}%', f'%{keyword}%']

    total = query_one("SELECT COUNT(*) c FROM teacher t" + where, params)['c']
    sql = """SELECT t.*, c.name AS college_name FROM teacher t
             LEFT JOIN college c ON t.college_id=c.id""" + where
    sql += " ORDER BY t.username LIMIT %s OFFSET %s"
    rows = query_all(sql, params + [page_size, (page - 1) * page_size])
    for r in rows:
        r.pop('password_hash', None)
        if r.get('avatar'):
            r['avatar'] = f"/uploads/avatar/{r['avatar']}"
    return jsonify({'success': True, 'data': fmt_rows(rows), 'total': total, 'page': page, 'page_size': page_size})


@admin_bp.route('/api/admin/teachers/<int:tid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_teacher_detail(tid):
    if request.method == 'DELETE':
        execute("DELETE FROM teacher WHERE id=%s", (tid,))
        log_operation('DELETE', 'teacher', tid, '删除教师')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    try:
        real_name = validate_name(data.get('real_name'), '姓名', 64)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    execute("""UPDATE teacher SET real_name=%s, gender=%s, college_id=%s, title=%s, phone=%s, email=%s, is_active=%s WHERE id=%s""",
            (real_name, data.get('gender'), data.get('college_id'), data.get('title'),
             data.get('phone'), data.get('email'), data.get('is_active', 1), tid))
    reset_pw = None
    if data.get('reset_password'):
        # 重置密码 = 重置为默认初始密码（业务约定 123456），不强制首次改密
        reset_pw = Config.DEFAULT_INITIAL_PASSWORD
        pw_hash = bcrypt.hashpw(reset_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        execute("UPDATE teacher SET password_hash=%s, must_change_pwd=0 WHERE id=%s", (pw_hash, tid))
        log_operation('UPDATE', 'teacher', tid, f'重置教师密码为 {reset_pw}')
    log_operation('UPDATE', 'teacher', tid, f"修改教师: {data['real_name']}")
    msg = '已更新'
    if reset_pw:
        msg += f'，新密码为：{reset_pw}'
    return jsonify({'success': True, 'message': msg})


# ---- 课程管理 ----
@admin_bp.route('/api/admin/courses', methods=['GET', 'POST'])
@role_required('admin')
def adm_courses():
    if request.method == 'POST':
        data = request.get_json() or {}
        if not data.get('code') or not data.get('name'):
            return jsonify({'success': False, 'message': '课程号与课程名称不能为空'})
        try:
            credit = float(data.get('credit', 0) or 0)
            hours = int(float(data.get('hours', 0) or 0))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '学分/学时必须是数字'})
        if not (0 <= credit <= 100) or not (0 <= hours <= 1000):
            return jsonify({'success': False, 'message': '学分应在 0-100 之间，学时应在 0-1000 之间'})
        try:
            rid = execute("""INSERT INTO course (code, name, credit, hours, type, college_id, description)
                             VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                          (data['code'], data['name'], credit, hours,
                           data.get('type', '必修'), data.get('college_id'), data.get('description')))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '课程号已存在'})
        log_operation('INSERT', 'course', rid, f"新增课程: {data['name']}")
        return jsonify({'success': True, 'message': '课程已添加', 'id': rid})

    keyword = request.args.get('keyword', '').strip()
    page = max(request.args.get('page', 1, type=int), 1)
    page_size = min(max(request.args.get('page_size', 20, type=int), 1), 100)

    where = " WHERE 1=1"
    params = []
    if keyword:
        where += " AND (c.code LIKE %s OR c.name LIKE %s)"
        params += [f'%{keyword}%', f'%{keyword}%']

    total = query_one("SELECT COUNT(*) c FROM course c" + where, params)['c']
    sql = """SELECT c.*, co.name AS college_name FROM course c LEFT JOIN college co ON c.college_id=co.id""" + where
    sql += " ORDER BY c.code LIMIT %s OFFSET %s"
    rows = query_all(sql, params + [page_size, (page - 1) * page_size])
    return jsonify({'success': True, 'data': fmt_rows(rows), 'total': total, 'page': page, 'page_size': page_size})


@admin_bp.route('/api/admin/courses/<int:cid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_course_detail(cid):
    if request.method == 'DELETE':
        execute("DELETE FROM course WHERE id=%s", (cid,))
        log_operation('DELETE', 'course', cid, '删除课程')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    if not data.get('code') or not data.get('name'):
        return jsonify({'success': False, 'message': '课程代码与名称不能为空'})
    execute("""UPDATE course SET code=%s, name=%s, credit=%s, hours=%s, type=%s, college_id=%s, description=%s WHERE id=%s""",
            (data['code'], data['name'], data.get('credit'), data.get('hours'),
             data.get('type'), data.get('college_id'), data.get('description'), cid))
    log_operation('UPDATE', 'course', cid, f"修改课程: {data['name']}")
    return jsonify({'success': True, 'message': '已更新'})


# ---- 开课管理 ----
@admin_bp.route('/api/admin/offerings', methods=['GET', 'POST'])
@role_required('admin')
def adm_offerings():
    if request.method == 'POST':
        data = request.get_json() or {}
        if not data.get('course_id') or not data.get('semester'):
            return jsonify({'success': False, 'message': '课程与学期不能为空'})
        try:
            max_count = parse_int(data.get('max_count', 60), default=60, min_value=1, max_value=10000, label='容量')
            usual_ratio = parse_int(data.get('usual_ratio', 40), default=40, min_value=0, max_value=100, label='平时占比')
            exam_ratio = parse_int(data.get('exam_ratio', 60), default=60, min_value=0, max_value=100, label='考试占比')
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})
        if usual_ratio + exam_ratio != 100:
            return jsonify({'success': False, 'message': '平时占比与考试占比之和须为 100%'})
        rid = execute("""INSERT INTO course_offering (course_id, teacher_id, semester, max_count, status, usual_ratio, exam_ratio)
                         VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                      (data['course_id'], data.get('teacher_id'), data.get('semester', CURRENT_SEMESTER),
                       max_count, data.get('status', '开放'), usual_ratio, exam_ratio))
        # 写入班级关联（可多选，支持合班；不选则不限班级）
        for cid in (data.get('class_ids') or []):
            execute("INSERT IGNORE INTO offering_class (offering_id, class_id) VALUES (%s,%s)", (rid, cid))
        # 班级统排课（必修/通识/实践）：指定班级的在读学生自动加入本教学班
        inherited = _sync_offering_enrollments_best_effort(rid)
        log_operation('INSERT', 'course_offering', rid, f"新增开课: course_id={data['course_id']}")
        msg = '开课已添加'
        if inherited:
            msg += f'，已自动加入 {inherited} 名学生'
        return jsonify({'success': True, 'message': msg, 'id': rid})

    semester = request.args.get('semester')
    sql = """SELECT co.*, c.code, c.name AS course_name, c.credit, t.real_name AS teacher_name,
                    (SELECT GROUP_CONCAT(cl.name ORDER BY cl.name SEPARATOR '、')
                     FROM offering_class oc JOIN class cl ON oc.class_id=cl.id
                     WHERE oc.offering_id=co.id) AS class_names
             FROM course_offering co JOIN course c ON co.course_id=c.id
             LEFT JOIN teacher t ON co.teacher_id=t.id WHERE 1=1"""
    params = []
    if semester:
        sql += " AND co.semester=%s"
        params.append(semester)
    sql += " ORDER BY co.semester DESC, c.code"
    rows = query_all(sql, params)
    for r in rows:
        ids = query_all("SELECT class_id FROM offering_class WHERE offering_id=%s", (r['id'],))
        r['class_ids'] = [x['class_id'] for x in ids]
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/offerings/<int:oid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_offering_detail(oid):
    if request.method == 'DELETE':
        execute("DELETE FROM course_offering WHERE id=%s", (oid,))
        log_operation('DELETE', 'course_offering', oid, '删除开课')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json(silent=True) or {}
    old = query_one("SELECT * FROM course_offering WHERE id=%s", (oid,))
    if not old:
        return jsonify({'success': False, 'message': '开课记录不存在'})
    if 'course_id' in data and data['course_id'] and int(data['course_id']) != old['course_id']:
        used = query_one("SELECT COUNT(*) c FROM enrollment WHERE offering_id=%s", (oid,))
        if used and used['c']:
            return jsonify({'success': False, 'message': '该教学班已有学生选课，不能更换课程（会改变已有成绩的归属）'})
    try:
        max_count = parse_int(data.get('max_count', old['max_count']), default=old['max_count'],
                              min_value=1, max_value=10000, label='容量')
        usual_ratio = parse_int(data.get('usual_ratio', old['usual_ratio']), default=old['usual_ratio'],
                                min_value=0, max_value=100, label='平时占比')
        exam_ratio = parse_int(data.get('exam_ratio', old['exam_ratio']), default=old['exam_ratio'],
                               min_value=0, max_value=100, label='考试占比')
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    # 与新增开课保持同样的比例校验，避免保存出"30% + 30%"这种非法配置
    if usual_ratio + exam_ratio != 100:
        return jsonify({'success': False, 'message': '平时占比与考试占比之和须为 100%'})
    if max_count < (old['selected_count'] or 0):
        return jsonify({'success': False, 'message': f"容量不能小于已选人数（{old['selected_count']}）"})
    semester = data.get('semester') or old['semester']
    # 记录修改前的授课班级，用于同步新增/移除班级的学生选课
    old_class_ids = set()
    if 'class_ids' in data:
        old_class_ids = {r['class_id'] for r in query_all(
            "SELECT class_id FROM offering_class WHERE offering_id=%s", (oid,))}
    execute("""UPDATE course_offering SET course_id=%s, teacher_id=%s, semester=%s, max_count=%s, status=%s,
               usual_ratio=%s, exam_ratio=%s WHERE id=%s""",
            (data.get('course_id') or old['course_id'],
             data['teacher_id'] if 'teacher_id' in data else old['teacher_id'],
             semester, max_count, data.get('status') or old['status'], usual_ratio, exam_ratio, oid))
    # 更新班级关联（先删后插）
    if 'class_ids' in data:
        new_class_ids = set()
        for cid in (data.get('class_ids') or []):
            try:
                new_class_ids.add(int(cid))
            except (TypeError, ValueError):
                continue
        execute("DELETE FROM offering_class WHERE offering_id=%s", (oid,))
        for cid in new_class_ids:
            execute("INSERT IGNORE INTO offering_class (offering_id, class_id) VALUES (%s,%s)", (oid, cid))
        # 新增班级：该班在读学生自动加入；移除班级：撤销未录成绩的统排课记录
        _sync_offering_classes_best_effort(oid, new_class_ids - old_class_ids, old_class_ids - new_class_ids)
    log_operation('UPDATE', 'course_offering', oid, '修改开课')
    return jsonify({'success': True, 'message': '已更新'})


# ---- 排课 / 考试冲突检测 ----

def _parse_weeks(s):
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


def _weeks_overlap(w1, t1, w2, t2):
    return bool(_effective_weeks(w1, t1) & _effective_weeks(w2, t2))


def _find_schedule_conflict(offering_id, weekday, start_section, end_section,
                            weeks, week_type, classroom_id, exclude_id=None):
    """检测排课冲突：同一教室或同一教师在同学期同时段被重复安排；参数非法时抛 ValueError"""
    weekday = int(weekday)
    start_section = int(start_section)
    end_section = int(end_section)
    if not (1 <= weekday <= 7):
        raise ValueError('星期必须在 1-7 之间')
    if start_section < 1 or end_section > 20:
        raise ValueError('节次范围不合法（1-20）')
    if start_section > end_section:
        raise ValueError('开始节次不能大于结束节次')
    off = query_one("SELECT semester, teacher_id FROM course_offering WHERE id=%s", (offering_id,))
    if not off:
        raise ValueError('教学班不存在')
    rows = query_all("""SELECT cs.id, cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
                               cs.classroom_id, c.name AS course_name, t.real_name AS teacher_name,
                               co.teacher_id, cr.building, cr.room
                        FROM course_schedule cs
                        JOIN course_offering co ON cs.offering_id=co.id
                        JOIN course c ON co.course_id=c.id
                        LEFT JOIN teacher t ON co.teacher_id=t.id
                        LEFT JOIN classroom cr ON cs.classroom_id=cr.id
                        WHERE co.semester=%s AND cs.weekday=%s
                          AND cs.start_section <= %s AND cs.end_section >= %s""",
                     (off['semester'], weekday, end_section, start_section))
    for r in rows:
        if exclude_id and r['id'] == exclude_id:
            continue
        if not _weeks_overlap(weeks, week_type, r['weeks'], r['week_type']):
            continue
        if classroom_id and r['classroom_id'] and int(r['classroom_id']) == int(classroom_id):
            return f"教室 {r['building'] or ''}{r['room'] or ''} 在该时段已被「{r['course_name']}」占用"
        if off['teacher_id'] and r['teacher_id'] and int(r['teacher_id']) == int(off['teacher_id']):
            return f"教师「{r['teacher_name']}」在该时段已有「{r['course_name']}」"
    return None


def _find_exam_conflict(exam_date, start_time, end_time, classroom_id):
    """检测考试教室冲突（同一教室同一天时间重叠）"""
    if not classroom_id:
        return None
    dup = query_one("""SELECT c.name AS course_name, cr.building, cr.room, ex.start_time, ex.end_time
                       FROM exam ex
                       JOIN course_offering co ON ex.offering_id=co.id
                       JOIN course c ON co.course_id=c.id
                       LEFT JOIN classroom cr ON ex.classroom_id=cr.id
                       WHERE ex.exam_date=%s AND ex.classroom_id=%s
                         AND ex.start_time < %s AND ex.end_time > %s LIMIT 1""",
                    (exam_date, classroom_id, end_time or '23:59', start_time or '00:00'))
    if dup:
        return (f"教室 {dup['building'] or ''}{dup['room'] or ''} 在 {exam_date} "
                f"{dup['start_time']}-{dup['end_time']} 已被「{dup['course_name']}」安排考试")
    return None


# ---- 排课管理 ----
@admin_bp.route('/api/admin/schedules', methods=['GET', 'POST'])
@role_required('admin')
def adm_schedules():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            offering_id = parse_int(data.get('offering_id'), label='教学班')
            weekday = parse_int(data.get('weekday'), label='星期')
            start_section = parse_int(data.get('start_section'), label='开始节次')
            end_section = parse_int(data.get('end_section'), label='结束节次')
            weeks = data.get('weeks', '1-16')
            week_type = data.get('week_type', '全周')
            classroom_id = data.get('classroom_id')
            conflict = _find_schedule_conflict(offering_id, weekday, start_section, end_section,
                                               weeks, week_type, classroom_id)
        except (ValueError, TypeError) as e:
            return jsonify({'success': False, 'message': str(e) or '排课参数不合法'})
        if conflict:
            return jsonify({'success': False, 'message': f'排课冲突：{conflict}'})
        rid = execute("""INSERT INTO course_schedule (offering_id, weekday, start_section, end_section, weeks, week_type, classroom_id)
                         VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                      (offering_id, weekday, start_section, end_section, weeks, week_type, classroom_id))
        log_operation('INSERT', 'course_schedule', rid, f"新增排课: offering_id={offering_id}")
        return jsonify({'success': True, 'message': '排课已添加', 'id': rid})

    offering_id = request.args.get('offering_id', type=int)
    sql = """SELECT cs.*, c.name AS course_name, co.semester, t.real_name AS teacher_name, cr.building, cr.room,
                    (SELECT GROUP_CONCAT(cl.name ORDER BY cl.name SEPARATOR '、')
                     FROM offering_class oc JOIN class cl ON oc.class_id=cl.id
                     WHERE oc.offering_id=cs.offering_id) AS class_names
             FROM course_schedule cs
             JOIN course_offering co ON cs.offering_id=co.id
             JOIN course c ON co.course_id=c.id
             LEFT JOIN teacher t ON co.teacher_id=t.id
             LEFT JOIN classroom cr ON cs.classroom_id=cr.id WHERE 1=1"""
    params = []
    if offering_id:
        sql += " AND cs.offering_id=%s"
        params.append(offering_id)
    sql += " ORDER BY co.semester DESC, cs.weekday, cs.start_section"
    rows = query_all(sql, params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/schedules/<int:sid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_schedule_detail(sid):
    if request.method == 'DELETE':
        execute("DELETE FROM course_schedule WHERE id=%s", (sid,))
        log_operation('DELETE', 'course_schedule', sid, '删除排课')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json(silent=True) or {}
    old = query_one("SELECT * FROM course_schedule WHERE id=%s", (sid,))
    if not old:
        return jsonify({'success': False, 'message': '排课记录不存在'})
    try:
        weekday = parse_int(data.get('weekday', old['weekday']), label='星期')
        start_section = parse_int(data.get('start_section', old['start_section']), label='开始节次')
        end_section = parse_int(data.get('end_section', old['end_section']), label='结束节次')
        weeks = data.get('weeks', old['weeks'])
        week_type = data.get('week_type', old['week_type'])
        classroom_id = data['classroom_id'] if 'classroom_id' in data else old['classroom_id']
        conflict = _find_schedule_conflict(old['offering_id'], weekday, start_section, end_section,
                                           weeks, week_type, classroom_id, exclude_id=sid)
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'message': str(e) or '排课参数不合法'})
    if conflict:
        return jsonify({'success': False, 'message': f'排课冲突：{conflict}'})
    execute("""UPDATE course_schedule SET weekday=%s, start_section=%s, end_section=%s,
               weeks=%s, week_type=%s, classroom_id=%s WHERE id=%s""",
            (weekday, start_section, end_section, weeks, week_type, classroom_id, sid))
    log_operation('UPDATE', 'course_schedule', sid, '修改排课')
    return jsonify({'success': True, 'message': '排课已更新'})


@admin_bp.route('/api/admin/major-schedule')
@role_required('admin')
def adm_major_schedule():
    """按专业维度查看课表：该专业各班级被指定课程的排课汇总（分班排课制）"""
    major_id = request.args.get('major_id', type=int)
    semester = request.args.get('semester', CURRENT_SEMESTER)
    if not major_id:
        return jsonify({'success': False, 'message': '请指定专业'})

    classes = query_all("SELECT id, name FROM class WHERE major_id=%s ORDER BY name", (major_id,))
    class_ids = [c['id'] for c in classes]
    if not class_ids:
        return jsonify({'success': True, 'data': [], 'classes': [], 'message': '该专业暂无班级'})

    placeholders = ','.join(['%s'] * len(class_ids))
    rows = query_all(f"""
        SELECT cs.id, cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
               c.name AS course_name, c.code, t.real_name AS teacher_name,
               cr.building, cr.room, co.id AS offering_id, co.semester
        FROM offering_class oc
        JOIN course_offering co ON oc.offering_id = co.id
        JOIN course c ON co.course_id = c.id
        LEFT JOIN teacher t ON co.teacher_id = t.id
        JOIN course_schedule cs ON cs.offering_id = co.id
        LEFT JOIN classroom cr ON cs.classroom_id = cr.id
        WHERE oc.class_id IN ({placeholders}) AND co.semester = %s
        GROUP BY cs.id
        ORDER BY cs.weekday, cs.start_section""", (*class_ids, semester))

    class_stat = query_all(f"""
        SELECT cl.id, cl.name, COUNT(s.id) AS student_count
        FROM class cl LEFT JOIN student s ON s.class_id = cl.id
        WHERE cl.id IN ({placeholders}) GROUP BY cl.id, cl.name ORDER BY cl.name""", class_ids)

    return jsonify({'success': True, 'data': fmt_rows(rows),
                    'classes': fmt_rows(class_stat)})


@admin_bp.route('/api/admin/major-schedule/export')
@role_required('admin')
def adm_major_schedule_export():
    """导出专业课表（Excel）"""
    major_id = request.args.get('major_id', type=int)
    semester = request.args.get('semester', CURRENT_SEMESTER)
    if not major_id:
        return jsonify({'success': False, 'message': '请指定专业'})

    major = query_one("""SELECT m.name, c.name AS college_name FROM major m
                         JOIN college c ON m.college_id=c.id WHERE m.id=%s""", (major_id,))
    if not major:
        return jsonify({'success': False, 'message': '专业不存在'})

    classes = query_all("SELECT id, name FROM class WHERE major_id=%s ORDER BY name", (major_id,))
    class_ids = [c['id'] for c in classes]
    rows = []
    if class_ids:
        placeholders = ','.join(['%s'] * len(class_ids))
        rows = query_all(f"""
            SELECT cs.id, cs.weekday, cs.start_section, cs.end_section, cs.weeks, cs.week_type,
                   c.name AS course_name, c.code, t.real_name AS teacher_name,
                   cr.building, cr.room
            FROM offering_class oc
            JOIN course_offering co ON oc.offering_id = co.id
            JOIN course c ON co.course_id = c.id
            LEFT JOIN teacher t ON co.teacher_id = t.id
            JOIN course_schedule cs ON cs.offering_id = co.id
            LEFT JOIN classroom cr ON cs.classroom_id = cr.id
            WHERE oc.class_id IN ({placeholders}) AND co.semester = %s
            GROUP BY cs.id
            ORDER BY cs.weekday, cs.start_section""", (*class_ids, semester))

    class_names = '、'.join(c['name'] for c in classes) or '无班级'
    subtitle = f"{major['college_name']} · {major['name']}　班级：{class_names}　学期：{semester}"
    buf = export_schedule_xlsx(rows, '专业课表', subtitle)
    return send_file(buf, as_attachment=True,
                     download_name=f"专业课表-{major['name']}-{semester}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ---- 作息时间 ----
@admin_bp.route('/api/admin/section-times', methods=['GET', 'PUT'])
@role_required('admin')
def adm_section_times():
    """作息时间：查看 / 批量修改每节课的开始结束时间"""
    if request.method == 'PUT':
        data = request.get_json() or {}
        items = data.get('items') or []
        if not items:
            return jsonify({'success': False, 'message': '没有要保存的数据'})
        import re as _re
        pattern = _re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
        for it in items:
            try:
                sec = int(it.get('section'))
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': '节次不合法'})
            st = (it.get('start_time') or '').strip()
            et = (it.get('end_time') or '').strip()
            if not pattern.match(st) or not pattern.match(et):
                return jsonify({'success': False, 'message': f'第{sec}节时间格式应为 HH:MM'})
            if st >= et:
                return jsonify({'success': False, 'message': f'第{sec}节结束时间须晚于开始时间'})
        for it in items:
            execute("UPDATE section_time SET start_time=%s, end_time=%s WHERE section=%s",
                    ((it['start_time'] or '').strip(), (it['end_time'] or '').strip(), int(it['section'])))
        log_operation('UPDATE', 'section_time', None, f'修改作息时间（{len(items)} 节）')
        return jsonify({'success': True, 'message': '作息时间已保存'})

    rows = query_all("SELECT section, start_time, end_time FROM section_time ORDER BY section")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


# ---- 教室管理 ----
@admin_bp.route('/api/admin/classrooms', methods=['GET', 'POST'])
@role_required('admin')
def adm_classrooms():
    if request.method == 'POST':
        data = request.get_json() or {}
        try:
            rid = execute("INSERT INTO classroom (building, room, capacity) VALUES (%s,%s,%s)",
                          (data['building'], data['room'], data.get('capacity', 60)))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '该教室已存在'})
        log_operation('INSERT', 'classroom', rid, f"新增教室: {data['building']}{data['room']}")
        return jsonify({'success': True, 'message': '教室已添加', 'id': rid})
    rows = query_all("SELECT * FROM classroom ORDER BY building, room")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/classrooms/<int:cid>', methods=['DELETE'])
@role_required('admin')
def adm_classroom_detail(cid):
    execute("DELETE FROM classroom WHERE id=%s", (cid,))
    log_operation('DELETE', 'classroom', cid, '删除教室')
    return jsonify({'success': True, 'message': '已删除'})


# ---- 考试安排 ----
@admin_bp.route('/api/admin/exams', methods=['GET', 'POST'])
@role_required('admin')
def adm_exams():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        offering_id = data.get('offering_id')
        exam_date = data.get('exam_date')
        if not offering_id or not exam_date:
            return jsonify({'success': False, 'message': '课程与考试日期不能为空'})
        if not query_one("SELECT id FROM course_offering WHERE id=%s", (offering_id,)):
            return jsonify({'success': False, 'message': '教学班不存在'})
        conflict = _find_exam_conflict(exam_date, data.get('start_time'), data.get('end_time'),
                                       data.get('classroom_id'))
        if conflict:
            return jsonify({'success': False, 'message': f'考试安排冲突：{conflict}'})
        rid = execute("""INSERT INTO exam (offering_id, exam_date, start_time, end_time, classroom_id, exam_type)
                         VALUES (%s,%s,%s,%s,%s,%s)""",
                      (offering_id, exam_date, data.get('start_time'),
                       data.get('end_time'), data.get('classroom_id'), data.get('exam_type', '期末')))
        log_operation('INSERT', 'exam', rid, f"新增考试: offering_id={offering_id}")
        return jsonify({'success': True, 'message': '考试安排已添加', 'id': rid})
    rows = query_all("""
        SELECT ex.*, c.name AS course_name, co.semester, t.real_name AS teacher_name, cr.building, cr.room
        FROM exam ex JOIN course_offering co ON ex.offering_id=co.id
        JOIN course c ON co.course_id=c.id
        LEFT JOIN teacher t ON co.teacher_id=t.id
        LEFT JOIN classroom cr ON ex.classroom_id=cr.id
        ORDER BY ex.exam_date DESC""")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/exams/<int:eid>', methods=['DELETE'])
@role_required('admin')
def adm_exam_detail(eid):
    execute("DELETE FROM exam WHERE id=%s", (eid,))
    log_operation('DELETE', 'exam', eid, '删除考试安排')
    return jsonify({'success': True, 'message': '已删除'})


# ---- 选课管理 ----
@admin_bp.route('/api/admin/enrollments')
@role_required('admin')
def adm_enrollments():
    offering_id = request.args.get('offering_id', type=int)
    sql = """SELECT e.*, s.username, s.real_name AS student_name, c.name AS course_name, co.semester
             FROM enrollment e
             JOIN student s ON e.student_id=s.id
             JOIN course_offering co ON e.offering_id=co.id
             JOIN course c ON co.course_id=c.id WHERE 1=1"""
    params = []
    if offering_id:
        sql += " AND e.offering_id=%s"
        params.append(offering_id)
    sql += " ORDER BY e.select_time DESC LIMIT 500"
    rows = query_all(sql, params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


# ---- 成绩管理 ----
@admin_bp.route('/api/admin/grades', methods=['GET', 'PUT'])
@role_required('admin')
def adm_grades():
    if request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        eid = data.get('id')
        if not eid:
            return jsonify({'success': False, 'message': '缺少成绩记录 id'})
        cur_row = query_one("""SELECT e.id, e.usual_score, e.exam_score, co.usual_ratio, co.exam_ratio
                               FROM enrollment e JOIN course_offering co ON e.offering_id=co.id
                               WHERE e.id=%s""", (eid,))
        if not cur_row:
            return jsonify({'success': False, 'message': '成绩记录不存在'})
        try:
            # 未提交的字段保持原值，避免只改一项时把另一项清空
            usual = parse_score(data['usual_score']) if 'usual_score' in data else (
                float(cur_row['usual_score']) if cur_row['usual_score'] is not None else None)
            exam = parse_score(data['exam_score']) if 'exam_score' in data else (
                float(cur_row['exam_score']) if cur_row['exam_score'] is not None else None)
        except ValueError as e:
            return jsonify({'success': False, 'message': f'保存失败: {e}'})
        # 注意 0 是合法比例，不能用 or 兜底
        usual_ratio = 40 if cur_row['usual_ratio'] is None else int(cur_row['usual_ratio'])
        exam_ratio = 60 if cur_row['exam_ratio'] is None else int(cur_row['exam_ratio'])
        total = point = None
        if usual is not None and exam is not None:
            total, point = calc_grade(usual, exam, usual_ratio, exam_ratio)
        execute("""UPDATE enrollment SET usual_score=%s, exam_score=%s, total_score=%s, grade_point=%s WHERE id=%s""",
                (usual, exam, total, point, eid))
        log_operation('UPDATE', 'enrollment', eid, f'管理员修改成绩: 平时={usual} 考试={exam} 总评={total}')
        return jsonify({'success': True, 'message': '成绩已更新'})

    keyword = request.args.get('keyword', '').strip()
    sql = """SELECT e.id, s.username, s.real_name AS student_name, c.name AS course_name, co.semester,
                    e.usual_score, e.exam_score, e.total_score, e.grade_point,
                    co.usual_ratio, co.exam_ratio
             FROM enrollment e JOIN student s ON e.student_id=s.id
             JOIN course_offering co ON e.offering_id=co.id JOIN course c ON co.course_id=c.id
             WHERE e.status='已选'"""
    params = []
    if keyword:
        sql += " AND (s.username LIKE %s OR s.real_name LIKE %s OR c.name LIKE %s)"
        params += [f'%{keyword}%'] * 3
    sql += " ORDER BY co.semester DESC, s.username LIMIT 500"
    rows = query_all(sql, params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


# ---- 申请审核 ----
@admin_bp.route('/api/admin/reviews/<apply_type>')
@role_required('admin')
def adm_reviews(apply_type):
    if apply_type not in REVIEW_TABLES:
        return jsonify({'success': False, 'message': '无效的申请类型'})
    _, sql, alias = REVIEW_TABLES[apply_type]
    status = request.args.get('status')
    params = None
    if status:
        if status not in ('待审核', '已通过', '已拒绝'):
            return jsonify({'success': False, 'message': '无效的状态筛选'})
        # 必须用表别名限定，否则 JOIN 到 student 等表时 status 列名歧义
        sql += f" WHERE {alias}.status = %s"
        params = (status,)
    sql += f" ORDER BY {alias}.created_at DESC LIMIT 500"
    rows = query_all(sql, params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/reviews/<apply_type>/<int:aid>', methods=['POST'])
@role_required('admin')
def adm_review_action(apply_type, aid):
    if apply_type not in REVIEW_TABLES:
        return jsonify({'success': False, 'message': '无效的申请类型'})
    data = request.get_json() or {}
    action = data.get('action')
    if action not in ('approve', 'reject', 'revoke'):
        return jsonify({'success': False, 'message': '无效操作'})
    table = REVIEW_TABLES[apply_type][0]
    remark = data.get('remark', '')
    force = bool(data.get('force'))

    row = query_one(f"SELECT * FROM {table} WHERE id=%s", (aid,))
    if not row:
        return jsonify({'success': False, 'message': '申请记录不存在'})

    # 撤销：把已通过/已拒绝的申请退回待审核，并回滚已产生的业务副作用
    if action == 'revoke':
        if row['status'] == '待审核':
            return jsonify({'success': False, 'message': '该申请本就处于待审核状态'})
        effects = []
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                if row['status'] == '已通过':
                    effects = _revert_review_effect(cur, apply_type, row)
                # 状态守卫：仅当状态未被并发修改时才回退
                cur.execute(f"""UPDATE {table} SET status='待审核', review_remark=NULL, reviewed_at=NULL
                                WHERE id=%s AND status=%s""", (aid, row['status']))
                if cur.rowcount != 1:
                    conn.rollback()
                    return jsonify({'success': False, 'message': '该申请状态已被其他操作修改，请刷新后重试'})
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f'撤销审核失败: {e}')
            return jsonify({'success': False, 'message': '撤销失败，请稍后重试'})
        finally:
            conn.close()

        detail = f"撤销审核{apply_type}: {row['status']} → 待审核"
        if effects:
            detail += '；' + '；'.join(effects)
        log_operation('REVOKE', table, aid, detail)
        msg = '已撤销，退回待审核'
        if effects:
            msg += '（' + '；'.join(effects) + '）'
        return jsonify({'success': True, 'message': msg, 'effects': effects})

    new_status = '已通过' if action == 'approve' else '已拒绝'
    if row['status'] == new_status:
        return jsonify({'success': False, 'message': f'该申请已是「{new_status}」状态'})

    effects, warnings = [], []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if action == 'approve':
                effects, warnings = _apply_review_effect(cur, apply_type, row, force)
                if warnings and not force:
                    # 前置条件不满足且未强制：不落库，把原因返回给前端
                    conn.rollback()
                    return jsonify({'success': False, 'message': '；'.join(warnings), 'need_confirm': True})
            else:
                # 从「已通过」改判为「已拒绝」时回滚副作用
                if row['status'] == '已通过':
                    effects = _revert_review_effect(cur, apply_type, row)

            cur.execute(f"""UPDATE {table} SET status=%s, review_remark=%s, reviewed_at=NOW()
                            WHERE id=%s AND status=%s""",
                        (new_status, remark, aid, row['status']))
            if cur.rowcount != 1:
                # 并发审核：另一请求已改过状态，本请求的副作用需要一并回滚
                conn.rollback()
                return jsonify({'success': False, 'message': '该申请状态已被其他操作修改，请刷新后重试'})
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'审核失败: {e}')
        return jsonify({'success': False, 'message': '审核失败，请稍后重试'})
    finally:
        conn.close()

    detail = f"审核{apply_type}: {new_status}"
    if effects:
        detail += '；' + '；'.join(effects)
    log_operation('REVIEW', table, aid, detail)

    msg = new_status
    if effects:
        msg += '（' + '；'.join(effects) + '）'
    if warnings:
        msg += '（提示：' + '；'.join(warnings) + '）'
    return jsonify({'success': True, 'message': msg, 'effects': effects, 'warnings': warnings})


# 学籍异动类型 → 学生状态
_STATUS_MAP = {'休学': '休学', '复学': '在读', '退学': '退学'}


def _apply_review_effect(cur, apply_type, row, force=False):
    """审核通过时执行业务副作用，返回 (effects, warnings)"""
    effects, warnings = [], []

    if apply_type == 'status_change':
        ct = row.get('change_type')
        if ct in _STATUS_MAP:
            new_status = _STATUS_MAP[ct]
            # 休学/退学同时冻结账号：登录只校验 is_frozen，只改 status 的话学生仍可继续选课、
            # 查成绩（会话有效期 7 天），学籍状态形同虚设。
            frozen = 1 if ct in ('休学', '退学') else 0
            cur.execute("UPDATE student SET status=%s, is_frozen=%s WHERE id=%s",
                        (new_status, frozen, row['student_id']))
            effects.append(f"学籍状态已改为「{new_status}」" + ("，账号已冻结" if frozen else "，账号已解除冻结"))
        else:
            # 转专业需要目标专业/班级信息，申请表未记录，需管理员后续在组织架构里调整
            warnings.append(f"「{ct}」需人工调整班级与专业归属")

    elif apply_type == 'retake':
        off = query_one("""SELECT co.id, co.max_count, co.selected_count, c.name
                           FROM course_offering co JOIN course c ON co.course_id=c.id
                           WHERE co.course_id=%s AND co.semester=%s AND co.status='开放'
                           ORDER BY co.id LIMIT 1""", (row['course_id'], CURRENT_SEMESTER))
        if not off:
            warnings.append('本学期该课程无开放教学班，需先在开课管理中开课')
        else:
            exist = query_one("SELECT id, status FROM enrollment WHERE student_id=%s AND offering_id=%s",
                              (row['student_id'], off['id']))
            if exist and exist['status'] == '已选':
                effects.append(f"已存在「{off['name']}」选课记录，无需重复")
            elif off['selected_count'] >= off['max_count']:
                warnings.append(f"「{off['name']}」名额已满（{off['selected_count']}/{off['max_count']}）")
            else:
                # 先原子占名额（条件 UPDATE）再写选课记录，避免并发审核时超员
                cur.execute("""UPDATE course_offering SET selected_count=selected_count+1
                               WHERE id=%s AND selected_count < max_count""", (off['id'],))
                if cur.rowcount != 1:
                    raise RuntimeError('教学班名额已满，请刷新后重试')
                if exist:
                    cur.execute("UPDATE enrollment SET status='已选', is_retake=1, select_time=NOW() WHERE id=%s",
                                (exist['id'],))
                else:
                    cur.execute("""INSERT INTO enrollment (student_id, offering_id, status, is_retake)
                                   VALUES (%s,%s,'已选',1)""", (row['student_id'], off['id']))
                effects.append(f"已自动选上「{off['name']}」（重修）")

    elif apply_type == 'credit_substitute':
        sub_id = row.get('substitute_course_id')
        if not sub_id:
            warnings.append('申请未指定替代课程，无法写入成绩')
        else:
            off = query_one("""SELECT co.id, c.name FROM course_offering co JOIN course c ON co.course_id=c.id
                               WHERE co.course_id=%s ORDER BY co.semester DESC LIMIT 1""", (sub_id,))
            if not off:
                warnings.append('替代课程尚无开课记录，无法写入成绩')
            else:
                exist = query_one("SELECT id, status, total_score FROM enrollment WHERE student_id=%s AND offering_id=%s",
                                  (row['student_id'], off['id']))
                if exist and exist['status'] == '已选' and (exist['total_score'] or 0) >= 60:
                    # 已有及格成绩时不得用认定分覆盖真实成绩（否则 90 分会被改成 60 分）
                    effects.append(f"「{off['name']}」已有及格成绩 {exist['total_score']} 分，保留原成绩未覆盖")
                elif exist:
                    cur.execute("""UPDATE enrollment SET status='已选', total_score=60, grade_point=1
                                   WHERE id=%s""", (exist['id'],))
                    effects.append(f"已认定「{off['name']}」成绩 60 分（学分替代）")
                else:
                    cur.execute("""INSERT INTO enrollment (student_id, offering_id, status, total_score, grade_point)
                                   VALUES (%s,%s,'已选',60,1)""", (row['student_id'], off['id']))
                    effects.append(f"已认定「{off['name']}」成绩 60 分（学分替代）")

    # project：仅报名审核，无业务副作用
    return effects, warnings


def _revert_review_effect(cur, apply_type, row):
    """把「已通过」改判为「已拒绝」时，撤销此前产生的副作用"""
    effects = []

    if apply_type == 'status_change':
        ct = row.get('change_type')
        if ct == '休学':
            cur.execute("UPDATE student SET status='在读', is_frozen=0 WHERE id=%s", (row['student_id'],))
            effects.append('学籍状态已还原为「在读」，账号已解除冻结')
        elif ct == '退学':
            cur.execute("UPDATE student SET status='在读', is_frozen=0 WHERE id=%s", (row['student_id'],))
            effects.append('学籍状态已还原为「在读」并解除冻结（请核实原状态）')
        elif ct == '复学':
            cur.execute("UPDATE student SET status='休学', is_frozen=1 WHERE id=%s", (row['student_id'],))
            effects.append('学籍状态已还原为「休学」，账号已重新冻结')

    elif apply_type == 'retake':
        off = query_one("""SELECT co.id, c.name FROM course_offering co JOIN course c ON co.course_id=c.id
                           WHERE co.course_id=%s AND co.semester=%s ORDER BY co.id LIMIT 1""",
                        (row['course_id'], CURRENT_SEMESTER))
        if off:
            rec = query_one("""SELECT id FROM enrollment
                               WHERE student_id=%s AND offering_id=%s AND status='已选' AND is_retake=1""",
                            (row['student_id'], off['id']))
            if rec:
                cur.execute("UPDATE enrollment SET status='退选', is_retake=0 WHERE id=%s", (rec['id'],))
                cur.execute("""UPDATE course_offering SET selected_count=GREATEST(selected_count-1,0)
                               WHERE id=%s""", (off['id'],))
                effects.append(f'已撤销「{off["name"]}」的重修选课')

    elif apply_type == 'credit_substitute':
        sub_id = row.get('substitute_course_id')
        if sub_id:
            off = query_one("""SELECT co.id, c.name FROM course_offering co JOIN course c ON co.course_id=c.id
                               WHERE co.course_id=%s ORDER BY co.semester DESC LIMIT 1""", (sub_id,))
            if off:
                # 仅撤销"认定分 60 + 绩点 1.0"这一特征记录，且必须是已选状态
                rec = query_one("""SELECT id FROM enrollment WHERE student_id=%s AND offering_id=%s
                                   AND status='已选' AND total_score=60 AND grade_point=1""",
                                (row['student_id'], off['id']))
                if rec:
                    cur.execute("""UPDATE enrollment SET status='退选', total_score=NULL, grade_point=NULL
                                   WHERE id=%s""", (rec['id'],))
                    effects.append(f'已撤销「{off["name"]}」的学分认定')

    return effects


# ---- 公告管理 ----
@admin_bp.route('/api/admin/announcements', methods=['GET', 'POST'])
@role_required('admin')
def adm_announcements():
    if request.method == 'POST':
        data = request.get_json() or {}
        rid = execute("INSERT INTO announcement (title, content, is_top) VALUES (%s,%s,%s)",
                      (data['title'], data['content'], data.get('is_top', 0)))
        log_operation('INSERT', 'announcement', rid, f"发布公告: {data['title']}")
        return jsonify({'success': True, 'message': '公告已发布', 'id': rid})
    rows = query_all("SELECT * FROM announcement ORDER BY is_top DESC, created_at DESC")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/announcements/<int:aid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_announcement_detail(aid):
    if request.method == 'DELETE':
        execute("DELETE FROM announcement WHERE id=%s", (aid,))
        log_operation('DELETE', 'announcement', aid, '删除公告')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    if not data.get('title') or not data.get('content'):
        return jsonify({'success': False, 'message': '公告标题与内容不能为空'})
    execute("UPDATE announcement SET title=%s, content=%s, is_top=%s, is_active=%s WHERE id=%s",
            (data['title'], data['content'], data.get('is_top', 0), data.get('is_active', 1), aid))
    log_operation('UPDATE', 'announcement', aid, f"修改公告: {data['title']}")
    return jsonify({'success': True, 'message': '已更新'})


# ---- 日志（仅超级管理员可查看/操作审计日志） ----
@admin_bp.route('/api/admin/logs', methods=['GET', 'DELETE'])
@role_required('admin')
@perm_required('super')
def adm_logs():
    if request.method == 'DELETE':
        execute("DELETE FROM operation_log")
        return jsonify({'success': True, 'message': '日志已清空'})
    rows = query_all("""SELECT l.*, a.real_name AS admin_name FROM operation_log l
                        LEFT JOIN admin a ON l.admin_id=a.id ORDER BY l.created_at DESC LIMIT 300""")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/logs/<int:lid>', methods=['DELETE'])
@role_required('admin')
@perm_required('super')
def adm_log_detail(lid):
    execute("DELETE FROM operation_log WHERE id=%s", (lid,))
    return jsonify({'success': True, 'message': '已删除'})


# ---- 教学项目管理 ----
@admin_bp.route('/api/admin/projects', methods=['GET', 'POST'])
@role_required('admin')
def adm_projects():
    if request.method == 'POST':
        data = request.get_json() or {}
        if not data.get('name'):
            return jsonify({'success': False, 'message': '项目名称不能为空'})
        try:
            max_count = parse_int(data.get('max_count', 30), default=30, min_value=1, max_value=10000, label='名额')
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})
        if not data.get('semester'):
            return jsonify({'success': False, 'message': '学期不能为空'})
        rid = execute("""INSERT INTO project (name, type, semester, max_count, start_date, end_date, description, is_open)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (data['name'], data.get('type', '学科竞赛'), data['semester'], max_count,
                       data.get('start_date') or None, data.get('end_date') or None,
                       data.get('description'), data.get('is_open', 1)))
        log_operation('INSERT', 'project', rid, f"新增教学项目: {data['name']}")
        return jsonify({'success': True, 'message': '项目已添加', 'id': rid})

    keyword = request.args.get('keyword', '').strip()
    where = " WHERE 1=1"
    params = []
    if keyword:
        where += " AND (p.name LIKE %s OR p.type LIKE %s)"
        params += [f'%{keyword}%', f'%{keyword}%']
    rows = query_all("""SELECT p.*, (SELECT COUNT(*) FROM project_apply pa WHERE pa.project_id=p.id) AS total_apply
                        FROM project p""" + where + " ORDER BY p.created_at DESC", params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/projects/<int:pid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_project_detail(pid):
    if request.method == 'DELETE':
        execute("DELETE FROM project WHERE id=%s", (pid,))
        log_operation('DELETE', 'project', pid, '删除教学项目')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'success': False, 'message': '项目名称不能为空'})
    try:
        max_count = parse_int(data.get('max_count', 30), default=30, min_value=1, max_value=10000, label='名额')
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    execute("""UPDATE project SET name=%s, type=%s, semester=%s, max_count=%s,
               start_date=%s, end_date=%s, description=%s, is_open=%s WHERE id=%s""",
            (data['name'], data.get('type', '学科竞赛'), data.get('semester'), max_count,
             data.get('start_date') or None, data.get('end_date') or None,
             data.get('description'), data.get('is_open', 1), pid))
    log_operation('UPDATE', 'project', pid, f"修改教学项目: {data['name']}")
    return jsonify({'success': True, 'message': '已更新'})


# ---- 创新创业学分 ----
@admin_bp.route('/api/admin/innovation-credits', methods=['GET', 'POST'])
@role_required('admin')
def adm_innovation_credits():
    if request.method == 'POST':
        data = request.get_json() or {}
        if not data.get('student_id') or not data.get('item_name'):
            return jsonify({'success': False, 'message': '请选择学生并填写项目名称'})
        try:
            credit = float(data.get('credit') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '学分必须是数字'})
        if not (0 <= credit <= 100):
            return jsonify({'success': False, 'message': '学分应在 0-100 之间'})
        rid = execute("""INSERT INTO innovation_credit (student_id, item_name, credit, category, obtained_date, is_confirmed)
                         VALUES (%s,%s,%s,%s,%s,%s)""",
                      (data['student_id'], data['item_name'], credit,
                       data.get('category', '竞赛获奖'), data.get('obtained_date') or None,
                       data.get('is_confirmed', 0)))
        log_operation('INSERT', 'innovation_credit', rid, f"录入创新学分: {data['item_name']}")
        return jsonify({'success': True, 'message': '创新学分已录入', 'id': rid})

    keyword = request.args.get('keyword', '').strip()
    where = " WHERE 1=1"
    params = []
    if keyword:
        where += " AND (s.username LIKE %s OR s.real_name LIKE %s OR ic.item_name LIKE %s)"
        params += [f'%{keyword}%'] * 3
    rows = query_all("""SELECT ic.*, s.username, s.real_name, cl.name AS class_name
                        FROM innovation_credit ic
                        JOIN student s ON ic.student_id=s.id
                        LEFT JOIN class cl ON s.class_id=cl.id""" + where +
                     " ORDER BY ic.created_at DESC LIMIT 500", params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/innovation-credits/<int:iid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_innovation_credit_detail(iid):
    if request.method == 'DELETE':
        execute("DELETE FROM innovation_credit WHERE id=%s", (iid,))
        log_operation('DELETE', 'innovation_credit', iid, '删除创新学分')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    try:
        credit = float(data.get('credit') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '学分必须是数字'})
    if not (0 <= credit <= 100):
        return jsonify({'success': False, 'message': '学分应在 0-100 之间'})
    execute("""UPDATE innovation_credit SET item_name=%s, credit=%s, category=%s,
               obtained_date=%s, is_confirmed=%s WHERE id=%s""",
            (data.get('item_name'), credit, data.get('category', '竞赛获奖'),
             data.get('obtained_date') or None, data.get('is_confirmed', 0), iid))
    log_operation('UPDATE', 'innovation_credit', iid, '修改创新学分')
    return jsonify({'success': True, 'message': '已更新'})


# ---- 教学执行计划 ----
@admin_bp.route('/api/admin/teaching-plans', methods=['GET', 'POST'])
@role_required('admin')
def adm_teaching_plans():
    if request.method == 'POST':
        data = request.get_json() or {}
        if not data.get('major_id') or not data.get('course_id'):
            return jsonify({'success': False, 'message': '请选择专业和课程'})
        try:
            sem_no = parse_int(data.get('semester_no', 1), default=1, min_value=1, max_value=12, label='开课学期')
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})
        dup = query_one("""SELECT id, semester_no FROM teaching_plan
                           WHERE major_id=%s AND course_id=%s""",
                        (data['major_id'], data['course_id']))
        if dup:
            return jsonify({'success': False,
                            'message': f"该专业已有此课程（第 {dup['semester_no']} 学期），无需重复添加"})
        try:
            rid = execute("""INSERT INTO teaching_plan (major_id, course_id, semester_no, category)
                             VALUES (%s,%s,%s,%s)""",
                          (data['major_id'], data['course_id'], sem_no, data.get('category', '必修')))
        except pymysql.err.IntegrityError:
            return jsonify({'success': False, 'message': '该专业已有此课程，无需重复添加'})
        log_operation('INSERT', 'teaching_plan', rid, f"新增教学计划: major={data['major_id']}")
        return jsonify({'success': True, 'message': '已添加到教学计划', 'id': rid})

    major_id = request.args.get('major_id', type=int)
    where = " WHERE 1=1"
    params = []
    if major_id:
        where += " AND tp.major_id=%s"
        params.append(major_id)
    rows = query_all("""SELECT tp.*, m.name AS major_name, c.code, c.name AS course_name,
                               c.credit, c.hours, c.type
                        FROM teaching_plan tp
                        JOIN major m ON tp.major_id=m.id
                        JOIN course c ON tp.course_id=c.id""" + where +
                     " ORDER BY m.name, tp.semester_no, c.code", params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/teaching-plans/<int:tid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_teaching_plan_detail(tid):
    if request.method == 'DELETE':
        execute("DELETE FROM teaching_plan WHERE id=%s", (tid,))
        log_operation('DELETE', 'teaching_plan', tid, '删除教学计划')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    try:
        sem_no = parse_int(data.get('semester_no', 1), default=1, min_value=1, max_value=12, label='开课学期')
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    execute("UPDATE teaching_plan SET semester_no=%s, category=%s WHERE id=%s",
            (sem_no, data.get('category', '必修'), tid))
    log_operation('UPDATE', 'teaching_plan', tid, '修改教学计划')
    return jsonify({'success': True, 'message': '已更新'})


# ---- 证书发放 ----
@admin_bp.route('/api/admin/certificates', methods=['GET', 'POST'])
@role_required('admin')
def adm_certificates():
    if request.method == 'POST':
        data = request.get_json() or {}
        if not data.get('student_id') or not data.get('name'):
            return jsonify({'success': False, 'message': '请选择学生并填写证书名称'})
        rid = execute("""INSERT INTO certificate (student_id, name, cert_no, issue_date, issuer)
                         VALUES (%s,%s,%s,%s,%s)""",
                      (data['student_id'], data['name'], data.get('cert_no'),
                       data.get('issue_date') or None, data.get('issuer')))
        log_operation('INSERT', 'certificate', rid, f"发放证书: {data['name']}")
        return jsonify({'success': True, 'message': '证书已发放', 'id': rid})

    keyword = request.args.get('keyword', '').strip()
    where = " WHERE 1=1"
    params = []
    if keyword:
        where += " AND (s.username LIKE %s OR s.real_name LIKE %s OR c.name LIKE %s)"
        params += [f'%{keyword}%'] * 3
    rows = query_all("""SELECT c.*, s.username, s.real_name, cl.name AS class_name
                        FROM certificate c
                        JOIN student s ON c.student_id=s.id
                        LEFT JOIN class cl ON s.class_id=cl.id""" + where +
                     " ORDER BY c.issue_date DESC, c.id DESC LIMIT 500", params)
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@admin_bp.route('/api/admin/certificates/<int:cid>', methods=['PUT', 'DELETE'])
@role_required('admin')
def adm_certificate_detail(cid):
    if request.method == 'DELETE':
        execute("DELETE FROM certificate WHERE id=%s", (cid,))
        log_operation('DELETE', 'certificate', cid, '删除证书')
        return jsonify({'success': True, 'message': '已删除'})
    data = request.get_json() or {}
    execute("""UPDATE certificate SET name=%s, cert_no=%s, issue_date=%s, issuer=%s WHERE id=%s""",
            (data.get('name'), data.get('cert_no'), data.get('issue_date') or None,
             data.get('issuer'), cid))
    log_operation('UPDATE', 'certificate', cid, '修改证书')
    return jsonify({'success': True, 'message': '已更新'})


# ---- 数据修复工具 ----
@admin_bp.route('/api/admin/repair/selected-count', methods=['POST'])
@role_required('admin')
def adm_repair_selected_count():
    """重算所有教学班的 selected_count（修复与实际选课数不一致）"""
    before = query_all("""
        SELECT co.id, co.selected_count,
               (SELECT COUNT(*) FROM enrollment e WHERE e.offering_id=co.id AND e.status='已选') AS real_count
        FROM course_offering co""")
    fixed = [b for b in before if b['selected_count'] != b['real_count']]
    execute("""UPDATE course_offering co
               SET selected_count = (SELECT COUNT(*) FROM enrollment e
                                     WHERE e.offering_id=co.id AND e.status='已选')""")
    log_operation('REPAIR', 'course_offering', None,
                  f'重算选课人数，修正 {len(fixed)} 个教学班')
    detail = [f"{b['id']}: {b['selected_count']}→{b['real_count']}" for b in fixed[:10]]
    return jsonify({'success': True,
                    'message': f'已重算 {len(before)} 个教学班，修正 {len(fixed)} 个',
                    'fixed_count': len(fixed), 'details': detail})


@admin_bp.route('/api/admin/repair/sync-enrollment', methods=['POST'])
@role_required('admin')
def adm_repair_sync_enrollment():
    """按班级补齐全校统排课（非选修）选课记录。

    用于修复历史数据：新建学生/批量导入/新建开课后，教师端名单与成绩导入
    依赖 enrollment 记录；此接口可手动触发一次全量继承同步（幂等）。
    """
    try:
        from enrollment_sync import sync_all_students, recompute_selected_count
        stats = sync_all_students() or {}
        fixed = recompute_selected_count()
    except Exception as e:
        print(f'批量同步班级选课失败: {e}')
        return jsonify({'success': False, 'message': '同步失败，请稍后重试'})
    changed = int(stats.get('added', 0)) + int(stats.get('restored', 0))
    log_operation('REPAIR', 'enrollment', None,
                  f"同步班级课程：涉及 {stats.get('students', 0)} 名学生，新增/恢复 {changed} 条选课")
    return jsonify({'success': True,
                    'message': f"同步完成：{stats.get('students', 0)} 名学生，"
                               f"新增/恢复 {changed} 条选课，重算 {fixed} 个教学班人数",
                    'stats': stats})


# ---- 批量导入 ----
@admin_bp.route('/api/admin/import/<entity_type>/template')
@role_required('admin')
def adm_import_template(entity_type):
    """下载导入模板（xlsx）"""
    if entity_type not in IMPORT_SCHEMAS:
        return jsonify({'success': False, 'message': '无效的实体类型'})
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = IMPORT_LABELS[entity_type]
    headers = [title for _, title, _ in IMPORT_SCHEMAS[entity_type]]
    ws.append(headers)
    examples = {
        'student': ['2024999', '张三', '男', '网络2401', '13800000000', 'zhangsan@stu.gyiist.edu.cn', '2024-09-01', '在读', '123456'],
        'teacher': ['T099', '李四', '女', '信息工程学院', '讲师', '13900000000', 'lisi@gyiist.edu.cn', '123456'],
        'course': ['CS999', '示例课程', '2.0', '32', '选修', '信息工程学院', '课程简介示例'],
        'class': ['网络2499', '网络工程', '2024'],
    }
    ws.append(examples[entity_type])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f'{IMPORT_LABELS[entity_type]}导入模板.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@admin_bp.route('/api/admin/import/<entity_type>', methods=['POST'])
@role_required('admin')
def adm_import(entity_type):
    if entity_type not in IMPORT_SCHEMAS:
        return jsonify({'success': False, 'message': '无效的实体类型'})

    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'message': '请上传文件'})

    try:
        header, body = _read_uploaded_table(file)
    except Exception as e:
        print(f'导入文件解析失败: {e}')
        return jsonify({'success': False, 'message': '文件解析失败，请使用系统提供的模板（xlsx/csv）'})

    schema = IMPORT_SCHEMAS[entity_type]
    if len(body) > MAX_IMPORT_ROWS:
        return jsonify({'success': False,
                        'message': f'单次最多导入 {MAX_IMPORT_ROWS} 行，当前 {len(body)} 行，请拆分后分批导入'})
    title2field = {title: field for field, title, _ in schema}
    header_map = {}
    for i, h in enumerate(header):
        if h in title2field:
            header_map[title2field[h]] = i

    required = [field for field, _, req in schema if req]
    missing = [f for f in required if f not in header_map]
    if missing:
        titles = [t for f, t, _ in schema if f in missing]
        return jsonify({'success': False, 'message': f'缺少必填列：{"、".join(titles)}'})

    class_cache = {}
    college_cache = {}
    major_cache = {}

    def get_class_id(name):
        if not name:
            return None
        name = str(name).strip()
        if name not in class_cache:
            r = query_one("SELECT id FROM class WHERE name=%s", (name,))
            class_cache[name] = r['id'] if r else None
        return class_cache[name]

    def get_college_id(name):
        if not name:
            return None
        name = str(name).strip()
        if name not in college_cache:
            r = query_one("SELECT id FROM college WHERE name=%s", (name,))
            college_cache[name] = r['id'] if r else None
        return college_cache[name]

    def get_major_id(name):
        if not name:
            return None
        name = str(name).strip()
        if name not in major_cache:
            r = query_one("SELECT id FROM major WHERE name=%s", (name,))
            major_cache[name] = r['id'] if r else None
        return major_cache[name]

    def cell(row, field, default=''):
        i = header_map.get(field)
        if i is None or i >= len(row):
            return default
        v = row[i]
        if v is None:
            return default
        v = str(v).strip()
        return v

    conn = get_db_connection()
    cursor = conn.cursor()
    ok_count = 0
    errors = []

    try:
        for lineno, row in enumerate(body, start=2):
            try:
                if entity_type == 'student':
                    username = cell(row, 'username')
                    real_name = cell(row, 'real_name')
                    if not username or not real_name:
                        raise ValueError('学号/姓名不能为空')
                    username = validate_name(username, '学号', 32)
                    real_name = validate_name(real_name, '姓名', 64)
                    pw = cell(row, 'password') or Config.DEFAULT_INITIAL_PASSWORD
                    pw_hash = _hash_password_cached(pw)
                    class_id = get_class_id(cell(row, 'class_name'))
                    gender = cell(row, 'gender') or '男'
                    status = cell(row, 'status') or '在读'
                    edate = cell(row, 'enrollment_date') or None
                    cursor.execute(
                        """INSERT INTO student (username, password_hash, real_name, gender, class_id, phone, email, enrollment_date, status, must_change_pwd)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0)""",
                        (username, pw_hash, real_name, gender, class_id,
                         cell(row, 'phone') or None, cell(row, 'email') or None, edate, status))
                    # 同事务内继承本班统排课：失败只记日志，不影响该行学生导入
                    try:
                        from enrollment_sync import sync_student_enrollments
                        sync_student_enrollments(cursor.lastrowid, class_id, cursor=cursor)
                    except Exception as e:
                        print(f'导入第{lineno}行同步班级课程失败: {e}')

                elif entity_type == 'teacher':
                    username = cell(row, 'username')
                    real_name = cell(row, 'real_name')
                    if not username or not real_name:
                        raise ValueError('工号/姓名不能为空')
                    username = validate_name(username, '工号', 32)
                    real_name = validate_name(real_name, '姓名', 64)
                    pw = cell(row, 'password') or Config.DEFAULT_INITIAL_PASSWORD
                    pw_hash = _hash_password_cached(pw)
                    college_id = get_college_id(cell(row, 'college_name'))
                    cursor.execute(
                        """INSERT INTO teacher (username, password_hash, real_name, gender, college_id, title, phone, email, must_change_pwd)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)""",
                        (username, pw_hash, real_name, cell(row, 'gender') or '男', college_id,
                         cell(row, 'title') or None, cell(row, 'phone') or None, cell(row, 'email') or None))

                elif entity_type == 'course':
                    code = cell(row, 'code')
                    name = cell(row, 'name')
                    if not code or not name:
                        raise ValueError('课程号/课程名称不能为空')
                    credit = cell(row, 'credit') or '0'
                    hours = cell(row, 'hours') or '0'
                    try:
                        credit = float(credit)
                        hours = int(float(hours))
                    except ValueError:
                        raise ValueError('学分/学时必须是数字')
                    college_id = get_college_id(cell(row, 'college_name'))
                    cursor.execute(
                        """INSERT INTO course (code, name, credit, hours, type, college_id, description)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (code, name, credit, hours, cell(row, 'type') or '必修', college_id,
                         cell(row, 'description') or None))

                elif entity_type == 'class':
                    name = cell(row, 'name')
                    major_name = cell(row, 'major_name')
                    if not name or not major_name:
                        raise ValueError('班级名称/专业名称不能为空')
                    major_id = get_major_id(major_name)
                    if not major_id:
                        raise ValueError(f'专业「{major_name}」不存在')
                    year = cell(row, 'grade_year') or '2024'
                    try:
                        year = int(float(year))
                    except ValueError:
                        raise ValueError('入学年份必须是数字')
                    cursor.execute("INSERT INTO class (major_id, name, grade_year) VALUES (%s,%s,%s)",
                                   (major_id, name, year))

                ok_count += 1
            except pymysql.err.IntegrityError:
                errors.append(f'第{lineno}行：编号/名称重复')
            except ValueError as e:
                errors.append(f'第{lineno}行：{e}')
            except Exception as e:
                # 数据库内部错误（长度/类型/外键）只写日志，不把细节回显给前端
                print(f'导入第{lineno}行失败: {e}')
                errors.append(f'第{lineno}行：数据格式或长度不符合要求')

        conn.commit()
        log_operation('IMPORT', entity_type, None, f"批量导入{IMPORT_LABELS[entity_type]}: 成功{ok_count}条，失败{len(errors)}条")
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'导入失败: {e}'})
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        'success': True,
        'message': f'导入完成：成功 {ok_count} 条，失败 {len(errors)} 条',
        'success_count': ok_count,
        'fail_count': len(errors),
        'errors': errors[:20]
    })
