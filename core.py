# -*- coding: utf-8 -*-
"""
基础设施模块：数据库工具、装饰器、通用函数、常量、登录限流、表格导入
被各蓝图模块（auth/common/student/teacher/admin）共享使用。
"""
import os
import csv
import io
import base64
import hashlib
import secrets
from datetime import datetime
from functools import wraps

import pymysql
from dbutils.pooled_db import PooledDB
from flask import request, session, jsonify

from config import Config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 当前学期：默认值写在代码里，跨学期无需改代码——在 .env 里设置 CURRENT_SEMESTER 即可覆盖
CURRENT_SEMESTER = (os.environ.get('CURRENT_SEMESTER') or '').strip() or '2025-2026-1'

ROLE_TABLE = {'student': ('student', 'is_frozen'), 'teacher': ('teacher', 'is_active'), 'admin': ('admin', 'is_active')}


# ==================== 数据库 ====================

# 数据库连接池：复用连接，避免每次查询都新建/销毁连接（防并发高峰耗尽 MySQL 连接数）
_pool = PooledDB(
    creator=pymysql,
    maxconnections=20,      # 最大连接数
    mincached=0,            # 懒创建，不预连数据库（首个查询时才建连）
    maxcached=10,           # 最大空闲连接数
    blocking=True,          # 连接耗尽时阻塞等待，而非直接报错
    ping=1,                 # 取连接时 ping 一下，确保连接有效
    host=Config.MYSQL_HOST,
    port=Config.MYSQL_PORT,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB,
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor,
)


def get_db_connection():
    # 从连接池取连接；调用方 conn.close() 会归还连接而非真正关闭
    return _pool.connection()


def query_all(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params or ())
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def query_one(sql, params=None):
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params or ())
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


