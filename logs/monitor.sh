#!/usr/bin/env bash
# Detached run monitor. Records lifecycle + outcome to logs/run_status.txt so the
# caller polls a file instantly instead of blocking on a sleep. Short interval so
# a fast failure is visible in seconds, not at the end of a worst-case window.
BASE=/Users/macbookpro/Desktop/greenfield/testing
cd "$BASE"
S="$BASE/logs/run_status.txt"
IV=15
: > "$S"
echo "watching from $(date '+%H:%M:%S')" >> "$S"
while pgrep -f "harbor run" >/dev/null; do
  J=$(ls -dt jobs/*/ 2>/dev/null | head -1)
  T=$(find "$J" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)
  printf '%s phase=%s verifier=[%s]\n' "$(date '+%H:%M:%S')" \
    "$([ -f "$T/agent/trajectory.json" ] && echo verify || echo agent)" \
    "$(ls "$T/verifier/" 2>/dev/null | tr '\n' ' ')" >> "$S"
  sleep "$IV"
done
J=$(ls -dt jobs/*/ 2>/dev/null | head -1)
T=$(find "$J" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)
{
  echo "ENDED $(date '+%H:%M:%S')  job=$J"
  [ -f "$T/exception.txt" ] && echo "EXCEPTION: $(tail -2 "$T/exception.txt" | tr '\n' ' ' | cut -c1-300)" || echo "clean trial"
  echo "reward: $(cat "$T/verifier/reward.json" 2>/dev/null | tr -d '\n' || echo none)"
} >> "$S"
