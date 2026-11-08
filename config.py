# config.py
import os
import secrets


def _load_env_file():
    """自动加载项目根目录的 .env 文件（若存在）。
    只填充尚未设置的环境变量，不覆盖已有值（环境变量优先级更高）。
    这样 `python app.py`、`init_db.py` 无需手动 export 也能读到配置。"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_env_file()


# 已知的占位/示例密钥：一旦被当作真实密钥使用，会话签名可被预测、伪造
_PLACEHOLDER_SECRETS = (
    '请改成随机字符串', '请改成', 'changeme', 'change-me', 'your-secret', 'secret',
    'abc123def456ghi789jkl012mno345pq',
)


def _load_secret_key():
    """会话密钥：优先环境变量，其次本地密钥文件，最后生成并持久化。
    保证重启后密钥稳定（session 不失效），且不硬编码在源码中。

    安全性：环境变量里若还是模板占位符（如"请改成随机字符串"）或明显过短，
    直接忽略并改用自动生成的随机密钥，避免上线后使用可预测的签名密钥。
    """
    env = (os.environ.get("SECRET_KEY") or '').strip()
    if env:
        low = env.lower()
        is_placeholder = any(p in env for p in _PLACEHOLDER_SECRETS) or any(p in low for p in _PLACEHOLDER_SECRETS)
        if not is_placeholder and len(env) >= 16:
            return env
        print('[警告] SECRET_KEY 仍是占位符或过短（<16 位），已忽略并改用自动生成的随机密钥。'
              ' 请执行 python -c "import secrets;print(secrets.token_hex(32))" 生成后写入 .env')
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    try:
        with open(key_file, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32)
    with open(key_file, "w", encoding="utf-8") as f:
        f.write(key)
    return key


class Config:
    # MySQL 数据库配置（可通过环境变量覆盖，便于部署）
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "1234")
    MYSQL_DB = os.environ.get("MYSQL_DB", "edu_admin")

    # 会话密钥：从环境变量或本地 .secret_key 文件加载（生产环境务必通过环境变量注入）
    SECRET_KEY = _load_secret_key()

    # ==================== 账号初始密码 ====================
    # 管理员新建/重置学生、教师账号时使用的初始密码（可用环境变量覆盖）。
    # 业务约定：初始密码允许使用弱口令（默认 123456），交付本人后可直接登录；
    # 用户自行修改密码时仍走 core.validate_password 的强密码策略。
    DEFAULT_INITIAL_PASSWORD = (os.environ.get("DEFAULT_INITIAL_PASSWORD") or "123456").strip() or "123456"

    # ==================== 服务端会话（Flask-Session） ====================
    # 会话数据不再写入 Cookie（Cookie 里只留随机 session_id），从根上避免
    # 会话内容被第三方读取（签名只能防篡改、不能防偷看）。
    # 默认 filesystem（零依赖、单机够用）；多机/分布式部署时改 SESSION_TYPE=redis 即可。
    SESSION_TYPE = os.environ.get("SESSION_TYPE", "filesystem")
    SESSION_FILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_session")
    SESSION_FILE_THRESHOLD = 1000          # 会话文件数量上限，超限自动清理最旧的
    SESSION_PERMANENT = True               # 与登录时 session.permanent=True 一致
    SESSION_USE_SIGNER = True              # session_id Cookie 也加签名，防伪造


# ==================== 数据库弱口令启动守卫 ====================
# 部署到远程数据库却仍用默认/空口令是最常见的"裸奔"事故源：
# 一旦 MYSQL_HOST 指向非本机地址且口令为弱口令，直接拒绝启动，避免带病上线。
_WEAK_DB_PASSWORDS = {'1234', '123456', 'root', 'password', 'passw0rd', ''}


def _is_local_host(host):
    return host in ('localhost', '127.0.0.1', '::1') or host.startswith('127.')


if Config.MYSQL_PASSWORD in _WEAK_DB_PASSWORDS:
    if not _is_local_host(Config.MYSQL_HOST):
        raise RuntimeError(
            f"[安全] 拒绝启动：数据库 {Config.MYSQL_HOST} 正在使用弱口令，"
            f"请在 .env 中设置强 MYSQL_PASSWORD 后再启动。")
    print("[警告] 正在使用默认数据库口令，仅限本机开发；"
          "部署到远程数据库前必须修改 MYSQL_PASSWORD。")
