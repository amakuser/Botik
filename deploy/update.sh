#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-/opt/Botik}"
BRANCH="${2:-master}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$REPO_DIR"

echo "[update] fetching branch $BRANCH"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [ ! -d ".venv" ]; then
  echo "[update] creating virtualenv"
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[update] running smoke tests"
pytest -q tests/test_micro_spread_logic.py tests/test_risk_manager_limits.py tests/test_spread_scanner.py tests/test_position_risk.py

if [ "${RUN_PREFLIGHT:-1}" = "1" ]; then
  echo "[update] running preflight checks"
  python tools/preflight.py --config config.yaml --timeout-sec 15
fi

echo "[update] restarting services"
systemctl restart botik-trading.service
systemctl restart botik-ml.service

echo "[update] done"
