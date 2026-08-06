#!/bin/bash
# Start script for Deku Calculator

set -o pipefail

APP_DIR="/app"
LOG_FILE="/tmp/app.log"

# Read port from environment, default to 4173
PORT="${APP_PUBLIC_PORT:-4173}"

echo "Starting Deku Calculator on port $PORT..."

# Kill any existing server on this port
pkill -f "python3 $APP_DIR/server.py" 2>/dev/null || true
sleep 1

# Start the server detached
cd "$APP_DIR"
setsid nohup python3 "$APP_DIR/server.py" > "$LOG_FILE" 2>&1 < /dev/null &

# Wait for server to be ready
MAX_WAIT=30
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
        echo "Server is ready on port $PORT"
        exit 0
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done

echo "ERROR: Server failed to start within $MAX_WAIT seconds"
echo "Log output:"
cat "$LOG_FILE"
exit 1
