# -*- coding: utf-8 -*-
"""gunicorn 生产配置"""
import multiprocessing
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 监听地址与端口
bind = "0.0.0.0:5000"

# worker 数量：CPU 核数 * 2 + 1（内存受限可减少）
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
threads = 2

# 请求超时
timeout = 60
graceful_timeout = 30
keepalive = 5

# ---- 日志（轮转，避免日志文件无限增长占满磁盘）----
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "generic": {
            "format": "[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S %z",
        },
        "access": {"format": "%(message)s"},
    },
    "handlers": {
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "error.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "generic",
        },
        "access_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "access.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "access",
        },
    },
    "loggers": {
        "gunicorn.error": {"handlers": ["error_file"], "level": "INFO", "propagate": False},
        "gunicorn.access": {"handlers": ["access_file"], "level": "INFO", "propagate": False},
    },
}
loglevel = "info"

# 仅信任本机反向代理（Nginx）传入的 X-Forwarded-For，防止客户端伪造来源 IP
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")

# 进程命名
proc_name = "edu_admin"

# 每个 worker 最大请求数（防内存泄漏，可选）
max_requests = 1000
max_requests_jitter = 50
