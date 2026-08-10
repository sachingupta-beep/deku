# Service Hub -- ONE container for the whole simulated fleet.
#
#   docker build -t service-hub:v1 .
#   docker run --rm -p 8080:8080 service-hub:v1
#
# Unlike the per-service fleet this replaces, the build context is just this
# directory: the hub vendors what it needs (hub/store.py) so the image has no
# dependency on anything outside service-hub/.
#
# Image properties, in the order they matter for a benchmark fixture:
#   * Base pinned by digest, not tag -- "python:3.12-slim" is a moving target and
#     a rebuild six months from now must produce the same interpreter.
#   * Dependencies installed with --require-hashes, so a compromised or
#     re-uploaded wheel fails the build instead of silently shipping.
#   * Runs as a non-root user.
#   * Layer order is cheap-to-expensive: requirements change rarely, service code
#     changes constantly, so a code edit rebuilds one small layer.

FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

RUN groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app

WORKDIR /app

# Dependencies first: this layer is cached across every code change.
COPY requirements.txt requirements-locked.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements-locked.txt

# Hub core.
COPY main.py router.py service_registry.py ./
COPY hub/ ./hub/

# Services and their seed data. Copied as whole trees so adding a service is a
# directory, not a Dockerfile edit -- the same property that makes the registry
# discover services without a central list.
COPY services/ ./services/
COPY data/ ./data/

RUN chown -R app:app /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HUB_HOST=0.0.0.0 \
    HUB_PORT=8080

EXPOSE 8080

USER app

# Probes the hub, not the services: "is the process serving?" must stay O(1).
# Loading 27 services to answer a healthcheck would defeat the whole design.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
