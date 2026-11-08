# -*- coding: utf-8 -*-
"""班级课程继承（enrollment 同步）核心模块。

背景与用途
----------
教务系统中课程按 ``course.type`` 分为两类，选课来源不同：

* **选修课**：由学生自主选课（student.py ``/api/student/course-select/enroll``），
  enrollment 记录来自学生主动操作，本模块不介入；
* **必修 / 通识 / 实践**：由学校统一排课——``course_offering`` 通过
  ``offering_class`` 指定授课班级，学生无需（也不允许）自主选课，课表由班级继承。

但教师端的成绩录入、成绩导入、选课名单、成绩模板等接口都只从 ``enrollment``
取学生。如果统排课不落成 enrollment，就会出现「学生课表里有这门课、教师名单里
却没有这名学生、导不进成绩」的不一致。本模块负责把「本班指定 + 本学期 + 非选修」
的课程幂等地补齐为 ``enrollment(status='已选')`` 记录，并在转班 / 开课改班级时
清理过期记录，同时提供 ``course_offering.selected_count`` 重算能力。

边界（重要）
------------
* 只处理 ``CURRENT_SEMESTER``（当前学期）的课程；历史学期的选课记录一律不动。
* 只处理 ``student.status='在读'`` 且 ``student.is_frozen=0`` 且有班级的学生。
* 只处理 ``course.type <> '选修'``（必修/通识/实践）；选修课的 enrollment 永远由
  学生自主选择，本模块不插入、不恢复、不删除。``course.type`` 为 NULL 的历史
  脏数据按非统排处理（跳过），与 SQL ``type <> '选修'`` 语义一致。
* 统排课**不校验** ``course_offering.max_count`` 容量：班级人数可能多于开课容量，
  因此 ``selected_count`` 按 enrollment 实际人数重算，允许大于 ``max_count``。
* **不修改任何已有成绩**（usual_score / exam_score / total_score / grade_point /
  is_retake）：只插入缺失记录、恢复「退选且无任何成绩」的记录、删除无成绩的
  过期统排记录。有成绩的记录永远保留（转班/移除班级时也不删，便于成绩追溯）。

幂等性
------
* ``enrollment`` 有 UNIQUE(student_id, offering_id)，配合 ``INSERT IGNORE``，
  重复执行不会重复插入；
* 已存在 ``status='已选'`` 的记录自然跳过（INSERT IGNORE）；
* 已存在 ``status='退选'`` 且 usual/exam/total 全 NULL、is_retake=0 的记录恢复为
  ``'已选'`` 并刷新 select_time；
* 所有函数可安全重复调用，并发场景由 UNIQUE KEY 兜底。

事务
----
* 传入 ``cursor`` 时使用调用方事务：不 commit、不 close，由调用方统一提交/回滚；
  调用方 cursor 需与项目其他代码一致，为 pymysql 的 DictCursor。
* 未传 ``cursor`` 时自建连接：成功 commit、异常 rollback、最后归还连接（连接池）。
* 写操作会在同一事务内顺带重算受影响教学班的 ``selected_count``（除
  ``sync_all_students`` 外——全量同步由调用方随后调用 ``recompute_selected_count``，
  与 upgrade_db.py / 管理端修复接口的既有流程一致）。

本模块不依赖 Flask request context，可被视图函数、init_db.py / upgrade_db.py
等脚本直接 import 调用。
"""
from contextlib import contextmanager

from core import CURRENT_SEMESTER, get_db_connection

__all__ = [
    'sync_student_enrollments',
    'drop_stale_class_enrollments',
    'ensure_offering_enrollments',
    'sync_offering_classes',
    'sync_all_students',
    'recompute_selected_count',
]


# ==================== 内部工具 ====================

@contextmanager
def _tx(cursor=None):
    """事务上下文。

    * cursor 由调用方提供：复用其事务，不 commit / 不 close（异常向上抛）；
    * cursor 为 None：从连接池取连接自建事务，成功 commit、异常 rollback、最终关闭。
    """
    if cursor is not None:
        yield cursor
        return
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _fetchone(cursor, sql, params=()):
    cursor.execute(sql, params)
    return cursor.fetchone()


def _fetchall(cursor, sql, params=()):
    cursor.execute(sql, params)
    return cursor.fetchall()


def _normalize_ids(values):
    """把 id 序列转成去重后的 int 列表（非法值忽略，防止拼 SQL 注入）。"""
    result, seen = [], set()
    for v in values or ():
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


