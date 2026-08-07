#!/bin/sh
# Creates the unprivileged role the AGENT uses.
#
# TASK-SPECIFIC, not the generic environment/providers/postgres/init.sh copy: that
# one creates `deku_app` against database `ethara`, while this task pins
#
#   DATABASE_URL = postgresql://app:deku-app-pw-2026@postgres:5432/strength_log
#
# in task.toml. The role name, password and database below are read straight from
# that URL -- change one, change both, or the agent gets a Postgres it cannot log
# into and the trial fails as "never connected" rather than "wrong credentials".
#
# Privilege split (PLAN.md 3.4): the superuser (verifier_admin) stays with the
# verifier so the agent cannot satisfy a workflow by writing rows directly instead
# of implementing the feature. `app` gets only what an application needs.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE app LOGIN PASSWORD 'deku-app-pw-2026';
    GRANT CONNECT ON DATABASE strength_log TO app;
    GRANT ALL ON SCHEMA public TO app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON TABLES TO app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON SEQUENCES TO app;
EOSQL
