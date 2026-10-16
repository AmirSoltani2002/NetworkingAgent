# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.lock ./
# CPU wheel avoids downloading CUDA runtimes for the default local deployment.
# GPU deployments can rebuild with a suitable PyTorch wheel index/version.
ARG TORCH_VERSION=2.8.0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX}"
RUN pip install --no-cache-dir -r requirements.lock && pip check

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" \
    HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 TOKENIZERS_PARALLELISM=false
RUN groupadd --gid 1000 rag && useradd --uid 1000 --gid rag --create-home rag \
    && mkdir -p /app /data/documents /data/models \
    && chown -R rag:rag /app /data
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY --chown=rag:rag rag ./rag
COPY --chown=rag:rag migrations ./migrations
COPY --chown=rag:rag alembic.ini ./
USER rag
EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('RAG_PORT','8090')+'/health',timeout=3)"
ENTRYPOINT ["python", "-m", "rag.cli"]
CMD ["api"]

FROM runtime AS test
USER root
COPY requirements-test.lock ./
RUN pip install --no-cache-dir -r requirements-test.lock
COPY --chown=rag:rag tests ./tests
COPY --chown=rag:rag pyproject.toml ./
USER rag
ENTRYPOINT ["pytest"]

FROM runtime AS production
