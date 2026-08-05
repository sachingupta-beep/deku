# Verifier image for deku/smoke-tip-calculator.
#
# Shared mode -- Harbor uploads tests/ at verification time. This file exists
# because validate_task.py requires it, but under shared mode the actual
# verifier runtime is the agent image (environment/Dockerfile), where the
# shared grader files have been synced in via harness/sync_verifier.py.
#
# Kept present as documentation of the base image the grader assumes exists.

FROM deku-verifier-base:0.2

COPY workflows.yaml conftest.py test_smoke.py /tests/
