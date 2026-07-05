#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.
if [ -d .venv ]; then source .venv/bin/activate; fi
python -m services.scanner_service.daemon
