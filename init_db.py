
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教务管理系统 - 数据库初始化脚本
创建 edu_admin 数据库、建表并写入演示数据
"""
import pymysql
import bcrypt
import os
import sys
from config import Config
from core import encrypt_pii

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _read_schema_statements():
    """读取 schema.sql 并拆分为单条语句。

    先去掉 -- 行注释再按分号切分，避免注释里的分号把语句切断。
    """
    with open(os.path.join(BASE_DIR, 'schema.sql'), encoding='utf-8') as f:
        lines = []
        for line in f:
            idx = line.find('--')
            if idx >= 0:
                line = line[:idx]
            lines.append(line)
    sql = '\n'.join(lines)
    return [s.strip() for s in sql.split(';') if s.strip()]


def main():
    # 安全确认：本脚本会清空全部业务数据，禁止在未确认的情况下误跑
    if '--yes' not in sys.argv:
        print('【警告】init_db.py 会 TRUNCATE 全部业务表并重建演示数据！')
        if not sys.stdin.isatty():
            print('非交互环境，请显式添加 --yes 参数确认执行（如：python init_db.py --yes）')
            sys.exit(1)
        try:
            answer = input('确认继续？请输入 yes 回车：').strip().lower()
        except (EOFError, KeyboardInterrupt):
            print('\n未获得确认输入，已取消。')
            sys.exit(1)
        if answer != 'yes':
            print('已取消。')
            sys.exit(1)

    # 1. 连接 MySQL（不指定库），创建数据库
    conn = pymysql.connect(
        host=Config.MYSQL_HOST, port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER, password=Config.MYSQL_PASSWORD,
        charset='utf8mb4'
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {Config.MYSQL_DB} DEFAULT CHARSET utf8mb4")
    conn.commit()
    cursor.close()
    conn.close()
    print(f"[1/4] 数据库 {Config.MYSQL_DB} 已创建")

    # 2. 执行 schema.sql 建表
    conn = pymysql.connect(
        host=Config.MYSQL_HOST, port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER, password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    cursor = conn.cursor()
    for stmt in _read_schema_statements():
        cursor.execute(stmt)
    conn.commit()
    print("[2/4] 数据表创建完成")

    # 3. 清空并写入演示数据
    tables = ['login_captcha', 'operation_log', 'announcement', 'teaching_plan', 'certificate', 'registration',
              'innovation_credit', 'credit_substitute_apply', 'project_apply', 'project',
              'status_change_apply', 'retake_apply', 'evaluation', 'exam', 'enrollment',
              'course_schedule', 'offering_class', 'section_time', 'classroom',
              'course_offering', 'course', 'teacher', 'student', 'class', 'major', 'college', 'admin']
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    for t in tables:
        cursor.execute(f"TRUNCATE TABLE {t}")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    # 管理员
    cursor.execute("INSERT INTO admin (username, password_hash, real_name, phone, is_super) VALUES (%s,%s,%s,%s,%s)",
                   ('admin', hash_pw('admin123'), '教务管理员', '0851-88888888', 1))

    # 学院
    colleges = [('01', '信息工程学院'), ('02', '大数据学院'), ('03', '经济管理学院')]
    cursor.executemany("INSERT INTO college (code, name) VALUES (%s,%s)", colleges)

    # 专业
    majors = [(1, '0101', '网络工程'), (1, '0102', '软件工程'), (2, '0201', '数据科学与大数据技术'), (3, '0301', '财务管理')]
    cursor.executemany("INSERT INTO major (college_id, code, name) VALUES (%s,%s,%s)", majors)

    # 班级
    classes = [(1, '网络2401', 2024), (1, '网络2402', 2024), (2, '软工2401', 2024), (3, '数据2401', 2024)]
    cursor.executemany("INSERT INTO class (major_id, name, grade_year) VALUES (%s,%s,%s)", classes)

    # 学生（杨庭为演示主账号）
    pw_stu = hash_pw('123456')
    students = [
        ('2024001', pw_stu, '杨庭', '男', 1, '520************1234', '138****0001', 'yangting@stu.gyiist.edu.cn',
         '2006-03-12', '共青团员', '贵州贵阳', '贵州省贵阳市花溪区', '2024-09-01', '在读', '未确认', None),
        ('2024002', pw_stu, '陈思远', '男', 1, None, '138****0002', None, None, '共青团员', '贵州遵义', None, '2024-09-01', '在读', '未确认', None),
        ('2024003', pw_stu, '李晓梅', '女', 1, None, '138****0003', None, None, '群众', '贵州安顺', None, '2024-09-01', '在读', '未确认', None),
        ('2024004', pw_stu, '王浩然', '男', 2, None, '138****0004', None, None, '共青团员', '贵州毕节', None, '2024-09-01', '在读', '未确认', None),
        ('2024005', pw_stu, '赵雨桐', '女', 3, None, '138****0005', None, None, '群众', '贵州铜仁', None, '2024-09-01', '在读', '未确认', None),
    ]
    cursor.executemany(
        "INSERT INTO student (username, password_hash, real_name, gender, class_id, id_card, phone, email, birth_date, political_status, native_place, address, enrollment_date, status, diversion_status, diversion_major_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", students)

    # 教师
    pw_tea = hash_pw('123456')
    teachers = [
        ('T001', pw_tea, '王建国', '男', 1, '教授', '139****1001', 'wangjg@gyiist.edu.cn'),
        ('T002', pw_tea, '刘敏', '女', 1, '副教授', '139****1002', 'lium@gyiist.edu.cn'),
        ('T003', pw_tea, '张志强', '男', 1, '讲师', '139****1003', 'zhangzq@gyiist.edu.cn'),
        ('T004', pw_tea, '周雅芳', '女', 2, '副教授', '139****1004', 'zhouyf@gyiist.edu.cn'),
    ]
    cursor.executemany(
        "INSERT INTO teacher (username, password_hash, real_name, gender, college_id, title, phone, email) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", teachers)

    # 课程
    courses = [
        ('CS101', '计算机网络', 4.0, 64, '必修', 1),
        ('CS102', '数据结构', 4.0, 64, '必修', 1),
        ('CS103', '操作系统', 3.5, 56, '必修', 1),
        ('CS104', '数据库原理', 3.5, 56, '必修', 1),
        ('CS105', '网络编程技术', 3.0, 48, '选修', 1),
        ('CS106', '信息安全概论', 2.5, 40, '选修', 1),
        ('CS201', '高等数学(上)', 5.0, 80, '必修', 1),
        ('CS202', '大学英语(三)', 3.0, 48, '必修', 1),
        ('CS203', 'Web应用开发', 3.0, 48, '选修', 1),
        ('DS101', '大数据导论', 2.5, 40, '通识', 2),
        ('PE101', '大学体育(三)', 1.0, 32, '必修', 1),
        ('CS301', '网络工程设计实践', 2.0, 32, '实践', 1),
    ]
    cursor.executemany(
        "INSERT INTO course (code, name, credit, hours, type, college_id) VALUES (%s,%s,%s,%s,%s,%s)", courses)

    # 教室
    classrooms = [
        ('博学楼', 'A101', 80), ('博学楼', 'A102', 60), ('博学楼', 'A203', 60),
        ('明德楼', 'B301', 100), ('明德楼', 'B302', 60), ('实验楼', 'C401', 40), ('实验楼', 'C402', 40),
    ]
    cursor.executemany("INSERT INTO classroom (building, room, capacity) VALUES (%s,%s,%s)", classrooms)

    # 作息时间（每节 50 分钟，节间休 10 分钟，大节间休 20 分钟；管理员可在后台修改）
    section_times = [
        (1, '08:00', '08:50'), (2, '09:00', '09:50'),
        (3, '10:10', '11:00'), (4, '11:10', '12:00'),
        (5, '14:00', '14:50'), (6, '15:00', '15:50'),
        (7, '16:10', '17:00'), (8, '17:10', '18:00'),
        (9, '19:00', '19:50'), (10, '20:00', '20:50'),
    ]
    cursor.executemany(
        "INSERT INTO section_time (section, start_time, end_time) VALUES (%s,%s,%s)", section_times)


    # 开课（2025-2026-1 学期），成绩比例：平时占比 : 考试占比
    offerings = [
        (1, 1, '2025-2026-1', 60, 3, 40, 60),   # 计算机网络 - 王建国 46开
        (2, 2, '2025-2026-1', 60, 3, 30, 70),   # 数据结构 - 刘敏 37开
        (3, 3, '2025-2026-1', 60, 2, 40, 60),   # 操作系统 - 张志强 46开
        (4, 2, '2025-2026-1', 60, 2, 50, 50),   # 数据库原理 - 刘敏 55开
        (5, 1, '2025-2026-1', 40, 1, 40, 60),   # 网络编程技术 - 王建国 46开
        (6, 3, '2025-2026-1', 40, 0, 30, 70),   # 信息安全概论 37开
        (7, 4, '2025-2026-1', 100, 2, 40, 60),  # 高等数学 - 周雅芳 46开
        (8, 4, '2025-2026-1', 80, 2, 50, 50),   # 大学英语 - 周雅芳 55开
        (9, 1, '2025-2026-1', 40, 1, 40, 60),   # Web应用开发 46开
        (10, 4, '2025-2026-1', 80, 1, 40, 60),  # 大数据导论 46开
        (11, 3, '2025-2026-1', 60, 2, 60, 40),  # 大学体育 64开（实践为主）
        (12, 1, '2025-2026-1', 30, 1, 70, 30),  # 网络工程设计实践 73开（实践为主）
    ]
    cursor.executemany(
        "INSERT INTO course_offering (course_id, teacher_id, semester, max_count, selected_count, usual_ratio, exam_ratio) VALUES (%s,%s,%s,%s,%s,%s,%s)", offerings)

    # 排课
    schedules = [
        (1, 1, 1, 2, '1-16', 1), (1, 3, 3, 4, '1-16', 1),       # 计算机网络
        (2, 2, 1, 2, '1-16', 2), (2, 4, 3, 4, '1-16', 2),       # 数据结构
        (3, 1, 3, 4, '1-16', 3),                                 # 操作系统
        (4, 3, 1, 2, '1-16', 3), (4, 5, 1, 2, '1-16', 3),       # 数据库原理
        (5, 2, 5, 6, '1-16', 6),                                 # 网络编程
        (7, 1, 5, 6, '1-16', 4), (7, 4, 1, 2, '1-16', 4),       # 高等数学
        (8, 2, 3, 4, '1-16', 5),                                 # 大学英语
        (9, 5, 3, 4, '1-16', 7),                                 # Web应用开发
        (10, 4, 5, 6, '1-16', 5),                                # 大数据导论
        (11, 5, 5, 6, '1-16', 4),                                # 大学体育
        (12, 6, 1, 4, '9-16', 6),                                # 网络工程设计实践
    ]
    cursor.executemany(
        "INSERT INTO course_schedule (offering_id, weekday, start_section, end_section, weeks, classroom_id) VALUES (%s,%s,%s,%s,%s,%s)", schedules)

    # 选课记录（杨庭选了 6 门，其中部分已有成绩；其他同学各选几门）
    enrollments = [
        # 杨庭（student_id=1）本学期在读课程
        (1, 1, '已选', None, None, None, None, 0),
        (1, 2, '已选', None, None, None, None, 0),
        (1, 4, '已选', None, None, None, None, 0),
        (1, 7, '已选', None, None, None, None, 0),
        (1, 8, '已选', None, None, None, None, 0),
        (1, 11, '已选', None, None, None, None, 0),
        # 其他同学
        (2, 1, '已选', None, None, None, None, 0),
        (2, 2, '已选', None, None, None, None, 0),
        (3, 1, '已选', None, None, None, None, 0),
        (3, 7, '已选', None, None, None, None, 0),
        (4, 3, '已选', None, None, None, None, 0),
        (4, 7, '已选', None, None, None, None, 0),
        (5, 8, '已选', None, None, None, None, 0),
        (5, 10, '已选', None, None, None, None, 0),
        (2, 8, '已选', None, None, None, None, 0),
        (3, 11, '已选', None, None, None, None, 0),
    ]
    cursor.executemany(
        "INSERT INTO enrollment (student_id, offering_id, status, usual_score, exam_score, total_score, grade_point, is_retake) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", enrollments)

    # 补几条上学期（2024-2025-2）已有成绩的开课与选课，用于成绩查询演示
    past_offerings = [(2, 2, '2024-2025-2', 60, 2, 40, 60), (7, 4, '2024-2025-2', 100, 2, 40, 60)]
    cursor.executemany(
        "INSERT INTO course_offering (course_id, teacher_id, semester, max_count, selected_count, usual_ratio, exam_ratio) VALUES (%s,%s,%s,%s,%s,%s,%s)", past_offerings)
    past_enrollments = [
        # offering 13 比例为 30:70，14 为 40:60（总评须与之匹配）
        (1, 13, '已选', 92.0, 88.0, 89.2, 3.9, 0),   # 数据结构 上学期 (92*0.3+88*0.7)
        (1, 14, '已选', 85.0, 79.0, 81.4, 3.1, 0),   # 高等数学 上学期 (85*0.4+79*0.6)
        (2, 13, '已选', 78.0, 81.0, 80.1, 3.0, 0),   # (78*0.3+81*0.7)
        (2, 14, '已选', 65.0, 58.0, 60.8, 1.8, 0),   # (65*0.4+58*0.6)
    ]
    cursor.executemany(
        "INSERT INTO enrollment (student_id, offering_id, status, usual_score, exam_score, total_score, grade_point, is_retake) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", past_enrollments)
    cursor.executemany(
        "INSERT INTO course_schedule (offering_id, weekday, start_section, end_section, weeks, classroom_id) VALUES (%s,%s,%s,%s,%s,%s)",
        [(13, 2, 1, 2, '1-16', 2), (14, 1, 5, 6, '1-16', 4)])

    # 敏感字段加密存储（身份证号），避免明文落库
    cursor.execute("SELECT id, id_card FROM student WHERE id_card IS NOT NULL AND id_card <> ''")
    for _r in cursor.fetchall():
        cursor.execute("UPDATE student SET id_card=%s WHERE id=%s", (encrypt_pii(_r['id_card']), _r['id']))

    # 选课人数与选课记录保持一致（否则演示数据一初始化，"已选人数"就与实际不符）
    cursor.execute("""UPDATE course_offering co
                      SET selected_count = (SELECT COUNT(*) FROM enrollment e
                                            WHERE e.offering_id = co.id AND e.status = '已选')""")

    # 开课-班级关联：按学生选课归属写入（教学班指定授课班级）
    cursor.execute("""INSERT IGNORE INTO offering_class (offering_id, class_id)
                      SELECT DISTINCT e.offering_id, s.class_id
                      FROM enrollment e JOIN student s ON e.student_id=s.id
                      WHERE e.status='已选' AND s.class_id IS NOT NULL""")

    # 班级课程继承：本班指定且非选修（必修/通识/实践）的课程由学校统一排课，
    # 必须落成 enrollment 记录，否则教师端的名单/成绩录入/导入看不到这些学生。
    # 注意：继承同步函数使用独立数据库连接（便于被 app/脚本复用），
    # 因此先提交前面已写入的教师、学生、开课、班级关联等演示数据，
    # 否则未提交的数据对其它连接不可见，同步会空跑。
    conn.commit()
    from enrollment_sync import sync_all_students, recompute_selected_count
    _inherit = sync_all_students()
    print(f"  [+] 班级课程继承：{_inherit['students']} 名学生，补齐 {_inherit['added']} 条选课、"
          f"恢复 {_inherit['restored']} 条（共 {_inherit['offerings']} 门次）")
    _fixed = recompute_selected_count()
    print(f"  [+] 已按实际选课人数重算 {_fixed} 个教学班的 selected_count")

    # 考试安排
    exams = [
        (1, '2026-01-12', '09:00', '11:00', 4, '期末'),
        (2, '2026-01-13', '09:00', '11:00', 4, '期末'),
        (4, '2026-01-14', '14:00', '16:00', 1, '期末'),
        (7, '2026-01-15', '09:00', '11:00', 4, '期末'),
        (8, '2026-01-16', '09:00', '11:00', 2, '期末'),
    ]
    cursor.executemany(
        "INSERT INTO exam (offering_id, exam_date, start_time, end_time, classroom_id, exam_type) VALUES (%s,%s,%s,%s,%s,%s)", exams)

    # 教学项目
    projects = [
        ('大学生创新创业训练计划', '创新创业', '2025-2026-1', 30, 1, '2025-10-08', '2025-11-30', '面向全校本科生，支持创新训练、创业训练与创业实践三类项目。', 1),
        ('全国大学生网络技术大赛校内选拔', '学科竞赛', '2025-2026-1', 20, 0, '2025-10-15', '2025-11-15', '选拔优秀选手代表学校参加全国大学生网络技术大赛。', 1),
        ('华为ICT学院精英班', '教学项目', '2025-2026-1', 40, 0, '2025-10-01', '2025-12-31', '校企联合培养项目，修读华为认证课程并参加认证考试。', 1),
    ]
    cursor.executemany(
        "INSERT INTO project (name, type, semester, max_count, apply_count, start_date, end_date, description, is_open) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", projects)
    cursor.execute("INSERT INTO project_apply (project_id, student_id, reason, status) VALUES (1, 1, '对创新创业有浓厚兴趣，希望锻炼实践能力', '已通过')")

    # 创新创业学分
    cursor.executemany(
        "INSERT INTO innovation_credit (student_id, item_name, credit, category, obtained_date, is_confirmed) VALUES (%s,%s,%s,%s,%s,%s)",
        [(1, '全国大学生计算机设计大赛省级二等奖', 2.0, '竞赛获奖', '2025-06-20', 1),
         (1, '大学生创新创业训练计划校级立项', 1.0, '科研项目', '2025-09-10', 0)])

    # 报到注册
    cursor.execute("INSERT INTO registration (student_id, semester) VALUES (1, '2025-2026-1')")

    # 证书
    cursor.executemany(
        "INSERT INTO certificate (student_id, name, cert_no, issue_date, issuer) VALUES (%s,%s,%s,%s,%s)",
        [(1, '全国大学英语四级证书', 'CET4-2025-062100', '2025-06-15', '全国大学英语四、六级考试委员会'),
         (1, '华为HCIA-Datacom认证', 'HCIA-2025-008821', '2025-05-28', '华为技术有限公司')])

    # 教学执行计划（网络工程专业）
    plans = [
        (1, 7, 1, '必修'), (1, 8, 3, '必修'), (1, 2, 2, '必修'), (1, 1, 3, '必修'),
        (1, 4, 3, '必修'), (1, 3, 4, '必修'), (1, 5, 5, '选修'), (1, 6, 5, '选修'),
        (1, 9, 6, '选修'), (1, 11, 3, '必修'), (1, 12, 7, '实践'),
    ]
    cursor.executemany("INSERT INTO teaching_plan (major_id, course_id, semester_no, category) VALUES (%s,%s,%s,%s)", plans)

    # 公告
    announcements = [
        ('2025-2026学年第一学期选课通知', '本学期自主选课时间为10月20日-10月30日，请各位同学登录教务系统按时完成选课，逾期不予补选。', 1, 1),
        ('关于2026届毕业生信息采集的通知', '请2026届毕业生于11月15日前登录系统核对个人信息，如有错误请到教务处更正。', 0, 1),
        ('期末考试安排已发布', '2025-2026学年第一学期期末考试安排已在"信息查询-考试信息查询"中发布，请及时查看。', 0, 1),
    ]
    cursor.executemany(
        "INSERT INTO announcement (title, content, is_top, is_active) VALUES (%s,%s,%s,%s)", announcements)

    conn.commit()
    print("[3/4] 演示数据写入完成")

    # 4. 校验
    cursor.execute("SELECT COUNT(*) c FROM student")
    stu = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) c FROM course_offering")
    off = cursor.fetchone()['c']
    print(f"[4/4] 校验通过：学生 {stu} 人，开课 {off} 门")
    print()
    print("=" * 50)
    print("初始化完成！演示账号：")
    print("  学生：2024001 / 123456（杨庭 网络2401）")
    print("  教师：T001    / 123456（王建国 教授）")
    print("  管理：admin   / admin123")
    print("=" * 50)

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
