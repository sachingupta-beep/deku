#!/usr/bin/env bash
set -u
BASE=/Users/macbookpro/Desktop/greenfield/testing
cd "$BASE"
export ANTHROPIC_BASE_URL=http://host.docker.internal:8765
export ANTHROPIC_API_KEY="$(cat "$BASE/.bridge_secret")"
export APP_PUBLIC_URL=http://localhost:4173
echo "START $(date '+%F %H:%M:%S')  ORACLE on smoke-tip-calculator"
yes | "$BASE/.venv/bin/harbor" run -p /tmp/deku-smoke/smoke-tip-calculator \
  -a oracle --n-concurrent-agents 1
echo "END $(date '+%F %H:%M:%S')"
