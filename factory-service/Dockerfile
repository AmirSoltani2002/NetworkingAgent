FROM zsk-ml:local AS runtime
USER root
RUN /opt/venv/bin/pip install --no-cache-dir websockets==15.0.1
COPY --chown=zsk:zsk factory-service/factory /app/factory
COPY --chown=zsk:zsk factory-service/migrations /app/factory-migrations
USER zsk
EXPOSE 8110
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8110/health',timeout=3)"
ENTRYPOINT ["python","-m","factory.cli"]
FROM runtime AS test
ENV PYTHONPATH=/app
USER root
COPY zsk-service/requirements-test.lock /app/requirements-test.lock
RUN pip install --no-cache-dir -r /app/requirements-test.lock
COPY --chown=zsk:zsk factory-service/tests /app/factory-tests
USER zsk
ENTRYPOINT ["pytest","-q","/app/factory-tests"]
FROM runtime AS production
