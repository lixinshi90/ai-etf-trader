#!/usr/bin/env bash
set -euo pipefail

# AI ETF Trader - Ubuntu 22.04 one-click deploy (venv + gunicorn + nginx + systemd)
# Usage:
#   sudo bash deploy_ubuntu22.sh
# Notes:
#   - Adjust DOMAIN, APP_USER, APP_DIR as needed.

DOMAIN="_"                 # replace with your domain or leave _ for any
APP_USER="aiuser"          # non-root user to run the service
APP_DIR="/opt/ai-etf-trader"  # project root directory
PYTHON_BIN="python3.11"    # use 3.11 as in environment.yml

# 0) Basic packages
apt-get update
apt-get install -y software-properties-common git curl unzip sqlite3 nginx

# 1) Python & venv
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y ${PYTHON_BIN} ${PYTHON_BIN}-venv ${PYTHON_BIN}-distutils

# 2) Create user and directories
if ! id -u ${APP_USER} >/dev/null 2>&1; then
  useradd -m -s /bin/bash ${APP_USER}
fi
mkdir -p ${APP_DIR}
chown -R ${APP_USER}:${APP_USER} ${APP_DIR}

# 3) Copy project into APP_DIR (assumes you rsync/scp beforehand)
#    If running inside server already in APP_DIR, skip this step.
#    Example: rsync -av ./ ${USER}@${SERVER}:${APP_DIR}/

# 4) Create venv and install requirements
cd ${APP_DIR}
if [ ! -d venv ]; then
  ${PYTHON_BIN} -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip wheel setuptools
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

# 5) .env placeholder (edit later)
if [ ! -f .env ]; then
  cat > .env <<EOF
# Model provider
OPENAI_API_KEY=replace_me
BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL_NAME=glm-4-air
# Task configs
ETF_LIST=510050,159915,510300
SCHEDULE_TIME=17:00
DAILY_AI_CALLS_LIMIT=3
# Robustness
TIMEOUT_SECONDS=120
MAX_RETRIES=5
FALLBACK_MODELS=glm-4-air
EOF
  echo "Created .env (please edit keys)"
fi

# 6) Systemd service for gunicorn
cat > /etc/systemd/system/ai-etf-web.service <<EOF
[Unit]
Description=AI ETF Trader Web (gunicorn)
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/gunicorn -b 127.0.0.1:5000 -w 2 src.web_app:app
User=${APP_USER}
Group=${APP_USER}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ai-etf-web
systemctl status ai-etf-web --no-pager || true

# 7) Nginx reverse proxy
cat > /etc/nginx/conf.d/ai-etf.conf <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
EOF

nginx -t && systemctl reload nginx

# 8) Timezone
timedatectl set-timezone Asia/Shanghai || true

# 9) Health check
curl -fsS http://127.0.0.1/health | grep -q "ok" && echo "Health OK" || echo "Health check failed (wait a few seconds and retry)"

echo "Deployment finished. Visit: http://<your-ip>/"

