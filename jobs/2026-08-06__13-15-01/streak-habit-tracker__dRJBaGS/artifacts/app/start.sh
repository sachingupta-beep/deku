#!/bin/bash

set -x

cd /app

# Install frontend dependencies and build
cd /app/frontend
npm install --legacy-peer-deps
npm run build

# Install backend dependencies
cd /app/backend
npm install

# Run seed/setup script
node setup.js

# Start the server detached
PORT="${APP_PUBLIC_PORT:-4173}"
setsid nohup node server.js > /tmp/app.log 2>&1 < /dev/null &

# Wait for server to be ready
echo "Waiting for server to start on port $PORT..."
for i in {1..30}; do
  if curl -s "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
    echo "Server is ready!"
    exit 0
  fi
  sleep 1
done

echo "Server failed to start"
cat /tmp/app.log
exit 1
