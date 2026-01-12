#!/usr/bin/env bash
# One-click deployment script for AI ETF Trader on server
# Usage: sudo bash /opt/ai-etf-trader/deploy/jan2_deploy.sh [/path/to/project_YYYYMMDDHHMM.tgz|.zip]
# If archive path is omitted, the script will pick the latest /tmp/project_*.tgz or .zip automatically.

set -euo pipefail

TARGET_DIR="/opt/ai-etf-trader"
SERVICE_NAME="ai-etf-web"
RUN_USER="aiuser"
RUN_GROUP="aiuser"

ARCHIVE_PATH="${1:-}"

pick_latest_archive() {
  local c
  c=$(ls -1t /tmp/project_*.tgz 2>/dev/null | head -1 || true)
  if [[ -z "$c" ]]; then
    c=$(ls -1t /tmp/project_*.zip 2>/dev/null | head -1 || true)
  fi
  echo "$c"
}

if [[ -z "${ARCHIVE_PATH}" ]]; then
  ARCHIVE_PATH="$(pick_latest_archive)"
fi

if [[ -z "${ARCHIVE_PATH}" || ! -f "${ARCHIVE_PATH}" ]]; then
  echo "[ERR] Archive not found. Provide path or upload as /tmp/project_*.tgz|.zip"
  exit 1
fi

echo "[+] Using archive: ${ARCHIVE_PATH}"

BACKUP_DIR="${TARGET_DIR}.bak_$(date +%Y%m%d%H%M%S)"
NEW_DIR="${TARGET_DIR}_new"

stop_service() {
  echo "[+] Stopping service: ${SERVICE_NAME}"
  systemctl stop "${SERVICE_NAME}" || true
}

start_service() {
  echo "[+] Restarting service: ${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"
}

health_check() {
  echo "[+] Health check: http://127.0.0.1/health"
  sleep 2
  if command -v curl >/dev/null 2>&1; then
    curl -sS --max-time 5 http://127.0.0.1/health | grep -qi "ok" && return 0 || return 1
  else
    echo "curl not installed, skipping"
    return 0
  fi
}

echo "[+] Backing up current deployment: ${TARGET_DIR} -> ${BACKUP_DIR}"
cp -a "${TARGET_DIR}" "${BACKUP_DIR}"

stop_service

echo "[+] Preparing new directory: ${NEW_DIR}"
rm -rf "${NEW_DIR}"
mkdir -p "${NEW_DIR}"

if [[ "${ARCHIVE_PATH}" == *.tgz ]] || [[ "${ARCHIVE_PATH}" == *.tar.gz ]]; then
  tar -xzf "${ARCHIVE_PATH}" -C "${NEW_DIR}"
elif [[ "${ARCHIVE_PATH}" == *.zip ]]; then
  unzip -q -o "${ARCHIVE_PATH}" -d "${NEW_DIR}"
else
  echo "[ERR] Unsupported archive format: ${ARCHIVE_PATH}"
  exit 1
fi

# Preserve environment and data/logs
echo "[+] Preserving .env, data/, logs/"
mkdir -p "${NEW_DIR}/data" "${NEW_DIR}/logs"
if [[ -f "${TARGET_DIR}/.env" ]]; then cp -f "${TARGET_DIR}/.env" "${NEW_DIR}/.env"; fi
if [[ -d "${TARGET_DIR}/data" ]]; then rsync -a "${TARGET_DIR}/data/" "${NEW_DIR}/data/"; fi
if [[ -d "${TARGET_DIR}/logs" ]]; then rsync -a "${TARGET_DIR}/logs/" "${NEW_DIR}/logs/"; fi

# Swap new content into place
echo "[+] Syncing new content into ${TARGET_DIR}"
rsync -a --delete "${NEW_DIR}/" "${TARGET_DIR}/"

# Dependencies (reuse venv if exists)
if [[ -x "${TARGET_DIR}/venv/bin/pip" && -f "${TARGET_DIR}/requirements.txt" ]]; then
  echo "[+] Installing requirements via existing venv"
  "${TARGET_DIR}/venv/bin/pip" install -r "${TARGET_DIR}/requirements.txt"
fi

# Ownership
echo "[+] Setting ownership: ${RUN_USER}:${RUN_GROUP}"
chown -R "${RUN_USER}:${RUN_GROUP}" "${TARGET_DIR}"

# Nginx test (optional)
if command -v nginx >/dev/null 2>&1; then
  echo "[+] Testing nginx config"
  nginx -t && systemctl reload nginx || echo "[WARN] nginx test failed or nginx reload skipped"
fi

start_service

if health_check; then
  echo "[✓] Deployment succeeded. Backup: ${BACKUP_DIR}"
else
  echo "[ERR] Health check failed. Consider rollback: sudo bash /opt/ai-etf-trader/deploy/rollback.sh ${BACKUP_DIR}"
  exit 1
fi

