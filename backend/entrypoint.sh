#!/bin/sh
set -e

case "$1" in
  api)
    echo "Running database migrations..."
    alembic upgrade head
    echo "Starting API server..."
    exec uvicorn fetch.main:app --host 0.0.0.0 --port 8000
    ;;
  *)
    exec "$@"
    ;;
esac