def _placeholders(ids):
    return ','.join(['%s'] * len(ids))


def _is_active_student(stu):
    """学生行是否参与统排课继承：在读且未冻结。"""
    return bool(stu) and stu['status'] == '在读' and not stu['is_frozen']


def _class_fixed_offering_ids(cursor, class_id, semester):
    """本班本学期由学校统一排课（非选修）的 offering id 列表。"""
    rows = _fetchall(cursor, """
        SELECT DISTINCT co.id AS offering_id
        FROM offering_class oc
        JOIN course_offering co ON co.id = oc.offering_id
        JOIN course c ON c.id = co.course_id
        WHERE oc.class_id = %s AND co.semester = %s AND c.type <> '选修'
        ORDER BY co.id""", (class_id, semester))
    return [r['offering_id'] for r in rows]


def _restore_student_inherited(cursor, student_id, class_id, semester):
    """把该生因历史原因此前退选、但尚未产生任何成绩的统排课恢复为「已选」。"""
    cursor.execute("""
        UPDATE enrollment e
        JOIN course_offering co ON co.id = e.offering_id
        JOIN course c ON c.id = co.course_id
        JOIN offering_class oc ON oc.offering_id = e.offering_id AND oc.class_id = %s
        SET e.status = '已选', e.select_time = NOW()
        WHERE e.student_id = %s
          AND co.semester = %s
          AND c.type <> '选修'
          AND e.status = '退选'
          AND e.usual_score IS NULL
          AND e.exam_score IS NULL
          AND e.total_score IS NULL
          AND e.is_retake = 0""", (class_id, student_id, semester))
    return cursor.rowcount


def _insert_student_inherited(cursor, student_id, class_id, semester):
    """补齐该生本班本学期的统排课记录（INSERT IGNORE 依赖唯一键保证幂等）。"""
    cursor.execute("""
        INSERT IGNORE INTO enrollment (student_id, offering_id, status, select_time)
        SELECT %s, co.id, '已选', NOW()
        FROM offering_class oc
        JOIN course_offering co ON co.id = oc.offering_id
        JOIN course c ON c.id = co.course_id
        WHERE oc.class_id = %s AND co.semester = %s AND c.type <> '选修'""",
        (student_id, class_id, semester))
    return cursor.rowcount


def _restore_offering_enrolled_classes(cursor, offering_id, class_ids):
    """把指定班级中「退选且无成绩」的学生恢复为本教学班的「已选」。"""
    ph = _placeholders(class_ids)
    cursor.execute(f"""
        UPDATE enrollment e
        JOIN student s ON s.id = e.student_id
        SET e.status = '已选', e.select_time = NOW()
        WHERE e.offering_id = %s
          AND s.class_id IN ({ph})
          AND s.status = '在读' AND s.is_frozen = 0
          AND e.status = '退选'
          AND e.usual_score IS NULL
          AND e.exam_score IS NULL
          AND e.total_score IS NULL
          AND e.is_retake = 0""", [offering_id] + class_ids)
    return cursor.rowcount


def _insert_offering_enrolled_classes(cursor, offering_id, class_ids):
    """把指定班级的在读未冻结学生加入教学班（INSERT IGNORE 幂等）。"""
    ph = _placeholders(class_ids)
    cursor.execute(f"""
        INSERT IGNORE INTO enrollment (student_id, offering_id, status, select_time)
        SELECT s.id, %s, '已选', NOW()
        FROM student s
        WHERE s.class_id IN ({ph}) AND s.status = '在读' AND s.is_frozen = 0""",
        [offering_id] + class_ids)
    return cursor.rowcount


def _recompute_selected_count(cursor, offering_ids=None):
    """内部版 selected_count 重算（复用调用方事务）；返回值发生变化的行数。

    注意：MySQL 默认返回「实际发生变化的行数」，值本来就一致的行不计入。
    """
    if offering_ids is None:
        cursor.execute("""
            UPDATE course_offering
            SET selected_count = (SELECT COUNT(*) FROM enrollment e
                                  WHERE e.offering_id = course_offering.id AND e.status = '已选')""")
        return cursor.rowcount
    ids = _normalize_ids(offering_ids)
    if not ids:
        return 0
    cursor.execute(f"""
        UPDATE course_offering
        SET selected_count = (SELECT COUNT(*) FROM enrollment e
                              WHERE e.offering_id = course_offering.id AND e.status = '已选')
        WHERE id IN ({_placeholders(ids)})""", ids)
    return cursor.rowcount


