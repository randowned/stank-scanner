#!/bin/sh
# Start as root so we can fix ownership of the mounted volume (Railway
# mounts volumes as root), then drop to the stankbot user.
set -e

# uvicorn and alembic write INFO logs to stderr by default; Railway
# colors anything on fd2 red. Merge stderr into stdout so routine
# startup/request logs aren't mis-flagged as errors.
exec 2>&1

echo "[entrypoint] chown /data"
chown -R stankbot:stankbot /data 2>/dev/null || true

# The Dockerfile exposes port 8000 and Railway's public domain is
# configured to target 8000. Don't auto-switch to $PORT — Railway's
# injected PORT doesn't always match the routed port and caused
# "connection refused" 502s when uvicorn bound to a mismatched port.
export WEB_BIND="0.0.0.0:8000"
echo "[entrypoint] WEB_BIND=$WEB_BIND"

echo "[entrypoint] alembic upgrade head"
cd /app
gosu stankbot alembic upgrade head

echo "[entrypoint] exec $*"
exec gosu stankbot "$@"
