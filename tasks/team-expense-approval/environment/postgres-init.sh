#!/bin/sh
# Creates the unprivileged role the AGENT uses. The superuser stays with the
# verifier (PLAN.md 3.4) so the agent cannot satisfy a workflow by writing rows
# directly instead of implementing the feature.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE deku_app LOGIN PASSWORD 'deku-local-dev';
    GRANT CONNECT ON DATABASE ethara TO deku_app;
    GRANT ALL ON SCHEMA public TO deku_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON TABLES TO deku_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON SEQUENCES TO deku_app;
EOSQL
