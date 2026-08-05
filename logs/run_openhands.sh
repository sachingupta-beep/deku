#!/usr/bin/env bash
set -u
BASE=/Users/macbookpro/Desktop/greenfield/testing
cd "$BASE"
SECRET="$(cat "$BASE/.bridge_secret")"
# OpenHands routes through LiteLLM, so it wants LLM_* rather than ANTHROPIC_*,
# and a provider-prefixed model name.
export LLM_API_KEY="$SECRET"
export LLM_BASE_URL=http://host.docker.internal:8765
export ANTHROPIC_API_KEY="$SECRET"
export ANTHROPIC_BASE_URL=http://host.docker.internal:8765
echo "START $(date '+%F %H:%M:%S')  openhands + anthropic/claude-opus-4-5-20251101"
yes | "$BASE/.venv/bin/harbor" run \
  -p /tmp/deku-cmp/streak-habit-tracker \
  -a openhands -m anthropic/claude-opus-4-5-20251101 --ak version=0.62.0 --n-concurrent-agents 1
echo "END $(date '+%F %H:%M:%S')"
