#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-/opt/Botik}"
SYSTEMD_DIR="/etc/systemd/system"

if [ ! -d "$REPO_DIR/deploy/systemd" ]; then
  echo "[install] missing directory: $REPO_DIR/deploy/systemd"
  exit 1
fi

install -m 0644 "$REPO_DIR/deploy/systemd/botik-trading.service" "$SYSTEMD_DIR/botik-trading.service"
install -m 0644 "$REPO_DIR/deploy/systemd/botik-ml.service" "$SYSTEMD_DIR/botik-ml.service"

systemctl daemon-reload
systemctl enable botik-trading.service
systemctl enable botik-ml.service

echo "[install] systemd units installed and enabled"
echo "[install] start services:"
echo "  systemctl start botik-trading.service"
echo "  systemctl start botik-ml.service"
