FROM python:3.12-slim-bookworm AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && pip check
FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN groupadd --gid 1000 zsk && useradd --uid 1000 --gid zsk --create-home zsk && mkdir -p /app /data/models && chown -R zsk:zsk /app /data
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY --chown=zsk:zsk zsk ./zsk
COPY --chown=zsk:zsk data ./data
COPY --chown=zsk:zsk migrations ./migrations
USER zsk
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=10 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=3)"
ENTRYPOINT ["python","-m","zsk.cli"]
FROM runtime AS test
ENV PYTHONPATH=/app
USER root
COPY requirements-test.lock ./
RUN pip install --no-cache-dir -r requirements-test.lock
COPY --chown=zsk:zsk tests ./tests
USER zsk
ENTRYPOINT ["pytest","-q","tests"]
FROM runtime AS production
