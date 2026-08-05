# Verifier image for ethara/creator-subscription-billing.
#
# Under [verifier].environment_mode = "separate" Harbor builds this image from
# tests/ and does NOT upload tests/ at runtime -- the image must ship /tests
# itself. That property is exactly what keeps workflows.yaml hidden from the agent.
#
# The base carries the grader, the capability adapters (postgres, deku-pay,
# minio) and the reward orchestration; this layer adds only what is specific
# to this task.
#
#     docker build -t deku-verifier-base:0.1 harness/verifier

FROM deku-verifier-base:0.2

COPY workflows.yaml conftest.py test_payments.py test_access_control.py \
     test_storage.py test_data_integrity.py /tests/