# ==================== 装饰器 ====================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or 'user_type' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    # 强制修改密码期间仍可访问的接口
    MUST_CHANGE_EXEMPT = {'/api/auth/change-password', '/api/auth/logout',
                          '/api/auth/me', '/api/avatar'}

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # 未登录返回 401（前端据此跳登录页），角色不符才是 403
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': '请先登录'}), 401
            if session.get('user_type') != role:
                return jsonify({'success': False, 'message': '无权限访问'}), 403
            # 写操作前复查账号状态：管理员冻结/停用后，已登录会话应立刻失效
            # （会话有效期 7 天，仅在登录时校验一次状态，否则被停用账号可继续操作）
            # 注意两种标记语义相反：student.is_frozen 0=正常/1=冻结，teacher/admin.is_active 1=启用/0=停用
            if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                table, flag = ROLE_TABLE[role]
                cur_user = None
                try:
                    cur_user = query_one(
                        f"SELECT {flag} AS v, must_change_pwd, password_hash FROM {table} WHERE id=%s",
                        (session.get('user_id'),))
                except (pymysql.err.ProgrammingError, pymysql.err.OperationalError):
                    # 老库尚未升级：降级为只校验账号状态
                    print('[警告] 数据表缺少 must_change_pwd 列，请执行 python upgrade_db.py')
                    cur_user = query_one(f"SELECT {flag} AS v FROM {table} WHERE id=%s",
                                         (session.get('user_id'),))
                if not cur_user:
                    session.clear()
                    return jsonify({'success': False, 'message': '账号不存在，请重新登录'}), 401
                usable = (cur_user['v'] == 0) if flag == 'is_frozen' else (cur_user['v'] == 1)
                if not usable:
                    session.clear()
                    return jsonify({'success': False, 'message': '账号已被停用，请联系管理员'}), 403
                # 密码被修改后，其他设备上的旧会话立即失效
                if cur_user.get('password_hash') and session.get('pwd_fp') \
                        and session['pwd_fp'] != password_fingerprint(cur_user['password_hash']):
                    session.clear()
                    return jsonify({'success': False, 'message': '密码已修改，请重新登录'}), 401
                if cur_user.get('must_change_pwd') and request.path not in MUST_CHANGE_EXEMPT:
                    return jsonify({'success': False, 'must_change_pwd': True,
                                    'message': '首次登录请先修改密码后再操作'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def perm_required(perm):
    """管理员细分权限校验：在已登录且为 admin 的基础上，进一步校验权限标记。
    例如 perm='super' 要求超级管理员；普通教务员访问敏感操作返回 403。
    权限标记来自登录时写入会话的 session['is_super']（或后续扩展其他标记）。
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': '请先登录'}), 401
            if session.get('user_type') != 'admin':
                return jsonify({'success': False, 'message': '无权限访问'}), 403
            if perm == 'super' and not session.get('is_super'):
                return jsonify({'success': False, 'message': '需要超级管理员权限'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ==================== 日志 / 工具 ====================

def log_operation(action, target_table=None, target_id=None, detail=None):
    try:
        execute(
            "INSERT INTO operation_log (admin_id, action, target_table, target_id, detail, ip_address) VALUES (%s,%s,%s,%s,%s,%s)",
            (session.get('user_id') if session.get('user_type') == 'admin' else None,
             action, target_table, target_id, detail, _client_ip())
        )
    except Exception as e:
        print(f"记录操作日志失败: {e}")


def fmt_rows(rows):
    """将 date/datetime/Decimal 转为可 JSON 序列化的值"""
    for row in rows:
        for k, v in row.items():
            if isinstance(v, (datetime,)):
                row[k] = v.strftime('%Y-%m-%d %H:%M')
            elif hasattr(v, 'strftime'):
                row[k] = v.strftime('%Y-%m-%d')
            elif v.__class__.__name__ == 'Decimal':
                row[k] = float(v) if v is not None else None
    return rows


def parse_score(v):
    """校验成绩为 0-100 的数字，返回保留一位小数的浮点数；空值返回 None；非法抛 ValueError"""
    if v is None or v == '':
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError('成绩必须是数字')
    if f < 0 or f > 100:
        raise ValueError('成绩应在 0-100 之间')
    return round(f, 1)


def parse_int(v, default=None, min_value=None, max_value=None, label='数值'):
    """校验并转换整数，非法或越界抛 ValueError"""
    if v is None or v == '':
        return default
    try:
        i = int(float(v))
    except (TypeError, ValueError):
        raise ValueError(f'{label}必须是整数')
    if min_value is not None and i < min_value:
        raise ValueError(f'{label}不能小于 {min_value}')
    if max_value is not None and i > max_value:
        raise ValueError(f'{label}不能大于 {max_value}')
    return i


def calc_grade(usual, exam, usual_ratio, exam_ratio):
    """按平时/考试占比计算总评与绩点。返回 (total, point)。
    总评 = 平时×平时占比% + 考试×考试占比%；绩点 = (总评-50)/10（≥60 才有），否则 0。"""
    total = round(usual * usual_ratio / 100 + exam * exam_ratio / 100, 1)
    point = round(max(0, (total - 50) / 10), 1) if total >= 60 else 0
    return total, point


# ==================== 登录限流（防暴力破解，跨进程共享） ====================
# 存 MySQL（login_throttle 表）而非进程内存：
# gunicorn 多 worker 下每个进程各有各的内存字典，会把阈值放大 N 倍；重启也会清零。
# 数据库存储对所有 worker 可见、重启不丢，配合验证码构成稳定的防爆破闸门。

_LOGIN_MAX_FAIL = 5                                    # IP 级：连续失败次数上限
_LOGIN_BLOCK_SECONDS = 10 * 60                         # IP 级锁定时长（秒）
_ACCT_MAX_FAIL = 10                                    # 账号级：连续失败次数上限
_ACCT_BLOCK_SECONDS = 15 * 60                          # 账号级锁定时长（秒）
_TRUST_PROXY = os.environ.get('TRUST_PROXY', '').lower() in ('1', 'true', 'yes')


def _client_ip():
    """取客户端 IP。

    默认只信任 TCP 对端地址（request.remote_addr）：X-Forwarded-For 可被客户端任意伪造，
    直接采信会让攻击者通过换头绕过登录限流，也能反向伪造他人 IP 造成误锁。

    若确实部署在反向代理之后，设置环境变量 TRUST_PROXY=1 后按下列顺序取值：
      1) X-Real-IP（由 Nginx 等反代注入）；
      2) X-Forwarded-For 的最右一项（由最近一跳代理追加，最左项不可信）。
    """
    if _TRUST_PROXY:
        real = (request.headers.get('X-Real-IP') or '').strip()
        if real:
            return real
        xff = request.headers.get('X-Forwarded-For') or ''
        parts = [p.strip() for p in xff.split(',') if p.strip()]
        if parts:
            return parts[-1]
    return request.remote_addr or 'unknown'


def _throttle_is_blocked(key):
    """key 当前是否处于封禁期（DB 侧比较时间，避免应用/数据库时区不一致）"""
    row = query_one(
        "SELECT 1 AS x FROM login_throttle WHERE throttle_key=%s AND blocked_until > NOW()", (key,))
    return row is not None


def _throttle_record_fail(key, max_fail, block_seconds):
    """原子化记录一次失败：主键行锁串行化并发，达到阈值即封禁并清零计数。
    单条 UPSERT 完成「读-判-增/封」，MySQL 对 SET 子句按从左到右累计求值。"""
    execute("""
        INSERT INTO login_throttle (throttle_key, fail_count, blocked_until)
        VALUES (%s, 1, NULL)
        ON DUPLICATE KEY UPDATE
            fail_count = IF(blocked_until IS NOT NULL AND blocked_until > NOW(), fail_count, fail_count + 1),
            blocked_until = IF(fail_count >= %s AND (blocked_until IS NULL OR blocked_until <= NOW()),
                               NOW() + INTERVAL %s SECOND, blocked_until),
            fail_count = IF(fail_count >= %s, 0, fail_count)
    """, (key, max_fail, block_seconds, max_fail))


def _throttle_clear(key):
    execute("DELETE FROM login_throttle WHERE throttle_key=%s", (key,))


def _throttle_clear_all():
    """清空限流表（测试/运维用）"""
    execute("DELETE FROM login_throttle")


# ---- IP 级限流 ----

def _is_login_blocked(ip):
    return _throttle_is_blocked('ip:' + ip)


def _record_login_fail(ip):
    _throttle_record_fail('ip:' + ip, _LOGIN_MAX_FAIL, _LOGIN_BLOCK_SECONDS)


def _clear_login_fail(ip):
    _throttle_clear('ip:' + ip)


# ---- 账号级限流（防分布式换 IP 攻击同一账号；阈值高于 IP 级，且受验证码前置约束）----

def _acct_key(user_type, username):
    return f"acct:{user_type}:{username}"


def _is_account_blocked(key):
    return _throttle_is_blocked(key)


def _record_account_fail(key):
    _throttle_record_fail(key, _ACCT_MAX_FAIL, _ACCT_BLOCK_SECONDS)


def _clear_account_fail(key):
    _throttle_clear(key)


# ==================== 课表导出 ====================

def get_section_times():
    """读取作息时间，返回 {节次: {'start': 'HH:MM', 'end': 'HH:MM'}}"""
    rows = query_all("SELECT section, start_time, end_time FROM section_time ORDER BY section")
    return {r['section']: {'start': r['start_time'], 'end': r['end_time']} for r in rows}


def export_schedule_xlsx(rows, title, subtitle, show_time=True):
    """把课表数据渲染成 Excel 网格（周一~周日 × 节次），返回 BytesIO。
    show_time=True 时在时间列/课程格中附上具体钟点。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    times = get_section_times() if show_time else {}

    def range_text(start_sec, end_sec):
        a = times.get(start_sec)
        b = times.get(end_sec) or a
        return f"{a['start']}-{b['end']}" if a and b else ''

    wb = Workbook()
    ws = wb.active
    ws.title = '课表'

    title_font = Font(size=14, bold=True)
    head_fill = PatternFill('solid', fgColor='1F6FEB')
    head_font = Font(color='FFFFFF', bold=True, size=11)
    cell_font = Font(size=10)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(style='thin', color='D0D7DE')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # 标题行 + 副标题
    ws.merge_cells('A1:H1')
    ws['A1'] = title
    ws['A1'].font = title_font
    ws['A1'].alignment = center
    ws.merge_cells('A2:H2')
    ws['A2'] = subtitle
    ws['A2'].alignment = center
    ws['A2'].font = Font(size=10, color='666666')

    # 表头：节次 + 周一~周日
    headers = ['节次', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=3, column=i, value=h)
        c.fill = head_fill
        c.font = head_font
        c.alignment = center
        c.border = border

    # 按「星期-起始节次」归集
    grid = {}
    max_section = 10
    for r in rows:
        try:
            wd = int(r['weekday'])
            ss = int(r['start_section'])
            es = int(r['end_section'])
        except (TypeError, ValueError):
            continue
        max_section = max(max_section, es)
        parts = [r.get('course_name') or '']
        t = range_text(ss, es)
        if t:
            parts.append(t)
        if r.get('teacher_name'):
            parts.append(r['teacher_name'])
        if r.get('building'):
            parts.append(f"{r['building']}{r.get('room') or ''}")
        if r.get('weeks'):
            parts.append(f"{r['weeks']}周")
        grid[(wd, ss)] = {'text': '\n'.join(p for p in parts if p), 'end': es}

    # 填充网格
    for sec in range(1, max_section + 1):
        row_idx = 3 + sec
        label = f'第{sec}节'
        t = times.get(sec)
        if t:
            label += f"\n{t['start']}-{t['end']}"
        c = ws.cell(row=row_idx, column=1, value=safe_cell(label))
        c.alignment = center
        c.border = border
        c.font = Font(size=9, color='666666')
        for wd in range(1, 8):
            cell = ws.cell(row=row_idx, column=wd + 1)
            cell.alignment = center
            cell.border = border
            cell.font = cell_font
            item = grid.get((wd, sec))
            if item:
                cell.value = safe_cell(item['text'])
                if item['end'] > sec:
                    # 跨节次：合并单元格并统一边框
                    ws.merge_cells(start_row=row_idx, start_column=wd + 1,
                                   end_row=3 + item['end'], end_column=wd + 1)
                    for rr in range(row_idx, 3 + item['end'] + 1):
                        ws.cell(row=rr, column=wd + 1).border = border

    # 列宽/行高
    ws.column_dimensions['A'].width = 12
    for wd in range(1, 8):
        ws.column_dimensions[get_column_letter(wd + 1)].width = 16
    ws.row_dimensions[1].height = 26
    for sec in range(1, max_section + 1):
        ws.row_dimensions[3 + sec].height = 42

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ==================== 表格导入 ====================

