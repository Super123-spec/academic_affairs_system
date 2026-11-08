#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教务管理系统后端入口
角色：student 学生 / teacher 教师 / admin 教务管理员

结构：
- core.py     基础设施（数据库工具、装饰器、通用函数）
- auth.py     认证与头像蓝图
- common.py   公共数据蓝图
- student.py  学生端蓝图
- teacher.py  教师端蓝图
- admin.py    管理端蓝图
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, jsonify, send_from_directory, request, redirect, session
from flask_cors import CORS
from flask_session import Session

from config import Config
from core import BASE_DIR, query_one, CURRENT_SEMESTER
from auth import auth_bp
from common import common_bp
from student import student_bp
from teacher import teacher_bp
from admin import admin_bp


def _read_version():
    """读取 VERSION 文件（便于发布追踪）；缺失时返回 dev"""
    try:
        with open(os.path.join(BASE_DIR, 'VERSION'), encoding='utf-8') as f:
            return f.read().strip() or 'dev'
    except OSError:
        return 'dev'


APP_VERSION = _read_version()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config.from_object(Config)
app.config['APP_VERSION'] = APP_VERSION
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# 上传/请求体大小限制（防超大文件拖垮服务），头像单文件 5MB 内，导入文件 10MB 内
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
# HTTPS 部署时通过环境变量开启 Secure 标志（HTTP 下开启会导致 cookie 无法传输）
if os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes'):
    app.config['SESSION_COOKIE_SECURE'] = True
# 强制跳转 HTTPS（仅当确认已具备证书/反代时开启，避免自锁）
_FORCE_HTTPS = os.environ.get('FORCE_HTTPS', '').lower() in ('1', 'true', 'yes')

# 服务端会话：会话数据存服务器（filesystem/redis），Cookie 只留 session_id
Session(app)

# CORS：默认不开启（前后端同源部署无需跨域）；仅当显式配置 ALLOWED_ORIGINS 时按白名单开放
_cors_origins = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', '').split(',') if o.strip()]
if _cors_origins:
    CORS(app, supports_credentials=True, origins=_cors_origins)

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(common_bp)
app.register_blueprint(student_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(admin_bp)


# ==================== 安全中间件 ====================

# 无需 CSRF 令牌的路径：登录前还没有会话，验证码是纯 GET 资源
_CSRF_EXEMPT = {'/api/auth/captcha'}
_UNSAFE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')


@app.before_request
def _force_https_redirect():
    """可选：生产环境强制 HTTPS（FORCE_HTTPS=1 时生效）"""
    if not _FORCE_HTTPS:
        return None
    if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
        return None
    # 301 会让浏览器把 POST 改成 GET 并丢失请求体，写操作必须用 308（保持方法与请求体）
    code = 301 if request.method in ('GET', 'HEAD') else 308
    return redirect(request.url.replace('http://', 'https://', 1), code=code)


@app.before_request
def _csrf_protect():
    """CSRF 防护（双提交令牌）：写操作必须携带与 Cookie 一致的 X-CSRF-Token 头。

    与 Cookie 的 SameSite=Lax 形成纵深防御：恶意站点无法读取本站 Cookie，
    也就无法伪造该请求头。
    """
    if request.method not in _UNSAFE_METHODS:
        return None
    if request.path in _CSRF_EXEMPT:
        return None
    expected = session.get('csrf_token')
    sent = request.headers.get('X-CSRF-Token', '')
    if not expected or not sent or not secrets.compare_digest(str(expected), str(sent)):
        return jsonify({'success': False,
                        'message': '安全校验失败（CSRF），请刷新页面后重试'}), 403
    return None


@app.after_request
def _security_headers(resp):
    """统一注入安全响应头、CSRF Cookie 与敏感接口禁缓存标记"""
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')          # 防点击劫持
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    resp.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
    # CSP：页面已外置全部内联脚本、内联事件改为 data-* 委托，
    # 故 script-src 可收紧为 'self'（移除 unsafe-inline），彻底阻断内联脚本注入。
    # style-src 仍保留 unsafe-inline：内联 style 属性分布极广，且 CSS 注入风险远低于脚本。
    resp.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
    if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
        resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    # 接口与健康检查禁止缓存，避免敏感数据被 CDN/代理缓存
    if request.path.startswith('/api/') or request.path == '/health':
        resp.headers.setdefault('Cache-Control', 'no-store, no-cache, must-revalidate, private')
        resp.headers.setdefault('Pragma', 'no-cache')
    # 双提交 CSRF 令牌：写入非 HttpOnly Cookie 供前端 JS 读取
    if not request.path.startswith(('/static/', '/uploads/')) and request.endpoint != 'static':
        token = session.get('csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['csrf_token'] = token
        if request.cookies.get('csrf_token') != token:
            resp.set_cookie('csrf_token', token, max_age=7 * 24 * 3600, path='/',
                            samesite='Lax', httponly=False,
                            secure=bool(app.config.get('SESSION_COOKIE_SECURE')))
    return resp


# ==================== 健康检查 ====================

@app.route('/favicon.ico')
def favicon():
    """返回空 favicon，避免浏览器请求站点图标产生 404 噪音"""
    return '', 204


@app.route('/health')
def health():
    """供负载均衡/监控探活：数据库不可用时返回 503"""
    db_ok = True
    try:
        query_one('SELECT 1 AS ok')
    except Exception as e:
        db_ok = False
        print(f'健康检查数据库不可用: {e}')
    payload = {
        'status': 'ok' if db_ok else 'degraded',
        'db': 'ok' if db_ok else 'error',
        'version': app.config['APP_VERSION'],
        'semester': CURRENT_SEMESTER,
    }
    return jsonify(payload), (200 if db_ok else 503)


# ==================== 页面路由 ====================

@app.route('/')
def index():
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'login.html')


@app.route('/student/<path:filename>')
def student_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'templates', 'student'), filename)


@app.route('/teacher/<path:filename>')
def teacher_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'templates', 'teacher'), filename)


@app.route('/admin/<path:filename>')
def admin_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'templates', 'admin'), filename)


@app.route('/css/<path:filename>')
def css_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'css'), filename)


@app.route('/js/<path:filename>')
def js_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'js'), filename)


# ==================== 错误处理 ====================

@app.errorhandler(413)
def too_large(e):
    return jsonify({'success': False, 'message': '上传文件过大'}), 413


@app.errorhandler(500)
def internal_error(e):
    # 记录异常便于排查，同时返回统一 JSON，避免暴露 HTML 堆栈
    app.logger.error('服务器内部错误: %s', e)
    return jsonify({'success': False, 'message': '服务器内部错误，请稍后重试'}), 500


@app.errorhandler(400)
def bad_request(e):
    # 请求体格式错误（如畸形 JSON）：返回 JSON，避免前端 res.json() 解析 HTML 失败
    return jsonify({'success': False, 'message': '请求格式错误'}), 400


@app.errorhandler(415)
def unsupported_media_type(e):
    # 缺少 application/json 的 Content-Type：同样返回 JSON 契约
    return jsonify({'success': False, 'message': '不支持的请求内容类型，请使用 application/json'}), 415


@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'message': '资源不存在'}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'success': False, 'message': '请求方法不允许'}), 405


if __name__ == '__main__':
    # debug 默认关闭（生产安全）；本地开发如需热重载，用环境变量 FLASK_DEBUG=1 开启
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=5000, debug=debug)
