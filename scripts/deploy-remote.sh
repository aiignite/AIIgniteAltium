#!/usr/bin/env bash
# AIDriveAltium 远程部署：rsync + SSH + docker compose（沿 AIDriveAll deploy-remote.sh 约定）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONFIG="${AIDRIVEALTIUM_DEPLOY_CONFIG:-$ROOT/scripts/deploy.env}"
if [[ -f "$CONFIG" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG"
  # SSH 密码可复用门户的 deploy.env
  if [[ -z "${AIDRIVEALTIUM_SSH_PASS:-}" && -f "$ROOT/../AIDriveAll/scripts/deploy.env" ]]; then
    AIDRIVEALTIUM_SSH_PASS="$(grep -E '^AIDRIVEALL_SSH_PASS=' "$ROOT/../AIDriveAll/scripts/deploy.env" | cut -d= -f2- || true)"
  fi
fi

HOST="${AIDRIVEALTIUM_DEPLOY_HOST:?请设置 AIDRIVEALTIUM_DEPLOY_HOST（见 scripts/deploy.env.example）}"
USER="${AIDRIVEALTIUM_DEPLOY_USER:-ubuntu}"
REMOTE_PATH="${AIDRIVEALTIUM_DEPLOY_PATH:-/home/ubuntu/AIDriveAltium}"

ssh_wrap() {
  if [[ -n "${AIDRIVEALTIUM_SSH_PASS:-}" ]] && command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$AIDRIVEALTIUM_SSH_PASS" ssh -o StrictHostKeyChecking=no "${USER}@${HOST}" "$@"
  else
    ssh -o StrictHostKeyChecking=no "${USER}@${HOST}" "$@"
  fi
}

rsync_ssh() {
  if [[ -n "${AIDRIVEALTIUM_SSH_PASS:-}" ]] && command -v sshpass >/dev/null 2>&1; then
    echo "sshpass -p '$AIDRIVEALTIUM_SSH_PASS' ssh -o StrictHostKeyChecking=no"
  else
    echo "ssh -o StrictHostKeyChecking=no"
  fi
}

echo "==> 目标: ${USER}@${HOST}:${REMOTE_PATH}"

echo "==> 同步代码..."
# mac 自带 openrsync 的 -e 参数有崩溃 bug：有免密钥时不传 -e；仅密码模式使用 -e
RSH_ARGS=""
if [[ -z "${SSH_KEY_READY:-}" && -n "${AIDRIVEALTIUM_SSH_PASS:-}" ]]; then
  RSH_ARGS="-e $(rsync_ssh)"
fi
rsync -avz $RSH_ARGS \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude '.venv-gw' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude 'frontend/dist' \
  --exclude 'backend/.env' \
  --exclude 'backend/data' \
  --exclude 'backend/.pytest_cache' \
  --exclude 'scripts/deploy.env' \
  --exclude 'gateway' \
  ./ "${USER}@${HOST}:${REMOTE_PATH}/"

echo "==> 服务器环境初始化（首次）..."
ssh_wrap "cd ${REMOTE_PATH} && if [ ! -f backend/.env ]; then cat > backend/.env <<'ENVEOF'
DATABASE_URL=postgresql+asyncpg://aidrive:aidrive_altium_dev@postgres:5432/aidrive_altium
SECRET_KEY=\$(head -c 24 /dev/urandom | base64)
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=admin123456
DATA_DIR=/data
ENVEOF
echo 'backend/.env created'; fi"

echo "==> 远程构建与启动（docker compose）..."
ssh_wrap "cd ${REMOTE_PATH} && chmod +x start.sh 2>/dev/null || true; docker compose up -d --build 2>&1 | tail -5"

echo "==> 健康检查..."
sleep 5
ssh_wrap "curl -s -m 8 http://127.0.0.1:3345/api/v1/health && echo && curl -s -o /dev/null -w 'frontend: %{http_code}\n' http://127.0.0.1:3340/altium/"

echo "== AIDriveAltium 服务器部署完成 =="
