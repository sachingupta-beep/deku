# Verifier image for ethara/warehouse-allocation-ledger.
#
# Under [verifier].environment_mode = "shared" the grader runs in the agent's own
# environment image, after the agent session has ended. This file exists so the
# verifier layer is buildable and inspectable on its own, and so G13 has a second
# image to build: it repeats the grader runtime rather than inheriting it,
# because inheriting would tie the two images together by a tag no registry here
# guarantees.
#
# Same base and the same pins as environment/Dockerfile. Nothing floats.
FROM python:3.12.7-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/tests

# curl is what test.sh polls the health route with, and the slim base does not
# ship it. postgresql-client is not needed here: the backend adapter speaks to
# postgres through psycopg rather than through a command line client.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      pytest==8.4.1 \
      pytest-json-ctrf==0.3.5 \
      httpx==0.28.1 \
      "psycopg[binary]==3.2.3" \
      pyyaml==6.0.2

# Chromium's real runtime dependencies on bookworm. `playwright install
# --with-deps` is deliberately avoided: on Debian it falls back to an Ubuntu
# package list and dies on a font package that does not exist here.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
      libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 \
      libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
      libcairo2 libasound2 fonts-liberation \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir playwright==1.49.1
RUN playwright install chromium

# The verifier image must ship /tests itself: that property is what keeps
# workflows.yaml and every assertion out of the agent's reach for the whole agent
# phase.
COPY test.sh pytest.ini score.py run_workflows.py run_rubric.py \
     capabilities.py appclient.py _shapes.py /tests/
COPY conftest.py workflows.yaml rubric.json instruction.md /tests/
COPY test_core_features.py test_data_integrity.py test_authorization.py \
     test_edge_cases.py /tests/

RUN chmod +x /tests/test.sh /tests/score.py /tests/run_workflows.py /tests/run_rubric.py

WORKDIR /tests
CMD ["/tests/test.sh"]
