#!/usr/bin/env bash
# Purpose: Linux/macOS 一键打包并上传至服务器 /tmp，用于后续服务器端一键部署。
# Usage:   bash scripts/linux_pack_upload.sh [SERVER] [REMOTE_TMP]
# Example: bash scripts/linux_pack_upload.sh ubuntu@106.52.47.82 /tmp

set -euo pipefail

SERVER="${1:-ubuntu@106.52.47.82}"
REMOTE_TMP="${2:-/tmp}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
TS="$(date +%Y%m%d%H%M)"
ARCHIVE_NAME="project_${TS}.tgz"
ARCHIVE_PATH="${PROJECT_ROOT}/${ARCHIVE_NAME}"

cd "${PROJECT_ROOT}"
echo "[+] Packing project at ${PROJECT_ROOT}"
# 归档：排除数据/缓存/虚拟环境/日志等
 tar -czf "${ARCHIVE_PATH}" \
  --exclude='./data' \
  --exclude='./logs' \
  --exclude='./venv' \
  --exclude='./.git' \
  --exclude='./decisions' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  .

ls -lh "${ARCHIVE_PATH}"

echo "[+] Uploading to ${SERVER}:${REMOTE_TMP}/"
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${ARCHIVE_PATH}" "${SERVER}:${REMOTE_TMP}/"

echo "[✓] Upload completed: ${ARCHIVE_NAME} -> ${SERVER}:${REMOTE_TMP}/"
echo "[→] Next on server: sudo bash /opt/ai-etf-trader/deploy/jan2_deploy.sh ${REMOTE_TMP}/${ARCHIVE_NAME}"
