FROM node:22.13.1-bookworm-slim AS nodesrc

FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/tests \
    APP_PUBLIC_PORT=4173

ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    NPM_CONFIG_CAFILE=/etc/ssl/certs/ca-certificates.crt \
    GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt

ENV NO_PROXY=localhost,127.0.0.1,::1,main,postgres \
    no_proxy=localhost,127.0.0.1,::1,main,postgres

COPY --from=nodesrc /usr/local/bin/node /usr/local/bin/node
COPY --from=nodesrc /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN set -eux; \
    ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    node --version; \
    npm --version

ARG PROXY_CA_PEM=""
RUN set -eux; \
    if [ -n "$PROXY_CA_PEM" ]; then \
      printf '%s\n' "$PROXY_CA_PEM" > /usr/local/share/ca-certificates/proxy-mitm.crt; \
      openssl x509 -in /usr/local/share/ca-certificates/proxy-mitm.crt -noout -subject -dates; \
      update-ca-certificates; \
      grep -c 'BEGIN CERTIFICATE' /etc/ssl/certs/ca-certificates.crt; \
    else \
      echo 'no PROXY_CA_PEM supplied; building without TLS interception'; \
    fi

RUN set -eux; \
    pip3 install --no-cache-dir --break-system-packages \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      pyyaml==6.0.2

RUN set -eux; \
    python3 --version; \
    python3 -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"; \
    python3 -c "import playwright.sync_api"; \
    command -v curl; \
    command -v openssl; \
    command -v node; \
    command -v npm

RUN set -eux; mkdir -p /app/.browser_screenshots /app/.downloads

WORKDIR /app
EXPOSE ${APP_PUBLIC_PORT}
CMD ["bash"]
