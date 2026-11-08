#!/usr/bin/env bash
# 教务管理系统 - Linux 生产启动脚本
# 用法：先完成初始化，再运行本脚本
set -e

cd "$(dirname "$0")"

# 1. 加载环境变量（若存在 .env）
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# 2. 创建虚拟环境（首次）
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 3. 安装依赖（首次或 requirements 变更时执行，避免每次启动都联网装包）
REQ_HASH=$(cat requirements.txt requirements-prod.txt | sha1sum | cut -d' ' -f1)
if [ ! -f .deps_hash ] || [ "$(cat .deps_hash)" != "$REQ_HASH" ]; then
    pip install -r requirements.txt -r requirements-prod.txt
    echo "$REQ_HASH" > .deps_hash
fi

# 4. 初始化数据库（首次，会清空并写入演示数据；已有数据请勿重复运行）
#    --yes：脚本内已有 .db_initialized 标记，此处显式确认无需交互
if [ ! -f .db_initialized ]; then
    python init_db.py --yes
    touch .db_initialized
fi

# 5. 创建日志目录
mkdir -p logs

# 6. 启动 gunicorn（生产）
exec gunicorn -c gunicorn.conf.py wsgi:app
