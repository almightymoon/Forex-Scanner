#!/usr/bin/env bash
# Start the FX Navigators data collector daemon
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -d .venv ]; then
  source .venv/bin/activate
fi

python3 -m services.data_collector.daemon
