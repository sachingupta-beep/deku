FROM python:3.12-slim

# Pin deps so the image is reproducible; no external network needed after build.
RUN pip install --no-cache-dir \
      "fastapi==0.115.5" \
      "uvicorn[standard]==0.32.1" \
      "httpx==0.28.1"

WORKDIR /app
COPY app.py .

# Defaults for local dev; compose overrides these at runtime.
ENV PAYMENTS_SECRET_KEY=sk_local_deku \
    PAYMENTS_PUBLISHABLE_KEY=pk_local_deku \
    PAYMENTS_WEBHOOK_SECRET=wh_local_deku \
    DEKU_SETTLE_DELAY=2

EXPOSE 8080

# Use python's stdlib urlopen for the healthcheck -- curl may not be present.
HEALTHCHECK --interval=5s --timeout=5s --retries=20 --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
