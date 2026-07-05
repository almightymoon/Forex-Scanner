#!/usr/bin/env bash
# Start the FX Navigators API server
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.

if [ -d .venv ]; then
  source .venv/bin/activate
fi

if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "Installing API dependencies..."
  pip install -r apps/api/requirements.txt
fi

cd apps/api
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
