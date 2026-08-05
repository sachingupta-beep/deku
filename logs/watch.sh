#!/usr/bin/env bash
# Poll a run at SHORT intervals and exit the moment it ends, so a fast failure
# surfaces in seconds instead of blocking for the whole worst-case window.
# usage: watch.sh <max_seconds> [interval_seconds]
MAX=${1:-1800}; IV=${2:-20}; n=$((MAX/IV))
for i in $(seq 1 $n); do
  if ! pgrep -f "harbor run" >/dev/null; then
    echo "ENDED after $((i*IV))s at $(date '+%H:%M:%S')"; exit 0
  fi
  sleep "$IV"
done
echo "STILL RUNNING after ${MAX}s at $(date '+%H:%M:%S')"; exit 1
