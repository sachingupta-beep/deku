#!/usr/bin/env bash
# 2 tasks x 2 models, sequential.
#
# Sequential, not parallel: this host has 8 GB of Docker memory and one task
# declares 4-8 GB for the agent plus a verifier plus sidecars. Two concurrent
# trials would contend and the failures would look like agent failures.

set -u

BASE=/Users/macbookpro/Desktop/greenfield/testing
cd "$BASE"

export ANTHROPIC_BASE_URL=http://host.docker.internal:8765
export ANTHROPIC_API_KEY="$(cat "$BASE/.bridge_secret")"

MODELS="claude-opus-4-5-20251101 claude-sonnet-4-5-20250929"
TASKS="streak-habit-tracker seat-allocation-map"

for task in $TASKS; do
  for model in $MODELS; do
    echo "===== $(date '+%H:%M:%S')  $task  $model  ====="
    yes | "$BASE/.venv/bin/harbor" run \
      -p "/tmp/deku-cmp/$task" \
      -a claude-code \
      -m "$model" \
      --n-concurrent-agents 1 \
      2>&1 | tail -20
    echo "===== $(date '+%H:%M:%S')  done  $task  $model  ====="
    echo
  done
done

echo "ALL COMPARISON RUNS COMPLETE"
