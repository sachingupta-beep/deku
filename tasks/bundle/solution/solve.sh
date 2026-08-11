#!/usr/bin/env bash
# D20 app-deferred: the reference application is generated downstream from
# solution/checklist.md. This script must fail loudly while solution/app/ ships
# without code, so a bundle stuck in NO-SOLUTION cannot be mistaken for one that
# has an oracle app installed.
set -u
echo "solve.sh: MECHANICALLY-GREEN, NO-SOLUTION -- app/ has no source yet." >&2
echo "solve.sh: generate the reference app from solution/checklist.md and re-run." >&2
exit 1
