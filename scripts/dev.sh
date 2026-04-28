#!/bin/bash
# StankBot one-command dev startup (macOS/Linux)
# Starts the Python backend in ENV=dev-mock and the Vite frontend dev server.
# Uses health-check polling instead of a blind sleep for reliable startup.

set -e

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
pid_file="$repo_root/.stankbot_backend.pid"
export ENV=dev-mock
export PYTHONPATH="$repo_root/src"

cleanup() {
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "Shutting down backend (PID $pid)..."
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    fi
}
trap cleanup EXIT

echo "Starting StankBot in dev-mock mode..."

# Start backend
python -m stankbot &
backend_pid=$!
echo "$backend_pid" > "$pid_file"
echo "Backend PID: $backend_pid"

# Wait for backend to be ready via health check
echo -n "Waiting for backend..."
for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
        echo " ready."
        break
    fi
    if ! kill -0 "$backend_pid" 2>/dev/null; then
        echo ""
        echo "ERROR: Backend process died during startup."
        exit 1
    fi
    sleep 0.5
done

if ! curl -sf http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
    echo ""
    echo "ERROR: Backend did not become ready within 30s."
    exit 1
fi

# Start frontend
cd "$repo_root/src/stankbot/web/frontend"
npm run dev
