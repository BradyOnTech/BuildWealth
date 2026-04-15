#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ORCHESTRATOR_DIR="$ROOT_DIR/services/orchestrator"

cd "$ORCHESTRATOR_DIR"
python3 -m pip install -e '.[dev]' >/dev/null
pytest -q \
  tests/test_storage_reliability_smoke.py \
  tests/test_backup_restore.py \
  tests/test_data_protection.py
