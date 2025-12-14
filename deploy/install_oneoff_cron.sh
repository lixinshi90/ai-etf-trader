#!/usr/bin/env bash
# Install a one-off cron job to run deployment on Jan 2 at 00:00 (server local time)
# Usage: sudo bash /opt/ai-etf-trader/deploy/install_oneoff_cron.sh [HH MM DAY MONTH]
# Default: 00 0 2 1 (Jan 2, 00:00)

set -euo pipefail

HH="${1:-0}"
MM="${2:-0}"
DAY="${3:-2}"
MONTH="${4:-1}"

DEPLOY_SCRIPT="/opt/ai-etf-trader/deploy/jan2_deploy.sh"
ARCHIVE_GLOB="/tmp/project_*.tgz"

if [[ ! -x "${DEPLOY_SCRIPT}" ]]; then
  echo "[ERR] ${DEPLOY_SCRIPT} not found or not executable"
  exit 1
fi

LINE="${MM} ${HH} ${DAY} ${MONTH} * root /usr/bin/bash ${DEPLOY_SCRIPT} \$(ls -1t ${ARCHIVE_GLOB} 2>/dev/null | head -1) >> /opt/ai-etf-trader/logs/cron_deploy.log 2>&1"

CRON_FILE="/etc/cron.d/ai-etf-oneoff"
echo "[+] Writing ${CRON_FILE}"
echo "${LINE}" > "${CRON_FILE}"
chmod 644 "${CRON_FILE}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart cron || systemctl restart crond || true
fi

echo "[✓] One-off cron installed: ${LINE}"

