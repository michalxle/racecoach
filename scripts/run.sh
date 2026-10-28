#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  printf 'Najpierw uruchom ./scripts/setup.sh\n' >&2
  exit 1
fi
npm --prefix frontend run build
exec .venv/bin/python -m racecoach "$@"
