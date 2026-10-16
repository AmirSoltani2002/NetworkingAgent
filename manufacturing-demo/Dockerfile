# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && pip check

FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN groupadd --gid 1000 manufacturing && useradd --uid 1000 --gid manufacturing --create-home manufacturing \
    && mkdir -p /app /data/models && chown -R manufacturing:manufacturing /app /data
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY --chown=manufacturing:manufacturing manufacturing ./manufacturing
USER manufacturing
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('MANUFACTURING_PORT','8000')+'/ready',timeout=3)"
ENTRYPOINT ["python", "-m", "manufacturing.cli"]
CMD ["api"]

FROM runtime AS test
USER root
COPY requirements-test.lock ./
RUN pip install --no-cache-dir -r requirements-test.lock
COPY --chown=manufacturing:manufacturing tests ./tests
COPY --chown=manufacturing:manufacturing pyproject.toml ./
USER manufacturing
ENTRYPOINT ["pytest"]

FROM runtime AS production