def _read_uploaded_table(file_storage):
    """读取上传的 xlsx/xls/csv，返回表头列表 + 数据行列表"""
    filename = file_storage.filename or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext == 'csv':
        text = file_storage.read().decode('utf-8-sig', errors='ignore')
        reader = csv.reader(io.StringIO(text))
        rows = [r for r in reader if any(cell.strip() for cell in r)]
        if not rows:
            raise ValueError('CSV 文件为空')
        return rows[0], rows[1:]

    # Excel
    from openpyxl import load_workbook
    wb = load_workbook(file_storage, read_only=True, data_only=True)
    ws = wb.active
    data = list(ws.iter_rows(values_only=True))
    data = [list(r) for r in data if any(c is not None and str(c).strip() for r in [r] for c in r)]
    if not data:
        raise ValueError('表格内容为空')
    header = [str(c).strip() if c is not None else '' for c in data[0]]
    body = data[1:]
    return header, body


# ==================== 密码策略 ====================

# 常见弱口令（含演示账号默认值、常见键盘序列）
WEAK_PASSWORDS = {
    '123456', '1234567', '12345678', '123456789', '1234567890', '111111', '000000',
    'password', 'passw0rd', 'admin123', 'admin@123', 'abc123', 'qwerty', 'qwerty123',
    '1qaz2wsx', 'zxcvbnm', 'iloveyou', '88888888', '666666', '123123', 'a123456',
}


