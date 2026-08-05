#!/bin/bash
# Golden reference solution for deku/smoke-tip-calculator.
#
# HELD OUT. Harbor uploads solution/ only when the oracle agent runs.
#
# This is a DEPLOYMENT script, not a build tutorial: it materializes the frozen
# reference app and starts it detached per the App Contract.

set -euo pipefail

APP_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/app"
WORKDIR=/app

if [ ! -f "${APP_SRC}/server.py" ]; then
  echo "solution/app is not populated - the oracle gate cannot pass." >&2
  exit 1
fi

: "${APP_PUBLIC_PORT:=4173}"

cp -a "${APP_SRC}/." "${WORKDIR}/"
cd "${WORKDIR}"

# Reserved by the App Contract.
mkdir -p .browser_screenshots .downloads

# Fully-detached start (App Contract): survives the session that launched it.
setsid nohup python3 server.py > /tmp/app.log 2>&1 < /dev/null &

for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:${APP_PUBLIC_PORT}/api/health" > /dev/null 2>&1; then
    echo "reference app up on ${APP_PUBLIC_PORT}"
    exit 0
  fi
  sleep 1
done

echo "reference app did not come up within 30s" >&2
tail -50 /tmp/app.log >&2 || true
exit 1
