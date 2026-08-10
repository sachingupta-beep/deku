#!/bin/bash
# The golden answer for ethara/warehouse-allocation-ledger.
#
# HELD OUT. Harbor uploads this directory only when the oracle agent runs. It must
# never reach a real agent, never enter training data, and never be published with
# a public slice -- it is a literal answer key.
#
# This is a DEPLOYMENT script, not a build tutorial: it materialises the frozen
# reference application and starts it per the App Contract, so an oracle run
# finishes in minutes rather than hours.
#
#   Gate: harbor run -p <task> -a oracle  ==>  reward == 1.0, twice.
#
# D20 app-deferred mode: app/ carries no code yet. This script FAILS LOUDLY in
# that state on purpose. A stub that pretended to succeed would make the nop-agent
# gate meaningless, because a zero from a broken deploy and a zero from an agent
# that built nothing would look identical.

set -euo pipefail

APP_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/app"
WORKDIR=/app

if [ ! -f "${APP_SRC}/backend/requirements.txt" ]; then
  echo "FATAL: the reference application is not populated." >&2
  echo "  expected: ${APP_SRC}/backend/requirements.txt" >&2
  echo "" >&2
  echo "This bundle left the kit as MECHANICALLY-GREEN, NO-SOLUTION. Generate the" >&2
  echo "reference application from the held-out coverage target beside this script," >&2
  echo "then re-run the oracle gate. Until then the task is NOT admissible and must" >&2
  echo "not be counted toward corpus targets." >&2
  exit 1
fi

: "${APP_PUBLIC_PORT:=4173}"
: "${DATABASE_URL:?DATABASE_URL is not set}"

cp -a "${APP_SRC}/." "${WORKDIR}/"
cd "${WORKDIR}"

# Reserved by the App Contract, and left empty.
mkdir -p .browser_screenshots .downloads

# --- backend ---------------------------------------------------------------
# Migrations carry the CHECK (reserved >= 0 AND reserved <= on_hand) constraint,
# which is the whole task. The seed is idempotent and safe on a second oracle run.
python -m pip install --no-cache-dir -r backend/requirements.txt
(cd backend && alembic upgrade head && python -m seeds.seed)
(cd backend && setsid nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    > /tmp/backend.log 2>&1 < /dev/null &)

# --- frontend: a production build behind a preview server, never a dev server --
(cd frontend && npm ci && npm run build)
(cd frontend && setsid nohup npm run preview -- \
    --host 0.0.0.0 --port "${APP_PUBLIC_PORT}" \
    > /tmp/app.log 2>&1 < /dev/null &)

# Block until the contract's health target answers, so an oracle run does not
# race the verifier.
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${APP_PUBLIC_PORT}/api/health" > /dev/null 2>&1; then
    echo "reference application up on ${APP_PUBLIC_PORT}"
    exit 0
  fi
  sleep 2
done

echo "reference application did not come up within 120s" >&2
tail -50 /tmp/backend.log /tmp/app.log >&2 || true
exit 1
