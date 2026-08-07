# Verifier image for ethara/strength-session-log.
#
# Runs the pytest layer and the vendored grader against the deployed app over HTTP. It never
# builds or serves the app: under shared verifier mode this container observes the same
# network namespace after the agent session has ended.
#
# The suite is stdlib-only by construction -- no provider SDK is importable here, which is the
# runtime half of the black-box rule that no_sdk_lint.py (G10) enforces statically.

# Pinned by explicit version tag, never `latest`. glibc (bookworm), not musl.
FROM python:3.12.7-slim-bookworm

ARG TARGETARCH
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64|arm64) echo "building verifier for ${TARGETARCH}" ;; \
      *) echo "unsupported architecture: '${TARGETARCH}' (expected amd64 or arm64)" >&2; exit 1 ;; \
    esac

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# curl is installed explicitly rather than assumed: a slim image does not ship it, and the
# grader shell scripts probe the app over HTTP. Package names verified for bookworm.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl; \
    rm -rf /var/lib/apt/lists/*

# D24: resolved in-build, per architecture. No host-resolved wheelhouse is ever COPYed in.
# Versions are pinned so two builds of this image collect the same suite.
RUN python -m pip install --no-cache-dir \
      pytest==8.3.3 \
      pytest-timeout==2.3.1

WORKDIR /tests

# The authored suite plus the vendored grader files land here at assembly time.
COPY . /tests

# test.sh is VENDORED and owns the reward path (G14): it writes {"reward":0.0} first and
# writes a reward file on every exit path. It is never authored or wrapped here.
CMD ["/bin/sh", "/tests/test.sh"]
