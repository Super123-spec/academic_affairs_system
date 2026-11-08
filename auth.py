# -*- coding: utf-8 -*-
"""认证与头像蓝图：登录、登出、当前用户、修改密码、头像上传、登录验证码"""
import base64
import os
import secrets
from datetime import datetime

import bcrypt
from captcha.image import ImageCaptcha
from flask import Blueprint, request, jsonify, session, send_from_directory

from core import (BASE_DIR, ROLE_TABLE, query_one, execute, get_db_connection, log_operation,
                  _client_ip, _is_login_blocked, _record_login_fail, _clear_login_fail,
                  _acct_key, _is_account_blocked, _record_account_fail, _clear_account_fail,
                  login_required, validate_password, password_fingerprint, log_auth_event)

auth_bp = Blueprint('auth', __name__)

# 登录验证码：去掉易混淆字符（0/O、1/I/L）
CAPTCHA_CHARS = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'

AVATAR_DIR = os.path.join(BASE_DIR, 'static', 'uploads', 'avatar')
os.makedirs(AVATAR_DIR, exist_ok=True)
ALLOWED_AVATAR_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _valid_image_signature(data, ext):
    """校验文件头 magic bytes 是否与扩展名匹配（防伪造扩展名上传非图片内容）"""
    if not data:
        return False
    if ext == 'png':
        return data[:8] == b'\x89PNG\r\n\x1a\n'
    if ext in ('jpg', 'jpeg'):
        return data[:3] == b'\xff\xd8\xff'
    if ext == 'gif':
        return data[:6] in (b'GIF87a', b'GIF89a')
    if ext == 'webp':
        return len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP'
    return False


# ==================== 登录验证码（防爆破） ====================

@auth_bp.route('/api/auth/captcha')
def get_captcha():
    """签发登录图形验证码：返回一次性 token 与 base64 PNG。
    答案存 MySQL 而非进程内存：gunicorn 多 worker 下签发与校验可能落在不同进程。"""
    code = ''.join(secrets.choice(CAPTCHA_CHARS) for _ in range(4))
    token = secrets.token_hex(16)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 顺带清理过期验证码（表很小，开销可忽略）
        cursor.execute("DELETE FROM login_captcha WHERE created_at < DATE_SUB(NOW(), INTERVAL 10 MINUTE)")
        cursor.execute("INSERT INTO login_captcha (token, code) VALUES (%s,%s)", (token, code))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    buf = ImageCaptcha(width=124, height=44).generate(code)
    return jsonify({'success': True, 'token': token,
                    'image': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()})


