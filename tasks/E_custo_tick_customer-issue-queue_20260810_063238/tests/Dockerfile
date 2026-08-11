# Verifier image for ethara/customer-issue-queue.
#
# task.toml sets [verifier].environment_mode = "shared", so the grader runs in
# the agent's own image (environment/Dockerfile installs its Python deps) and
# the hold-out of tests/ is TEMPORAL, not spatial: Harbor uploads this layer
# only after the agent phase has ended.
#
# This file exists so the layer can also be built standalone, which is what a
# future switch to "separate" mode would need. The base carries the grader, the
# capability adapters and the reward orchestration; this layer adds only what is
# specific to this task.
#
#     docker build -t deku-verifier-base:0.2 harness/verifier

FROM deku-verifier-base:0.2

COPY workflows.yaml rubric.json conftest.py \
     test_core_features.py test_data_integrity.py test_authorization.py \
     test_email.py test_edge_cases.py /tests/