# ==================== 对外接口 ====================

def sync_student_enrollments(student_id, class_id=None, semester=CURRENT_SEMESTER, cursor=None) -> dict:
    """补齐单个学生「本班 + 本学期 + 非选修（统排课）」的选课记录。

    参数
    ----
    student_id : int
    class_id   : int|None  为 None 时查库取学生当前班级；显式传入用于「学生转班后
                先同步新班」或「新建学生同事务内继承」等场景。
    semester   : str       默认当前学期；非当前学期的数据不会被修改。
    cursor     : pymysql DictCursor|None
                传入则使用调用方事务（不 commit / 不 close），用于管理员批量导入等
                需要与主流程同事务提交的场景；否则自建连接并提交。

    行为
    ----
    * 学生不存在 / 不在读 / 已冻结 / 无班级 / 班级本学期无统排课：返回全 0；
    * 已存在「已选」记录跳过；已有「退选」且无任何成绩、非重修记录恢复为「已选」；
    * 缺失记录按 ``enrollment(学生, 课程, '已选', NOW())`` 批量插入；
    * 若发生新增/恢复，同事务内重算这些教学班的 ``selected_count``。

    返回 ``{'added': int, 'restored': int, 'offerings': int}``：
    ``added`` 新插入条数、``restored`` 恢复条数、
    ``offerings`` 该生本班本学期统排课门数（即应继承课程数）。
    """
    stats = {'added': 0, 'restored': 0, 'offerings': 0}
    with _tx(cursor) as cur:
        stu = _fetchone(cur, "SELECT id, class_id, status, is_frozen FROM student WHERE id=%s",
                        (student_id,))
        if not stu or not _is_active_student(stu):
            return stats
        target_class_id = class_id if class_id is not None else stu['class_id']
        if not target_class_id:
            return stats
        offering_ids = _class_fixed_offering_ids(cur, target_class_id, semester)
        if not offering_ids:
            return stats
        stats['restored'] = _restore_student_inherited(cur, student_id, target_class_id, semester)
        stats['added'] = _insert_student_inherited(cur, student_id, target_class_id, semester)
        stats['offerings'] = len(offering_ids)
        if stats['added'] or stats['restored']:
            _recompute_selected_count(cur, offering_ids)
        return stats


def drop_stale_class_enrollments(student_id, old_class_id, new_class_id,
                                 semester=CURRENT_SEMESTER, cursor=None) -> dict:
    """学生转班后，撤销原班级统排课中「新班级不再需要」的选课记录。

    仅删除同时满足以下条件的 enrollment：

    * 属于学生原班级（``offering_class`` 指定了 old_class_id）、本学期、非选修；
    * 尚未产生任何成绩（usual/exam/total 全 NULL）且不是重修（is_retake=0）；
    * 新班级不再被该开课指定（new_class_id 为空时视为不再需要），
      即新班级仍需要的课程会被保留。

    选修课、已产生成绩/重修记录一律不动；有成绩的旧班课程保留以便成绩追溯。
    删除后在同事务内重算受影响教学班的 ``selected_count``。

    返回 ``{'removed': int}``。
    """
    result = {'removed': 0}
    if not old_class_id:
        return result
    with _tx(cursor) as cur:
        sql = """
            SELECT DISTINCT e.offering_id
            FROM enrollment e
            JOIN course_offering co ON co.id = e.offering_id
            JOIN course c ON c.id = co.course_id
            JOIN offering_class oc ON oc.offering_id = e.offering_id AND oc.class_id = %s
            WHERE e.student_id = %s
              AND co.semester = %s
              AND c.type <> '选修'
              AND e.usual_score IS NULL
              AND e.exam_score IS NULL
              AND e.total_score IS NULL
              AND e.is_retake = 0"""
        params = [old_class_id, student_id, semester]
        if new_class_id:
            sql += """
              AND NOT EXISTS (SELECT 1 FROM offering_class oc_new
                              WHERE oc_new.offering_id = e.offering_id
                                AND oc_new.class_id = %s)"""
            params.append(new_class_id)
        rows = _fetchall(cur, sql, params)
        offering_ids = [r['offering_id'] for r in rows]
        if not offering_ids:
            return result
        cur.execute(f"""
            DELETE e FROM enrollment e
            WHERE e.student_id = %s AND e.offering_id IN ({_placeholders(offering_ids)})""",
            [student_id] + offering_ids)
        result['removed'] = cur.rowcount
        if result['removed']:
            _recompute_selected_count(cur, offering_ids)
        return result