def _check_captcha(data):
    """校验并消费图片验证码。通过返回 None，否则返回错误消息。
    一次性使用：无论码对错，token 都被消费，防止对同一张图反复试错。"""
    token = (data.get('captcha_token') or '').strip()
    code = (data.get('captcha_code') or '').strip().upper()
    if not token or not code:
        return '请输入图片验证码'
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 原子消费：码对且未过期才删得掉，比对放在删除条件里，避免「先查后删」的并发竞态
        cursor.execute(
            "DELETE FROM login_captcha WHERE token=%s AND code=%s AND created_at > DATE_SUB(NOW(), INTERVAL 5 MINUTE)",
            (token, code))
        if cursor.rowcount == 1:
            conn.commit()
            return None
        conn.rollback()
        # 删不中：区分过期/码错/不存在，并把残留 token 清掉
        cursor.execute("SELECT TIMESTAMPDIFF(SECOND, created_at, NOW()) AS age FROM login_captcha WHERE token=%s",
                       (token,))
        row = cursor.fetchone()
        cursor.execute("DELETE FROM login_captcha WHERE token=%s", (token,))
        conn.commit()
        if row and (row['age'] is None or row['age'] > 300):
            return '验证码已过期，请刷新后重试'
        if row:
            return '验证码错误，请重新输入'
        return '验证码已失效，请刷新后重试'
    finally:
        cursor.close()
        conn.close()


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    ip = _client_ip()
    if _is_login_blocked(ip):
        return jsonify({'success': False, 'message': '登录失败次数过多，请 10 分钟后再试'}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    user_type = data.get('user_type', 'student')

    if user_type not in ROLE_TABLE:
        return jsonify({'success': False, 'message': '无效的用户类型'})
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})

    # 账号级限流：与 IP 级并行，防分布式换 IP 攻击同一账号（阈值更高）
    acct = _acct_key(user_type, username)
    if _is_account_blocked(acct):
        return jsonify({'success': False, 'message': '该账号登录失败次数过多，请 15 分钟后再试'}), 429

    # 先验验证码再验密码：爆破者必须先过验证码才碰得到密码校验
    captcha_error = _check_captcha(data)
    if captcha_error:
        log_auth_event('LOGIN_FAIL', user_type, username, False, f'验证码错误: {captcha_error}')
        return jsonify({'success': False, 'message': captcha_error})

    table, flag = ROLE_TABLE[user_type]
    flag_cond = 'is_frozen = 0' if table == 'student' else 'is_active = 1'
    user = query_one(f"SELECT * FROM {table} WHERE username = %s AND {flag_cond}", (username,))

    # 防用户名枚举：账号不存在/停用与密码错误返回同一文案，不向攻击者泄露账号有效性
    generic_err = '用户名或密码错误'
    if not user:
        _record_login_fail(ip)
        _record_account_fail(acct)
        log_auth_event('LOGIN_FAIL', user_type, username, False, '账号不存在或已停用')
        return jsonify({'success': False, 'message': generic_err})
    if not bcrypt.checkpw(password.encode('utf-8')[:72], user['password_hash'].encode('utf-8')):
        _record_login_fail(ip)
        _record_account_fail(acct)
        log_auth_event('LOGIN_FAIL', user_type, username, False, '密码错误')
        return jsonify({'success': False, 'message': generic_err})

    _clear_login_fail(ip)
    _clear_account_fail(acct)
    # 会话固定防护：登录成功后清空旧会话，重新建立身份信息
    session.clear()
    session['user_id'] = user['id']
    session['user_type'] = user_type
    session['username'] = user['username']
    session['real_name'] = user['real_name']
    session['pwd_fp'] = password_fingerprint(user['password_hash'])
    session['must_change_pwd'] = bool(user.get('must_change_pwd'))
    session['is_super'] = bool(user.get('is_super'))      # 管理员细分权限（超级管理员标记）
    session.permanent = True
    log_auth_event('LOGIN_OK', user_type, username, True)

    return jsonify({
        'success': True,
        'message': '登录成功',
        'must_change_pwd': bool(user.get('must_change_pwd')),
        'user': {'id': user['id'], 'username': user['username'], 'real_name': user['real_name'],
                 'user_type': user_type, 'is_super': bool(user.get('is_super'))}
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': '已退出登录'})


@auth_bp.route('/api/auth/me')
@login_required
def get_me():
    table = ROLE_TABLE[session['user_type']][0]
    avatar = query_one(f"SELECT avatar FROM {table} WHERE id=%s", (session['user_id'],))
    avatar_name = (avatar or {}).get('avatar')
    return jsonify({'success': True, 'user': {
        'id': session['user_id'], 'username': session['username'],
        'real_name': session['real_name'], 'user_type': session['user_type'],
        'is_super': bool(session.get('is_super')),
        'avatar': f'/uploads/avatar/{avatar_name}' if avatar_name else ''
    }})


@auth_bp.route('/api/avatar', methods=['POST'])
@login_required
def upload_avatar():
    """上传/修改当前登录用户自己的头像（各角色只能改自己）"""
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '请选择图片文件'})
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_AVATAR_EXT:
        return jsonify({'success': False, 'message': '仅支持 png/jpg/jpeg/gif/webp 格式'})
    # 限制大小（5MB）
    data = file.read()
    if len(data) > 5 * 1024 * 1024:
        return jsonify({'success': False, 'message': '图片大小不能超过 5MB'})
    # 校验文件真实内容与扩展名一致
    if not _valid_image_signature(data, ext):
        return jsonify({'success': False, 'message': '文件内容不是有效的图片'})

    table = ROLE_TABLE[session['user_type']][0]
    user_id = session['user_id']
    old = query_one(f"SELECT avatar FROM {table} WHERE id=%s", (user_id,))
    old_name = (old or {}).get('avatar')

    # 先落盘新头像，成功后再删除旧文件：避免写失败导致头像丢失且库里指向不存在的文件
    filename = f"{session['user_type']}_{user_id}_{int(datetime.now().timestamp())}.{ext}"
    try:
        with open(os.path.join(AVATAR_DIR, filename), 'wb') as f:
            f.write(data)
    except OSError as e:
        print(f'保存头像失败: {e}')
        return jsonify({'success': False, 'message': '头像保存失败，请稍后重试'})
    execute(f"UPDATE {table} SET avatar=%s WHERE id=%s", (filename, user_id))
    if old_name and old_name != filename:
        old_path = os.path.join(AVATAR_DIR, old_name)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    log_operation('UPDATE', table, user_id, '更新头像')
    return jsonify({'success': True, 'message': '头像已更新',
                    'avatar': f'/uploads/avatar/{filename}'})


@auth_bp.route('/uploads/avatar/<path:filename>')
@login_required
def avatar_file(filename):
    return send_from_directory(AVATAR_DIR, filename)


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    old_pw = data.get('old_password', '')
    new_pw = data.get('new_password', '')
    # 密码策略（长度/复杂度/弱口令）
    policy_error = validate_password(new_pw)
    if policy_error:
        return jsonify({'success': False, 'message': policy_error})
    if new_pw == old_pw:
        return jsonify({'success': False, 'message': '新密码不能与原密码相同'})

    table = ROLE_TABLE[session['user_type']][0]
    user = query_one(f"SELECT * FROM {table} WHERE id = %s", (session['user_id'],))
    if not user:
        session.clear()
        return jsonify({'success': False, 'message': '账号不存在，请重新登录'}), 401
    if not bcrypt.checkpw(old_pw.encode('utf-8')[:72], user['password_hash'].encode('utf-8')):
        return jsonify({'success': False, 'message': '原密码错误'})

    new_hash = bcrypt.hashpw(new_pw.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')
    try:
        execute(f"UPDATE {table} SET password_hash = %s, must_change_pwd = 0 WHERE id = %s",
                (new_hash, session['user_id']))
    except Exception as e:
        # 老库尚未升级：退回只改密码
        print(f'更新密码时附带列失败（可能未执行 upgrade_db.py）: {e}')
        execute(f"UPDATE {table} SET password_hash = %s WHERE id = %s", (new_hash, session['user_id']))
    # 轮换本机会话标识：其他设备上的旧会话在下次写操作时因指纹不一致而失效
    session['pwd_fp'] = password_fingerprint(new_hash)
    session.pop('must_change_pwd', None)
    log_operation('UPDATE', table, session['user_id'], '修改登录密码')
    return jsonify({'success': True, 'message': '密码修改成功'})
