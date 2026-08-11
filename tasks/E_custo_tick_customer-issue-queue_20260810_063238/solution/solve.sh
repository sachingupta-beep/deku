#!/usr/bin/env bash
# Oracle deploy script for E_custo_tick_customer-issue-queue_20260810_063238.
#
# app-deferred mode (D20): solution/app/ carries no application code yet, so
# there is nothing to deploy. This script fails loudly rather than exiting 0,
# because a stub that pretends success would make G20 (nop agent scores 0.0)
# and G19 (oracle returns 1.0) indistinguishable from a real solution.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/app"

# USER_README.md ships with the bundle; application source does not.
if [ -z "$(find "$APP_DIR" -type f ! -name 'USER_README.md' -print -quit 2>/dev/null)" ]; then
  echo "ABORT: solution/app/ contains no application code (app-deferred, D20)." >&2
  echo "  This bundle is MECHANICALLY-GREEN, NO-SOLUTION and is not admissible." >&2
  echo "  Generate the reference app from solution/checklist.md, then re-run." >&2
  exit 1
fi

echo "ABORT: solve.sh has not been updated for the generated app." >&2
exit 1
