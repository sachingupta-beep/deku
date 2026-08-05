#!/bin/bash
# The golden answer (PLAN.md 1.5, 3.2).
#
# HELD OUT. Harbor uploads solution/ only when the oracle agent runs. It must never
# reach a real agent, never enter training data, and never be published with the
# public slice -- it is a literal answer key.
#
# This is a DEPLOYMENT script, not a build tutorial: it materializes the frozen
# reference app and starts it per the App Contract, so `harbor run -a oracle`
# finishes in minutes rather than hours.
#
#   Gate: harbor run -p tasks/streak-habit-tracker -a oracle  ==>  reward == 1.0
#   Run it twice. A single pass does not rule out flakiness (PLAN.md 4.8).

set -euo pipefail

APP_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/app"
WORKDIR=/app

if [ ! -f "${APP_SRC}/frontend/package.json" ]; then
  echo "solution/app is not populated - the oracle gate cannot pass." >&2
  echo "Author the reference implementation into ${APP_SRC} before admitting" >&2
  echo "this task (PLAN.md 2.2 step 2)." >&2
  exit 1
fi

: "${APP_PUBLIC_PORT:=4173}"
: "${BACKEND_URL:?BACKEND_URL is not set}"

cp -a "${APP_SRC}/." "${WORKDIR}/"
cd "${WORKDIR}"

# Reserved by the App Contract.
mkdir -p .browser_screenshots .downloads

# --- backend adapter + seeds -----------------------------------------------
# The reference app talks to the Harbor-managed PocketBase at BACKEND_URL and
# uses SEED_USER_PASSWORD (surfaced by the harness) as the demo login secret.
if [ -f backend/requirements.txt ]; then
  python -m pip install --no-cache-dir -r backend/requirements.txt
fi
if [ -f backend/seed.py ]; then
  python backend/seed.py
fi
if [ -f backend/main.py ]; then
  (cd backend && nohup python main.py > /tmp/backend.log 2>&1 &)
fi

# --- frontend: production build behind a preview server, never a dev server --
(cd frontend && npm ci && npm run build)
(cd frontend && nohup npm run preview -- \
    --host 0.0.0.0 --port "${APP_PUBLIC_PORT}" \
    > /tmp/frontend.log 2>&1 &)

# Block until the contract's healthcheck target answers, so the oracle run does
# not race the verifier.
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:${APP_PUBLIC_PORT}/" > /dev/null 2>&1; then
    echo "reference app up on ${APP_PUBLIC_PORT}"
    exit 0
  fi
  sleep 2
done

echo "reference app did not come up within 120s" >&2
tail -50 /tmp/backend.log /tmp/frontend.log >&2 || true
exit 1