def ensure_offering_enrollments(offering_id, semester=CURRENT_SEMESTER) -> dict:
    """教师打开名单/成绩/导入前自愈：按教学班指定班级补齐统排课学生。

    * 选修课 / 非本学期 / 教学班不存在：直接 no-op，返回 ``{'added': 0}``；
    * 非选修课：把 ``offering_class`` 指定班级中「在读且未冻结」的学生补成
      ``enrollment(status='已选')``；此前「退选且无成绩」的记录一并恢复；
    * 若发生变更，同事务内重算该教学班的 ``selected_count``。

    幂等：重复调用不会重复插入。返回 ``{'added': int}``，
    其中 ``added`` = 新插入 + 从「退选」恢复 的条数（即本次实际补进名单的人数）。
    """
    result = {'added': 0}
    with _tx() as cur:
        off = _fetchone(cur, """
            SELECT co.id, co.semester, c.type
            FROM course_offering co JOIN course c ON c.id = co.course_id
            WHERE co.id = %s""", (offering_id,))
        # course.type 为 NULL 的历史脏数据按「非统排」跳过，与 SQL `type <> '选修'` 一致
        if (not off or off['semester'] != semester
                or not off['type'] or off['type'] == '选修'):
            return result
        cur.execute("""
            UPDATE enrollment e
            JOIN student s ON s.id = e.student_id
            SET e.status = '已选', e.select_time = NOW()
            WHERE e.offering_id = %s
              AND e.status = '退选'
              AND e.usual_score IS NULL
              AND e.exam_score IS NULL
              AND e.total_score IS NULL
              AND e.is_retake = 0
              AND s.status = '在读' AND s.is_frozen = 0
              AND EXISTS (SELECT 1 FROM offering_class oc
                          WHERE oc.offering_id = e.offering_id AND oc.class_id = s.class_id)""",
            (offering_id,))
        restored = cur.rowcount
        cur.execute("""
            INSERT IGNORE INTO enrollment (student_id, offering_id, status, select_time)
            SELECT s.id, %s, '已选', NOW()
            FROM student s
            JOIN offering_class oc ON oc.offering_id = %s AND oc.class_id = s.class_id
            WHERE s.status = '在读' AND s.is_frozen = 0""",
            (offering_id, offering_id))
        inserted = cur.rowcount
        result['added'] = inserted + restored
        if result['added']:
            _recompute_selected_count(cur, [offering_id])
        return result


def sync_offering_classes(offering_id, added_class_ids, removed_class_ids) -> dict:
    """开课修改指定班级后同步学生选课（仅当前学期非选修统排课）。

    * 新增班级：该班「在读且未冻结」学生自动加入教学班（已退选且无成绩的恢复）；
    * 移除班级：撤销这些班级学生中「无任何成绩且非重修」的选课记录；
      有成绩记录保留（成绩追溯），选修课、非当前学期 no-op；
    * 只接受 CURRENT_SEMESTER 的统排课教学班，其它情况直接 no-op；
    * 变更后同事务内重算该教学班的 ``selected_count``。

    参数里的班级 id 应为「本次变更」的差集（同时出现在两个列表时以新增为准）。

    返回 ``{'added': int, 'removed': int}``（added 含从「退选」恢复的条数）。
    """
    result = {'added': 0, 'removed': 0}
    added_ids = _normalize_ids(added_class_ids)
    added_set = set(added_ids)
    removed_ids = [i for i in _normalize_ids(removed_class_ids) if i not in added_set]
    with _tx() as cur:
        off = _fetchone(cur, """
            SELECT co.id, co.semester, c.type
            FROM course_offering co JOIN course c ON c.id = co.course_id
            WHERE co.id = %s""", (offering_id,))
        if (not off or off['semester'] != CURRENT_SEMESTER
                or not off['type'] or off['type'] == '选修'):
            return result

        if removed_ids:
            cur.execute(f"""
                DELETE e FROM enrollment e
                JOIN student s ON s.id = e.student_id
                WHERE e.offering_id = %s
                  AND s.class_id IN ({_placeholders(removed_ids)})
                  AND e.usual_score IS NULL
                  AND e.exam_score IS NULL
                  AND e.total_score IS NULL
                  AND e.is_retake = 0""", [offering_id] + removed_ids)
            result['removed'] = cur.rowcount

        if added_ids:
            restored = _restore_offering_enrolled_classes(cur, offering_id, added_ids)
            inserted = _insert_offering_enrolled_classes(cur, offering_id, added_ids)
            result['added'] = inserted + restored

        if result['added'] or result['removed']:
            _recompute_selected_count(cur, [offering_id])
        return result


