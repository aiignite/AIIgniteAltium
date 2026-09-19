#!/usr/bin/env bash
# AIDriveAltium 一键本地启动（PostgreSQL 需已安装并运行）
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"

echo "== AIDriveAltium 启动 =="

# 1. Python 虚拟环境
if [ ! -x "$PY" ]; then
  echo "-- 创建 venv 并安装依赖…"
  python3 -m venv "$ROOT/.venv"
  "$PY" -m pip install -q -r "$ROOT/backend/requirements.txt"
fi

# 2. 数据库连接检查（backend/.env: DATABASE_URL）
echo "-- 检查数据库连接…"
cd "$ROOT/backend"
if ! "$PY" - <<'EOF'
import asyncio, os, sys
sys.path.insert(0, '.')
from app.config import settings
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("数据库连接 OK:", settings.database_url.split("@")[-1])
    finally:
        await engine.dispose()

asyncio.run(main())
EOF
then
  echo "!! 数据库连接失败。请确认 PostgreSQL 已运行并在 backend/.env 配置 DATABASE_URL"
  echo "   参考安装: brew install postgresql@17 && brew services start postgresql@17"
  echo "   建库:     createdb -U <user> aidrive_altium"
  exit 1
fi

# 3. 停止旧进程
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

# 4. 启动后端 (3345)
echo "-- 启动后端 http://localhost:3345 …"
nohup "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 3345 > /tmp/aidrive_backend.log 2>&1 &

# 5. 启动前端 (3340)
echo "-- 启动前端 http://localhost:3340 …"
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "   安装前端依赖…"
  npm install --silent
fi
nohup npm run dev > /tmp/aidrive_frontend.log 2>&1 &

sleep 5
echo
echo "== 启动完成 =="
echo "  前端:   http://localhost:3340"
echo "  后端API: http://localhost:3345/docs"
echo "  默认管理员: admin@example.com / admin123456（见 backend/.env）"
echo "  日志: /tmp/aidrive_backend.log /tmp/aidrive_frontend.log"
