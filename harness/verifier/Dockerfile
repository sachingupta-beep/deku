# Shared verifier base image (PLAN.md 3.7 images/verifier/).
#
# Built from harness/ so both graders land in one image:
#     docker build -t deku-verifier-base:0.2 -f harness/verifier/Dockerfile harness
#
# Each task's tests/Dockerfile is then three lines: FROM this, COPY its own
# workflows.yaml + conftest.py + test_*.py over the top. The graders, the
# capability adapters and the reward orchestration live here and are identical
# corpus-wide -- which is the point. A grader change is a corpus-wide event
# (PLAN.md 4.5), so it must have exactly one source of truth.

# Vendor image: Chromium and its system libraries are preinstalled and pinned to
# the playwright version in the tag, so the browser cannot drift underneath a
# grader that must stay comparable across a sweep (PLAN.md 4.5).
#
# Not python:3.12-slim + `playwright install --with-deps`: slim is Debian trixie,
# where that command falls back to an Ubuntu package list and dies on the missing
# ttf-ubuntu-font-family. noble carries Python 3.12, which the harness requires.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/tests

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The vendor image ships the BROWSERS (/ms-playwright, via PLAYWRIGHT_BROWSERS_PATH)
# but not the Python package, so playwright is pip-installed here at the version
# matching the image tag. No `playwright install` step: the browsers already exist.
RUN pip install --no-cache-dir --break-system-packages \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      "psycopg[binary]==3.2.3" \
      boto3==1.35.99 \
      pyyaml==6.0.2 \
      playwright==1.49.1

COPY verifier/score.py verifier/_shapes.py verifier/capabilities.py \
     verifier/appclient.py verifier/test.sh verifier/pytest.ini /tests/
COPY eval/run_workflows.py eval/run_rubric.py /tests/

# test.sh runs each grader only when its script is executable. That switch is
# what let the pipeline score pytest-only before the browser grader existed,
# and it keeps the rubric judge optional.
RUN chmod +x /tests/test.sh /tests/score.py /tests/run_workflows.py /tests/run_rubric.py

WORKDIR /tests
