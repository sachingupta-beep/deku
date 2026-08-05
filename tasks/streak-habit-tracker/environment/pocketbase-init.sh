#!/bin/sh
# Creates the superuser and the task's collection schema before the agent starts.
#
# The schema is environment, not agent work. Creating a PocketBase collection
# requires admin credentials, and BACKEND_ADMIN_KEY is deliberately withheld from
# the agent phase (PLAN.md 3.4) so an agent cannot satisfy workflows by writing
# state directly. Without this the task is unsolvable: instruction.md mandates
# three named collections the agent is structurally forbidden from creating.
#
# instruction.md already gives the agent this exact data model (`datamodel` is in
# spec_sections_given), so pre-creating it removes an impossible requirement
# without removing any of the work being measured.
set -e

ADMIN_EMAIL="admin@ethara.ai"
ADMIN_PASS="deku-local-dev"
BASE="http://127.0.0.1:8090"

pocketbase migrate up
pocketbase admin create "$ADMIN_EMAIL" "$ADMIN_PASS" || true
pocketbase serve --http=0.0.0.0:8090 &
PB_PID=$!

for _ in $(seq 1 60); do
  wget -qO- "$BASE/api/health" >/dev/null 2>&1 && break
  sleep 1
done

TOKEN=$(wget -qO- --header='Content-Type: application/json' \
  --post-data="{\"identity\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASS\"}" \
  "$BASE/api/admins/auth-with-password" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')

create() {
  wget -qO- --header='Content-Type: application/json' --header="Authorization: $TOKEN" \
    --post-data="$1" "$BASE/api/collections" >/dev/null 2>&1 \
    && echo "created collection" || echo "collection exists or failed (continuing)"
}

# API rules are REQUIRED on both collections.
# In PocketBase 0.22, an unset (null) rule means SUPERADMIN-ONLY access.
# The agent authenticates as a normal end user and has no admin credentials
# (BACKEND_ADMIN_KEY is withheld from the agent phase by design), so null rules
# produce HTTP 403 on every read and write, making the task impossible to pass.
# These rules grant each user access to their OWN rows only:
#   - listRule/viewRule/updateRule/deleteRule: "user_id = @request.auth.id"
#   - createRule: "@request.auth.id != \"\" && user_id = @request.auth.id"
# This keeps cross-user isolation intact (tested by cross_user_access_forbidden)
# while allowing the normal-user app to function. Do NOT set rules to "" (public).

create '{
  "name":"habits","type":"base",
  "listRule":"user_id = @request.auth.id",
  "viewRule":"user_id = @request.auth.id",
  "createRule":"@request.auth.id != \"\" && user_id = @request.auth.id",
  "updateRule":"user_id = @request.auth.id",
  "deleteRule":"user_id = @request.auth.id",
  "schema":[
    {"name":"user_id","type":"text","required":true},
    {"name":"name","type":"text","required":true},
    {"name":"description","type":"text","required":false},
    {"name":"color","type":"text","required":false},
    {"name":"deleted","type":"bool","required":false}
  ]
}'

create '{
  "name":"completions","type":"base",
  "listRule":"user_id = @request.auth.id",
  "viewRule":"user_id = @request.auth.id",
  "createRule":"@request.auth.id != \"\" && user_id = @request.auth.id",
  "updateRule":"user_id = @request.auth.id",
  "deleteRule":"user_id = @request.auth.id",
  "schema":[
    {"name":"user_id","type":"text","required":true},
    {"name":"habit_id","type":"text","required":true},
    {"name":"date","type":"text","required":true}
  ]
}'

wait "$PB_PID"
