# Agent runtime for ethara/warehouse-allocation-ledger.
#
# Under [verifier].environment_mode = "shared" the verifier runs in THIS image
# after the agent phase ends, so the image carries both the agent's toolchain
# (from the TRD: Python 3.12 + FastAPI backend, Node for the Vite/React frontend)
# and the grader's runtime dependencies.
#
# glibc, not musl: the TRD pins bcrypt via passlib and psycopg, both of which
# ship prebuilt glibc wheels. An Alpine base would rebuild them from source on
# every architecture, or fail.
#
# Every version below is an explicit tag. Nothing floats, and no architecture is
# hardcoded: apt, pip and npm each resolve per architecture on their own, so no
# TARGETARCH branch is warranted here and adding one would be a gratuitous
# failure surface.
FROM python:3.12.7-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    NODE_MAJOR=20

# curl is installed explicitly rather than assumed: the slim base does not ship
# it, and both the NodeSource bootstrap below and the App Contract's own
# self-check need it. postgresql-client supplies pg_isready, which is what the
# task.toml healthcheck runs against the postgres SIDECAR, never against the
# agent's application.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      build-essential \
      postgresql-client \
 && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Reserved by the App Contract, created empty at the application root.
RUN mkdir -p /app/.browser_screenshots /app/.downloads

# Grader runtime. These belong to the verifier, not to the agent, and the agent
# is free to ignore them. Pinned exactly so a grader run cannot drift. psycopg is
# what the backend capability adapter reads the allocation tables with, and it is
# the only way the contention observation can be proved at all.
RUN pip install --no-cache-dir --break-system-packages \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      "psycopg[binary]==3.2.3" \
      pyyaml==6.0.2 \
 || pip install --no-cache-dir \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      "psycopg[binary]==3.2.3" \
      pyyaml==6.0.2

# ---------------------------------------------------------------------------
# Runtime patches for third-party bugs in the AGENT framework.
#
# Harbor installs OpenHands into /opt/openhands-venv at RUN time, so this image
# cannot patch it directly -- it does not exist yet at build time. Python imports
# `sitecustomize` at interpreter startup from anywhere on sys.path, and PYTHONPATH
# is on sys.path, so this reaches processes started long after the build.
#
# Currently fixes binaryornot.is_binary_string, which OpenHands calls on every
# file read. On an empty file chardet returns encoding=None, the library calls
# bytes.decode(None), and its except branch references the Python 2 builtin
# `unicode` -- turning a recoverable decode error into a NameError, a FastAPI 500,
# and AgentState.RUNNING -> ERROR. It killed a 132-step run on 2026-08-07.
# ---------------------------------------------------------------------------
COPY sitecustomize.py /opt/deku-patches/sitecustomize.py

ENV PYTHONPATH=/opt/deku-patches:/tests

# Browser grader runtime. `playwright install --with-deps` is deliberately NOT
# used: on Debian it falls back to an Ubuntu package list and dies on a font
# package that does not exist here. The libraries below are chromium's actual
# runtime dependencies on bookworm.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
      libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 \
      libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
      libcairo2 libasound2 fonts-liberation \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir --break-system-packages playwright==1.49.1 \
 || pip install --no-cache-dir playwright==1.49.1
RUN playwright install chromium

WORKDIR /app

# No CMD. This is an agent environment image: Harbor starts the agent session in
# it, and the App Contract makes starting the application the agent's own job,
# detached, on the port it reads from APP_PUBLIC_PORT, bound to 0.0.0.0. A CMD
# here would start something the contract says the agent must start itself.
