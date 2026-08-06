#!/bin/bash
# Deku Calculator startup script

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Get port from environment or default
PORT="${APP_PUBLIC_PORT:-4173}"

echo "Starting Deku Calculator on port $PORT..."

# Kill any existing server on this port by finding the PID
for pid in $(cat /proc/*/cmdline 2>/dev/null | tr '\0' '\n' | grep -l "server.py" 2>/dev/null | cut -d'/' -f3 2>/dev/null); do
    kill -9 "$pid" 2>/dev/null
done
sleep 1

# Start the server detached
setsid nohup python3 "$APP_DIR/server.py" > /tmp/app.log 2>&1 < /dev/null &

# Wait for the server to be ready
for i in $(seq 1 30); do
    if curl -s "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
        echo "Server is ready!"
        exit 0
    fi
    sleep 0.5
done

echo "ERROR: Server failed to start within 15 seconds"
cat /tmp/app.log
exit 1
