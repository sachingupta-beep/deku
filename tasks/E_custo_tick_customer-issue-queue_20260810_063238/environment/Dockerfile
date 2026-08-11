# Agent runtime for ethara/customer-issue-queue.
#
# Stack comes from task.toml (highest authority) and 02-TRD.md: Node 20 +
# TypeScript for the app, PostgreSQL and Mailpit as sidecars the agent only
# holds the client end of. Under [verifier].environment_mode = "shared" the
# grader runs in THIS image, so its Python runtime deps are installed here too;
# the agent is free to ignore them.
#
# Pinned by explicit version tag, never `latest`.
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_MAJOR=20

# Multi-architecture guard (reference C §C.4). NodeSource publishes both
# amd64 and arm64 for setup_20.x; any other architecture aborts the build
# rather than producing a silently broken image.
ARG TARGETARCH
RUN case "${TARGETARCH}" in \
      amd64|arm64) echo "building for ${TARGETARCH}" ;; \
      *) echo "unsupported architecture: ${TARGETARCH:-<unset>}" >&2; exit 1 ;; \
    esac

# postgresql-client supplies pg_isready for the sidecar healthcheck in
# task.toml; curl is installed explicitly because this slim image does not
# carry it, and a health check that can never succeed is worse than none.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git build-essential postgresql-client \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI ONLY -- no daemon in this image. It talks to the `dockerd` sidecar
# over TCP (DOCKER_HOST below), a nested daemon with no access to the host's.
# The agent needs it to test the /app/Dockerfile the deployment contract asks
# for; the harness builds the graded image itself, on a daemon the agent never
# touches.
#
# Static tarball rather than `apt-get install docker.io`: that package drags in
# the daemon, containerd and runc -- ~400MB this image must never run.
ARG DOCKER_CLI_VERSION=27.3.1
RUN set -eux; \
    case "$(uname -m)" in \
      x86_64)  DOCKER_ARCH=x86_64  ;; \
      aarch64) DOCKER_ARCH=aarch64 ;; \
      *) echo "unsupported architecture for the docker CLI: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_CLI_VERSION}.tgz" \
      -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /usr/local/bin --strip-components=1 docker/docker; \
    rm /tmp/docker.tgz; \
    docker --version

# buildx, so the agent's `docker build` uses the SAME builder grading uses.
# Without it the static CLI falls back to the legacy builder -- a different
# engine from the one that scores it, and every build prints a deprecation
# warning that reads like an error.
ARG DOCKER_BUILDX_VERSION=0.19.3
RUN set -eux; \
    case "$(uname -m)" in \
      x86_64)  BX_ARCH=amd64 ;; \
      aarch64) BX_ARCH=arm64 ;; \
      *) echo "unsupported architecture for buildx: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    mkdir -p /usr/local/libexec/docker/cli-plugins; \
    curl -fsSL "https://github.com/docker/buildx/releases/download/v${DOCKER_BUILDX_VERSION}/buildx-v${DOCKER_BUILDX_VERSION}.linux-${BX_ARCH}" \
      -o /usr/local/libexec/docker/cli-plugins/docker-buildx; \
    chmod +x /usr/local/libexec/docker/cli-plugins/docker-buildx

ENV DOCKER_HOST=tcp://dockerd:2375 \
    DOCKER_BUILDKIT=1

# Reserved by the App Contract.
RUN mkdir -p /app/.browser_screenshots /app/.downloads

# Grader runtime deps (shared verifier mode). psycopg reads the tickets and
# users tables directly; httpx drives the HTTP API.
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

ENV PYTHONPATH=/tests

# Browser grader runtime. `playwright install --with-deps` is NOT used: it falls
# back to an Ubuntu package list on Debian and dies on a missing font package.
# The libraries below are chromium's actual runtime deps on Debian bookworm.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
      libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 \
      libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
      libcairo2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --break-system-packages playwright==1.49.1 \
       || pip install --no-cache-dir playwright==1.49.1
RUN playwright install chromium

WORKDIR /app

# No package cache is COPYed from the host (D24): a host-resolved node_modules
# or wheelhouse carries the build host's architecture-specific binaries and is
# wrong on the other architecture. Registry access at build time is covered by
# the allowlist in task.toml.
#
# PostgreSQL and Mailpit are sidecars, never baked in. The app reads their
# addresses from DATABASE_URL and SMTP_HOST/SMTP_PORT at runtime, binds 0.0.0.0,
# takes its port from APP_PUBLIC_PORT (container-internal 4173), and serves a
# production build behind a preview server -- never a dev server.
