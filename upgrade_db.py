#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库结构升级脚本（幂等，可重复执行）

用途：已部署过的系统，在代码更新后补齐新增的表/数据，且【不会清空已有业务数据】。
与 init_db.py 的区别：init_db.py 会 TRUNCATE 全部表（仅用于首次初始化），
本脚本只做「缺什么补什么」。

用法：
    python upgrade_db.py
"""
import os
import sys

import pymysql

from config import Config


def get_conn(with_db=True):
    kw = dict(
        host=Config.MYSQL_HOST, port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER, password=Config.MYSQL_PASSWORD,
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
    )
    if with_db:
        kw['database'] = Config.MYSQL_DB
    return pymysql.connect(**kw)


def table_exists(cursor, name):
    cursor.execute("""SELECT COUNT(*) c FROM information_schema.tables
                      WHERE table_schema=%s AND table_name=%s""", (Config.MYSQL_DB, name))
    return cursor.fetchone()['c'] > 0


# ---------------- 各项升级 ----------------

def upgrade_section_time(cursor):
    """作息时间表：每节课的开始/结束时间（各端课表显示用）"""
    if not table_exists(cursor, 'section_time'):
        cursor.execute("""
            CREATE TABLE section_time (
                id INT PRIMARY KEY AUTO_INCREMENT,
                section INT NOT NULL UNIQUE COMMENT '节次 1-10',
                start_time VARCHAR(8) NOT NULL COMMENT '开始时间 HH:MM',
                end_time VARCHAR(8) NOT NULL COMMENT '结束时间 HH:MM'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='作息时间表'
        """)
        print('  [+] 已创建表 section_time')

    defaults = [
        (1, '08:00', '08:50'), (2, '09:00', '09:50'),
        (3, '10:10', '11:00'), (4, '11:10', '12:00'),
        (5, '14:00', '14:50'), (6, '15:00', '15:50'),
        (7, '16:10', '17:00'), (8, '17:10', '18:00'),
        (9, '19:00', '19:50'), (10, '20:00', '20:50'),
    ]
    cursor.execute("SELECT COUNT(*) c FROM section_time")
    before = cursor.fetchone()['c']
    for sec, st, et in defaults:
        cursor.execute("""INSERT IGNORE INTO section_time (section, start_time, end_time)
                          VALUES (%s,%s,%s)""", (sec, st, et))
    cursor.execute("SELECT COUNT(*) c FROM section_time")
    after = cursor.fetchone()['c']
    if after > before:
        print(f'  [+] 已补写作息时间 {after - before} 条（共 {after} 条）')
    else:
        print(f'  [=] 作息时间已存在 {after} 条，跳过')


def upgrade_offering_class(cursor):
    """开课-班级关联表：教学班指定授课班级"""
    if not table_exists(cursor, 'offering_class'):
        cursor.execute("""
            CREATE TABLE offering_class (
                id INT PRIMARY KEY AUTO_INCREMENT,
                offering_id INT NOT NULL,
                class_id INT NOT NULL,
                UNIQUE KEY uk_offering_class (offering_id, class_id),
                FOREIGN KEY (offering_id) REFERENCES course_offering(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES class(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print('  [+] 已创建表 offering_class')
        # 按现有选课归属回填班级关联
        cursor.execute("""INSERT IGNORE INTO offering_class (offering_id, class_id)
                          SELECT DISTINCT e.offering_id, s.class_id
                          FROM enrollment e JOIN student s ON e.student_id=s.id
                          WHERE e.status='已选' AND s.class_id IS NOT NULL""")
        print(f'  [+] 已按现有选课回填 {cursor.rowcount} 条班级关联')
    else:
        print('  [=] 表 offering_class 已存在，跳过')


def upgrade_class_enrollment(cursor):
    """班级课程继承：把「本班指定且非选修」的本学期课程补齐为 enrollment（幂等）。

    背景：教师端成绩录入/导入/名单/模板只从 enrollment 取学生；而 offering_class
    指定的必修/通识/实践课由学校统一排课，历史上没有落成选课记录，导致新学生
    在教师端看不到、导不进成绩。本步骤一次性补齐存量数据（之后由各入口自愈保持
    同步），选修课不受影响、已有成绩记录不会被改动。重复执行不会重复插入。

    实现说明：同步逻辑由 enrollment_sync 自建连接并提交，cursor 参数仅用于与
    其它升级步骤保持统一签名。
    """
    from enrollment_sync import sync_all_students, recompute_selected_count

    stats = sync_all_students() or {}
    added = int(stats.get('added', 0))
    restored = int(stats.get('restored', 0))
    if added or restored:
        print(f"  [+] 班级课程继承：{stats.get('students', 0)} 名学生，"
              f"补齐选课 {added} 条、恢复 {restored} 条（{stats.get('offerings', 0)} 门次）")
    else:
        print(f"  [=] 班级课程继承：{stats.get('students', 0)} 名学生的统排课选课记录已完整")
    updated = recompute_selected_count()
    if updated:
        print(f'  [+] 已重算 {updated} 个教学班的已选人数')
    else:
        print('  [=] 各教学班已选人数与实际一致，无需重算')


def upgrade_login_captcha(cursor):
    """登录验证码表：防爆破（一次性 token，5 分钟过期）"""
    if table_exists(cursor, 'login_captcha'):
        print('  [=] 表 login_captcha 已存在，跳过')
        return
    cursor.execute("""
        CREATE TABLE login_captcha (
            token VARCHAR(32) PRIMARY KEY COMMENT '一次性令牌，登录时随验证码字符一起提交',
            code VARCHAR(8) NOT NULL COMMENT '验证码字符',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录图形验证码'
    """)
    print('  [+] 已创建表 login_captcha')


def upgrade_core_tables(cursor):
    """按 schema.sql 补齐缺失的表：CREATE TABLE IF NOT EXISTS 幂等，不会动已有数据和表结构"""
    from init_db import _read_schema_statements
    cursor.execute("""SELECT COUNT(*) c FROM information_schema.tables
                      WHERE table_schema=%s""", (Config.MYSQL_DB,))
    before = cursor.fetchone()['c']
    for stmt in _read_schema_statements():
        if stmt.lstrip().upper().startswith('CREATE TABLE'):
            cursor.execute(stmt)
    cursor.execute("""SELECT COUNT(*) c FROM information_schema.tables
                      WHERE table_schema=%s""", (Config.MYSQL_DB,))
    after = cursor.fetchone()['c']
    print(f'  [{"+" if after > before else "="}] 数据表 {before} → {after} 张' +
          (f'（补齐 {after - before} 张）' if after > before else '（无缺失）'))



def _has_column(cursor, table, column):
    cursor.execute("""SELECT COUNT(*) c FROM information_schema.columns
                      WHERE table_schema=%s AND table_name=%s AND column_name=%s""",
                   (Config.MYSQL_DB, table, column))
    return cursor.fetchone()['c'] > 0


def upgrade_password_policy(cursor):
    """为三张账号表补充 must_change_pwd（首次登录强制改密）列"""
    added = 0
    for table in ('admin', 'student', 'teacher'):
        if not table_exists(cursor, table):
            continue
        if not _has_column(cursor, table, 'must_change_pwd'):
            cursor.execute(f"""ALTER TABLE {table}
                               ADD COLUMN must_change_pwd TINYINT(1) DEFAULT 0
                               COMMENT '首次登录需强制修改密码'""")
            added += 1
            print(f'  [+] {table} 已新增 must_change_pwd 列')
        else:
            print(f'  [=] {table}.must_change_pwd 已存在')
    if not added:
        print('  [=] 三张账号表均已具备 must_change_pwd')


def upgrade_admin_super(cursor):
    """为 admin 表补充 is_super（超级管理员细分权限）列，并把现有管理员设为超级管理员"""
    if not table_exists(cursor, 'admin'):
        print('  [=] admin 表不存在，跳过')
        return
    if not _has_column(cursor, 'admin', 'is_super'):
        cursor.execute("""ALTER TABLE admin
                           ADD COLUMN is_super TINYINT(1) NOT NULL DEFAULT 0
                           COMMENT '是否超级管理员（可看审计日志等敏感操作）'""")
        print('  [+] admin 已新增 is_super 列')
        # 既有管理员默认提为超级管理员，避免升级后原有账号失去日志等敏感权限
        cursor.execute("UPDATE admin SET is_super=1 WHERE is_super=0")
        if cursor.rowcount:
            print(f'  [+] 已将 {cursor.rowcount} 名既有管理员设为超级管理员')
    else:
        print('  [=] admin.is_super 已存在')


def upgrade_encrypt_pii(cursor):
    """把历史明文身份证号加密（AES-256-GCM），已加密的跳过"""
    from core import encrypt_pii
    if not _has_column(cursor, 'student', 'id_card'):
        print('  [=] student.id_card 不存在，跳过')
        return
    # 先确保列宽能容纳密文（enc:v1: + base64(nonce + ciphertext) 约 60-90 字符）
    cursor.execute("""SELECT CHARACTER_MAXIMUM_LENGTH AS len FROM information_schema.columns
                      WHERE table_schema=%s AND table_name='student' AND column_name='id_card'""",
                   (Config.MYSQL_DB,))
    info = cursor.fetchone()
    if info and (info['len'] or 0) < 100:
        cursor.execute("ALTER TABLE student MODIFY id_card VARCHAR(255) "
                       "COMMENT '身份证号（AES-GCM 加密存储）'")
        print('  [+] student.id_card 列宽已扩展为 VARCHAR(255)')
    cursor.execute("""SELECT id, id_card FROM student
                      WHERE id_card IS NOT NULL AND id_card <> ''
                        AND id_card NOT LIKE 'enc:v1:%'""")
    rows = cursor.fetchall()
    for r in rows:
        cursor.execute("UPDATE student SET id_card=%s WHERE id=%s",
                       (encrypt_pii(r['id_card']), r['id']))
    if rows:
        print(f'  [+] 身份证号加密 {len(rows)} 条')
    else:
        print('  [=] 无明文身份证号需加密')

UPGRADES = [
    ('补齐 schema.sql 中的数据表', upgrade_core_tables),
    ('作息时间表 section_time', upgrade_section_time),
    ('开课-班级关联 offering_class', upgrade_offering_class),
    ('班级课程继承（enrollment 同步）', upgrade_class_enrollment),
    ('登录验证码 login_captcha', upgrade_login_captcha),
    ('密码策略 must_change_pwd 列', upgrade_password_policy),
    ('管理员细分权限 is_super 列', upgrade_admin_super),
    ('身份证号加密存储', upgrade_encrypt_pii),
]


def main():
    print('=' * 52)
    print('教务管理系统 - 数据库结构升级（幂等，不影响已有数据）')
    print('=' * 52)
    print(f'数据库：{Config.MYSQL_HOST}:{Config.MYSQL_PORT}/{Config.MYSQL_DB}')

    # 先确认库存在
    try:
        root = get_conn(with_db=False)
    except Exception as e:
        print(f'\n[错误] 无法连接 MySQL：{e}')
        sys.exit(1)
    with root.cursor() as cur:
        cur.execute("SELECT SCHEMA_NAME FROM information_schema.schemata WHERE SCHEMA_NAME=%s",
                    (Config.MYSQL_DB,))
        if not cur.fetchone():
            print(f'\n[错误] 数据库 {Config.MYSQL_DB} 不存在，请先运行 python init_db.py 初始化')
            root.close()
            sys.exit(1)
    root.close()

    conn = get_conn()
    failed = []
    try:
        with conn.cursor() as cur:
            for label, fn in UPGRADES:
                print(f'\n[{label}]')
                try:
                    fn(cur)
                    conn.commit()
                except Exception as e:
                    # MySQL 的 DDL 会隐式提交，无法真正回滚：逐个步骤容错并如实报告
                    failed.append(label)
                    print(f'  [错误] {label} 升级失败：{e}')
    finally:
        conn.close()

    if failed:
        print('\n' + '=' * 52)
        print('[警告] 以下步骤失败：' + '、'.join(failed))
        print('注意：MySQL 建表语句会隐式提交，"回滚"无效；已成功的步骤保持生效，')
        print('      修复上述问题后重新执行本脚本即可继续补齐（脚本本身幂等）。')
        print('=' * 52)
        sys.exit(1)

    print('\n' + '=' * 52)
    print('升级完成！重启服务后生效。')
    print('=' * 52)


if __name__ == '__main__':
    main()
