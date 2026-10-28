#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  if command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
  else
    python3 -m venv .venv
  fi
fi
.venv/bin/python -c 'import sys; assert sys.version_info >= (3,11), "Wymagany Python 3.11+; zalecany 3.12"'
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e ./backend -e ./agent
npm --prefix frontend ci
npm --prefix frontend run build
printf '\nGotowe. Uruchom: ./scripts/run.sh --demo\n'
