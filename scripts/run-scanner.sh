#!/usr/bin/env bash
# Run the FX Navigators scanner pipeline (no API server needed)
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.

if [ -d .venv ]; then
  source .venv/bin/activate
fi

python3 -m services.scanner_service.pipeline
