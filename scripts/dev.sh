#!/usr/bin/env bash
# One-time local setup, then run the whole product on http://127.0.0.1:3101 (no AWS needed).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements-dev.txt
fi
(cd web && npm install --no-audit --no-fund && npm run build)
(cd services/api && npm install --no-audit --no-fund)

if ! ls data/*.timing.json >/dev/null 2>&1; then
  .venv/bin/python scripts/build_samples.py --skip-mos
fi
exec node services/api/server.js
