#!/usr/bin/env bash
# Run SCEP server. From repo root: bash run_scep.sh
set -e
cd "$(dirname "$0")"
export PYTHONPATH=.
python -m uvicorn scep.app.main:app --reload --host 0.0.0.0 --port 8002
