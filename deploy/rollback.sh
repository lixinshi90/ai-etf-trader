#!/usr/bin/env bash
# One-click rollback script
# Usage: sudo bash /opt/ai-etf-trader/deploy/rollback.sh /opt/ai-etf-trader.bak_YYYYMMDDHHMMSS

set -euo pipefail

TARGET_DIR="/opt/ai-etf-trader"
BACKUP_DIR="${1:-}"
SERVICE_NAME="ai-etf-web"
RUN_USER="aiuser"
RUN_GROUP="aiuser"

if [[ -z "${BACKUP_DIR}" || ! -d "${BACKUP_DIR}" ]]; then
  echo "[ERR] Backup directory not found. Usage: rollback.sh /opt/ai-etf-trader.bak_YYYYMMDDHHMMSS"
  exit 1
fi

echo "[+] Stopping service: ${SERVICE_NAME}"
systemctl stop "${SERVICE_NAME}" || true

echo "[+] Restoring backup: ${BACKUP_DIR} -> ${TARGET_DIR}"
rsync -a --delete "${BACKUP_DIR}/" "${TARGET_DIR}/"

chown -R "${RUN_USER}:${RUN_GROUP}" "${TARGET_DIR}"

echo "[+] Restarting service: ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 2
if command -v curl >/dev/null 2>&1; then
  curl -s http://127.0.0.1/health || true
fi

echo "[✓] Rollback completed."
