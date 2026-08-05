#!/usr/bin/env bash
set -u
BASE=/Users/macbookpro/Desktop/greenfield/testing
cd "$BASE"
export ANTHROPIC_BASE_URL=http://host.docker.internal:8765
export ANTHROPIC_API_KEY="$(cat "$BASE/.bridge_secret")"
echo "START $(date '+%F %H:%M:%S')"
yes | "$BASE/.venv/bin/harbor" run \
  -p /tmp/deku-cmp/streak-habit-tracker \
  -a claude-code -m claude-sonnet-4-5-20250929 --n-concurrent-agents 1
echo "END $(date '+%F %H:%M:%S')"
