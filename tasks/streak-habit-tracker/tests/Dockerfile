# Verifier image for ethara/streak-habit-tracker.
#
# Under [verifier].environment_mode = "separate" Harbor builds this image from
# tests/ and does NOT upload tests/ at runtime -- the image must ship /tests
# itself. That property is exactly what keeps workflows.yaml hidden from the agent.
#
# The base carries the grader, the capability adapters and the reward
# orchestration; this layer adds only what is specific to this task.
#
#     docker build -t deku-verifier-base:0.1 harness/verifier

FROM deku-verifier-base:0.2

COPY workflows.yaml conftest.py test_habits.py test_completions.py \
     test_streaks.py test_authorization.py /tests/
