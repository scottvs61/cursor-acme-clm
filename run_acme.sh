#!/usr/bin/env bash
# Run ACME server. From repo root: ./run_acme.sh
set -e
cd "$(dirname "$0")"
export PYTHONPATH=.
python -m uvicorn acme.app.main:app --reload --host 0.0.0.0 --port 8000
