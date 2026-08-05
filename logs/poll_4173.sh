#!/usr/bin/env bash
# Records whether the agent's app is reachable on the published host port,
# so we can tell "never started" from "started then died before verification".
while true; do
  code=$(curl -sS --max-time 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:4173/ 2>/dev/null || echo "000")
  names=$(docker ps --format '{{.Names}}' | tr '\n' ' ')
  echo "$(date '+%H:%M:%S') http=$code containers=[$names]"
  sleep 20
done