def sync_all_students(semester=CURRENT_SEMESTER) -> dict:
    """全量补齐：为所有「在读、未冻结、有班级」的学生补本班本学期统排课记录。

    用于 upgrade_db.py 一次性存量迁移、管理端「按班级补齐全校统排课」修复接口。
    批量 SQL（INSERT IGNORE ... SELECT / UPDATE ... JOIN）避免 N+1；单事务提交。

    注意：本函数**不**重算 ``selected_count``（由调用方随后调用
    ``recompute_selected_count``，与 upgrade_db.py / 管理端修复接口的流程一致）。

    返回 ``{'students': int, 'added': int, 'restored': int, 'offerings': int}``：
    ``students`` 参与同步的学生数、``added`` 新插入条数、``restored`` 恢复条数、
    ``offerings`` 命中的「学生-统排课」门次总数（各学生应继承课程数之和）。
    """
    stats = {'students': 0, 'added': 0, 'restored': 0, 'offerings': 0}
    with _tx() as cur:
        students = _fetchall(cur, """
            SELECT id FROM student
            WHERE status = '在读' AND is_frozen = 0 AND class_id IS NOT NULL
            ORDER BY id""")
        stats['students'] = len(students)
        if not students:
            return stats

        row = _fetchone(cur, """
            SELECT COUNT(*) AS c
            FROM student s
            JOIN offering_class oc ON oc.class_id = s.class_id
            JOIN course_offering co ON co.id = oc.offering_id
            JOIN course c ON c.id = co.course_id
            WHERE s.status = '在读' AND s.is_frozen = 0 AND s.class_id IS NOT NULL
              AND co.semester = %s AND c.type <> '选修'""", (semester,))
        stats['offerings'] = int(row['c'] or 0)

        cur.execute("""
            UPDATE enrollment e
            JOIN student s ON s.id = e.student_id
            JOIN course_offering co ON co.id = e.offering_id
            JOIN course c ON c.id = co.course_id
            JOIN offering_class oc ON oc.offering_id = e.offering_id AND oc.class_id = s.class_id
            SET e.status = '已选', e.select_time = NOW()
            WHERE s.status = '在读' AND s.is_frozen = 0
              AND co.semester = %s AND c.type <> '选修'
              AND e.status = '退选'
              AND e.usual_score IS NULL
              AND e.exam_score IS NULL
              AND e.total_score IS NULL
              AND e.is_retake = 0""", (semester,))
        stats['restored'] = cur.rowcount

        cur.execute("""
            INSERT IGNORE INTO enrollment (student_id, offering_id, status, select_time)
            SELECT s.id, co.id, '已选', NOW()
            FROM student s
            JOIN offering_class oc ON oc.class_id = s.class_id
            JOIN course_offering co ON co.id = oc.offering_id
            JOIN course c ON c.id = co.course_id
            WHERE s.status = '在读' AND s.is_frozen = 0 AND s.class_id IS NOT NULL
              AND co.semester = %s AND c.type <> '选修'""", (semester,))
        stats['added'] = cur.rowcount
        return stats


def recompute_selected_count(offering_ids=None, cursor=None) -> int:
    """按 enrollment 实际 ``status='已选'`` 人数重算教学班 ``selected_count``。

    * offering_ids 为 None：重算全表；为空列表：直接返回 0；
    * 统排课不限制容量，重算结果允许大于 ``max_count``；
    * 传入 cursor 时使用调用方事务，否则自建连接提交。

    返回实际发生变化的行数（MySQL rowcount 口径：值本来就一致的行不计入）。
    """
    with _tx(cursor) as cur:
        if offering_ids is None:
            return _recompute_selected_count(cur, None)
        ids = _normalize_ids(offering_ids)
        if not ids:
            return 0
        return _recompute_selected_count(cur, ids)
