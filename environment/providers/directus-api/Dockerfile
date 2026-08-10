# Build from the environment root so the shared plane is in context:
#   docker build -f directus-api/Dockerfile -t mocks-directus-api:v1 .
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
RUN groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app
WORKDIR /app
COPY directus-api/requirements.txt directus-api/requirements-locked.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements-locked.txt
COPY _mutable_store.py admin_plane.py tracking_middleware.py ./
COPY directus-api/ ./
RUN chown -R app:app /app
EXPOSE 8105
USER app
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8105"]