def password_fingerprint(password_hash):
    """密码指纹：仅用于判断"密码是否被改过"，不泄露哈希本身"""
    return hashlib.sha256(('edu-pw-fp:' + str(password_hash or '')).encode('utf-8')).hexdigest()[:20]


def validate_password(pw):
    """密码策略校验：通过返回 None，不通过返回中文错误信息"""
    if not isinstance(pw, str) or not pw:
        return '密码不能为空'
    if len(pw) < 8:
        return '密码长度不能少于 8 位'
    if len(pw) > 72:
        return '密码长度不能超过 72 位'   # bcrypt 只使用前 72 字节
    if pw.strip().lower() in WEAK_PASSWORDS:
        return '密码过于简单，请更换更复杂的密码'
    has_alpha = any(c.isalpha() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    if not (has_alpha and has_digit):
        return '密码必须同时包含字母和数字'
    if pw.islower() and has_digit:
        # 允许，但若全小写且很短则提示（不强制）
        if len(pw) < 10:
            return None
    return None


def gen_temp_password(length=12):
    """生成满足策略的随机临时密码（保证含字母与数字）"""
    alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        pw = ''.join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw):
            return pw


# ==================== 输入净化（纵深防御） ====================

def validate_name(value, label='姓名', maxlen=64):
    """姓名/工号等显示字段的输入侧净化。

    输出层（前端 esc/jsAttr）已统一转义，这里做第二道防线：
    拒绝 HTML 结构字符与控制字符，从源头阻断存储型 XSS，
    即使将来某处输出漏了转义也不会被利用。
    通过返回去除首尾空白后的字符串，非法抛 ValueError。
    """
    s = str(value or '').strip()
    if not s:
        raise ValueError(f'{label}不能为空')
    if len(s) > maxlen:
        raise ValueError(f'{label}长度不能超过 {maxlen} 个字符')
    if any(ch in s for ch in '<>'):
        raise ValueError(f'{label}不能包含 < > 等特殊字符')
    if any(ord(ch) < 32 for ch in s):
        raise ValueError(f'{label}包含非法控制字符')
    return s


