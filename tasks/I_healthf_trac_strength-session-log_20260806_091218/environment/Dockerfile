# Agent runtime for ethara/strength-session-log.
# Sources, in priority order: task.toml > _spec/02-TRD.md > _spec/01-PRD.md > reference Dockerfiles.
#
# The TRD leaves language and framework to the agent and pins only the HTTP boundary, so this
# image carries the two runtimes a web app in this corpus is built with, plus a PostgreSQL
# client for the declared `backend` slot. Nothing here starts the app: the agent builds and
# starts it per the deployment contract in instruction.md.

# Debian bookworm (glibc, not musl): the runtime depends on prebuilt wheels and prebuilt
# node binaries, and musl variants of those are a different, frequently broken build.
# Pinned by explicit version tag, never `latest`.
FROM node:22.11.0-bookworm

# Multi-architecture guard. Both linux/amd64 and linux/arm64 are supported; anything else
# aborts the build here rather than producing a silently broken image.
ARG TARGETARCH
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64|arm64) echo "building for ${TARGETARCH}" ;; \
      *) echo "unsupported architecture: '${TARGETARCH}' (expected amd64 or arm64)" >&2; exit 1 ;; \
    esac

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=development

# Package names verified against Debian bookworm. `curl` is installed explicitly rather than
# assumed: the base image is not guaranteed to carry it, and a health probe that can never
# succeed is worse than none. postgresql-client gives the agent psql against DATABASE_URL.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      postgresql-client \
      python3 \
      python3-pip \
      python3-venv \
      tini; \
    rm -rf /var/lib/apt/lists/*

# Corepack ships with this Node tag; enabling it lets the agent use npm, pnpm or yarn.
RUN corepack enable

# D24: any dependency cache is resolved IN-BUILD, per architecture. A host-resolved
# wheelhouse, npm/pnpm store or node_modules tree is never COPYed in -- those carry the build
# host's architecture-specific binaries and are wrong on the other architecture.
RUN set -eux; \
    npm config set cache /root/.npm --global; \
    python3 -m pip install --break-system-packages --no-cache-dir --upgrade pip setuptools wheel

# ---------------------------------------------------------------------------
# Grader runtime.
#
# This image is ALSO where the verifier runs -- both under Harbor's shared mode
# (verifier.environment_mode = "shared") and under harness/eval_fresh.py, which
# redeploys into a clean container built from this same Dockerfile. The graders
# are not self-contained: run_workflows.py and run_rubric.py import httpx and
# drive Playwright, score.py imports yaml, and the substep tests run under
# pytest. Without them the verifier dies on ModuleNotFoundError and the trial
# reports a harness fault instead of an agent score.
#
# The agent is free to ignore all of this; it is grader machinery, not app deps.
# Versions match the rest of the corpus so a grader change behaves identically
# across tasks.
# ---------------------------------------------------------------------------
RUN python3 -m pip install --break-system-packages --no-cache-dir \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      pyyaml==6.0.2 \
      psycopg[binary]==3.2.3

ENV PYTHONPATH=/tests

# Chromium for the browser grader. The explicit library list is deliberate:
# `playwright install --with-deps` resolves a distro package set that has broken
# on Debian before (a missing font package aborts the whole install), so the real
# chromium runtime deps are named here instead.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
      libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 \
      libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
      libcairo2 libasound2 fonts-liberation; \
    rm -rf /var/lib/apt/lists/*; \
    python3 -m pip install --break-system-packages --no-cache-dir playwright==1.49.1; \
    python3 -m playwright install chromium

WORKDIR /app

# The reserved directories the deployment contract requires, present and empty.
RUN mkdir -p /app/.browser_screenshots /app/.downloads

# 4173 is the container-internal port the deployment contract fixes. The published port comes
# from APP_PUBLIC_PORT at run time; neither is hardcoded into the application.
EXPOSE 4173

# No HEALTHCHECK here. A healthcheck is emitted only for a sidecar (for the db slot that would
# be `pg_isready -h postgres` in the compose file), never against the agent's own app --
# the app does not exist at image build time.

# tini reaps the detached process tree the agent starts with `setsid nohup`.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sleep", "infinity"]
