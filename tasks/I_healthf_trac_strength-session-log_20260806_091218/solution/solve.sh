#!/usr/bin/env bash
# solution/solve.sh -- oracle deploy script for the Ethara Strength Session Log.
#
# STATE: app-deferred (D20). solution/app/ carries no application code yet, so this
# script FAILS LOUDLY. It is deliberately not a stub that pretends success: G20 depends
# on nobody mistaking a stub for a solution, and a silent exit 0 here would report a
# working oracle over an empty directory.
#
# When the app is generated downstream from solution/checklist.md, replace the guard
# below with the real install-and-start sequence. That sequence must:
#   - install dependencies at deploy time (solution/app/ never carries a dependency tree)
#   - serve a production build, never a dev server
#   - bind 0.0.0.0 on the container-internal port 4173
#   - read the public port from APP_PUBLIC_PORT
#   - start fully detached, so the server outlives the session:
#       setsid nohup <command> > /tmp/app.log 2>&1 < /dev/null &
#   - write credentials to /app/USER_README.md
#   - create empty .browser_screenshots/ and .downloads/ at the app root

set -u

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/app"

# Any source file other than the credentials README means the app has landed.
code_files="$(find "$APP_DIR" -type f ! -name 'USER_README.md' 2>/dev/null | head -n 1)"

if [ -z "$code_files" ]; then
  echo "FATAL: solution/app/ carries no application code (state: MECHANICALLY-GREEN, NO-SOLUTION)." >&2
  echo "       This bundle is NOT ADMISSIBLE. Generate the app from solution/checklist.md first," >&2
  echo "       then replace this guard with the real deploy sequence and re-run the handoff gates." >&2
  exit 1
fi

echo "FATAL: solution/app/ carries code but solve.sh has not been completed." >&2
echo "       Implement the install-and-start sequence documented at the top of this file." >&2
exit 1