# ==================== 敏感信息加密 / 脱敏 ====================

_PII_PREFIX = 'enc:v1:'
_pii_key_cache = {}


def _pii_key():
    """身份证等敏感字段的加密密钥：由 SECRET_KEY 经 HKDF 派生（无需额外配置项）

    注意：更换 SECRET_KEY 会导致已加密数据无法解密，迁移前请先解密或用密钥备份。
    """
    if 'k' not in _pii_key_cache:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        hk = HKDF(algorithm=hashes.SHA256(), length=32,
                  salt=b'edu-pii-v1', info=b'id-card-encryption')
        _pii_key_cache['k'] = hk.derive((Config.SECRET_KEY or 'fallback').encode('utf-8'))
    return _pii_key_cache['k']


def encrypt_pii(value):
    """AES-256-GCM 加密敏感字段；空值原样返回；已加密值不重复加密"""
    if value is None or value == '':
        return value
    text = str(value)
    if text.startswith(_PII_PREFIX):
        return text
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct = AESGCM(_pii_key()).encrypt(nonce, text.encode('utf-8'), None)
    return _PII_PREFIX + base64.urlsafe_b64encode(nonce + ct).decode('ascii')


def decrypt_pii(value):
    """解密敏感字段；历史明文（无前缀）原样返回，便于平滑迁移"""
    if not value:
        return value
    text = str(value)
    if not text.startswith(_PII_PREFIX):
        return text
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.urlsafe_b64decode(text[len(_PII_PREFIX):].encode('ascii'))
        return AESGCM(_pii_key()).decrypt(raw[:12], raw[12:], None).decode('utf-8')
    except Exception as e:
        print(f'敏感字段解密失败: {e}')
        return ''


def mask_id_card(value):
    """身份证脱敏：保留前 3 位与后 4 位，如 520***********1234"""
    s = str(value or '')
    if not s:
        return s
    if len(s) <= 7:
        return '*' * len(s)
    return s[:3] + '*' * (len(s) - 7) + s[-4:]


def encrypt_and_mask_id_card(value):
    """读取路径用：先解密再脱敏"""
    return mask_id_card(decrypt_pii(value))


# ==================== 导出安全 ====================

def safe_cell(value):
    """防 Excel 公式注入：以 = + - @ 或制表/回车开头的文本前加单引号"""
    if not isinstance(value, str) or not value:
        return value
    if value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


# ==================== 登录审计 ====================

def log_auth_event(action, user_type, username, ok, detail=''):
    """记录登录成功/失败（用于安全审计；不依赖登录状态）"""
    try:
        execute(
            "INSERT INTO operation_log (admin_id, action, target_table, target_id, detail, ip_address) "
            "VALUES (NULL,%s,%s,NULL,%s,%s)",
            (action, user_type,
             f"{username} | {'成功' if ok else '失败'}{(' | ' + detail) if detail else ''}",
             _client_ip()))
    except Exception as e:
        print(f'记录登录审计失败: {e}')
