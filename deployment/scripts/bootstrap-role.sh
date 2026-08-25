#!/usr/bin/env bash
# Prepare one laptop after the project has been copied to /opt/panopticon.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy the role file first, for example: cp deployment/env/command.env .env"
  exit 1
fi

set -a
. ./.env
set +a

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip wheel
.venv/bin/python -m pip install -r requirements.txt

echo "Bootstrap complete for role '${PANOPTICON_ROLE:-unset}'."
echo "Run deployment/scripts/start-role.sh when this laptop's role prerequisites are ready."
