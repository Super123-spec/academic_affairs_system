# -*- coding: utf-8 -*-
"""
生产 WSGI 入口（gunicorn 等 WSGI 服务器使用）

启动示例：
    gunicorn -c gunicorn.conf.py wsgi:app

或直接：
    gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
"""
from app import app

if __name__ == '__main__':
    app.run()
