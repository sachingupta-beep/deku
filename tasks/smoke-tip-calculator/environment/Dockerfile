# Agent environment for deku/smoke-tip-calculator.
#
# This image is also where the SHARED verifier runs (task.toml sets
# verifier.environment_mode = "shared"), so both the agent's runtime AND the
# grader's runtime deps live here. Copied from tasks/streak-habit-tracker's
# Dockerfile because that image is proven to launch chromium on Debian trixie.

FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_MAJOR=20

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git build-essential unzip \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Reserved by the App Contract.
RUN mkdir -p /app/.browser_screenshots /app/.downloads

# Grader runtime deps (shared-mode verifier). The agent is free to ignore them.
RUN pip install --no-cache-dir --break-system-packages \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      pyyaml==6.0.2 \
 || pip install --no-cache-dir \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      pyyaml==6.0.2

ENV PYTHONPATH=/tests

# Browser grader runtime. Same recipe as streak-habit-tracker -- do NOT switch
# to `playwright install --with-deps` on Debian trixie; it dies on missing
# ttf-ubuntu-font-family. These are the real chromium deps.
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
