FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 META_HARNESS_DATA=/data CORE_HOST=0.0.0.0 CORE_PORT=8000
WORKDIR /app
COPY core/server.py /app/server.py
RUN mkdir -p /data && useradd --system --uid 10001 harness && chown -R harness:harness /app /data
USER harness
EXPOSE 8000
CMD ["python", "/app/server.py"]
