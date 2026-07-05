#!/usr/bin/env bash
# Start PostgreSQL + Redis via Docker and configure the app to use them
set -e
cd "$(dirname "$0")/.."

if ! docker info > /dev/null 2>&1; then
  echo "Docker is not running. Please start Docker Desktop and retry."
  exit 1
fi

echo "Starting PostgreSQL + Redis..."
docker compose up -d

echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U fxnav -d fxnavigators > /dev/null 2>&1; then
    echo "PostgreSQL is ready."
    break
  fi
  sleep 2
done

if [ ! -f .env ]; then
  cp .env.example .env
fi

echo ""
echo "To use PostgreSQL, add to .env:"
echo "  USE_POSTGRES=true"
echo "  DATABASE_URL=postgresql://fxnav:fxnav_dev@localhost:5432/fxnavigators"
echo ""
echo "Then install psycopg2: pip install psycopg2-binary"
echo "And restart the API."
