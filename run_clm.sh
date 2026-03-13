#!/usr/bin/env bash
# Run CLM API (and serve UI). From repo root: ./run_clm.sh
set -e
cd "$(dirname "$0")"
export PYTHONPATH=.
python -m uvicorn clm.app.main:app --reload --host 0.0.0.0 --port 8001
