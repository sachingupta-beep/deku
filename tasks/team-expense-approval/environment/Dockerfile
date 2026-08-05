FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_MAJOR=20

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git build-essential postgresql-client \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Reserved by the App Contract (PLAN.md 4.3).
RUN mkdir -p /app/.browser_screenshots /app/.downloads

# The verifier runs in THIS image under shared mode (PLAN.md 1.8 fallback), because
# a separate verifier environment is torn up only after Harbor has already stopped
# this one -- so a separate grader never sees a live app. These are the grader's
# runtime deps, not the agent's; the agent is free to ignore them.
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

# Browser grader runtime. `playwright install --with-deps` is NOT used: these
# images are Debian trixie, where that command falls back to an Ubuntu package
# list and dies on the missing ttf-ubuntu-font-family. The libraries below are
# chromium's actual runtime deps on Debian, verified by launching it.
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

# PLAN.md 3.6 Phase 2: warm the package caches here (npm store + pip wheelhouse)
# so the agent phase can run with network_mode = "no-network". Until then the
# allowlist in task.toml covers registry access at build time.
#
# Keycloak and PostgreSQL are sidecar services, not baked into this image; the
# agent reaches them through AUTH_ISSUER_URL and DATABASE_URL.
