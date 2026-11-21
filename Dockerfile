# Build with --platform linux/amd64 for the portable cloud runner.
FROM node:22-bookworm-slim AS node
FROM python:3.13-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libatomic1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY analytics/requirements.lock.txt analytics/requirements-cloud.txt /app/analytics/
RUN pip install --no-cache-dir -r analytics/requirements-cloud.txt && pip check && node --version
COPY analytics/ /app/analytics/
COPY lib/ /app/lib/
COPY scripts/ /app/scripts/
COPY test/ /app/test/
RUN useradd --create-home --uid 10001 runner && mkdir -p /data /app/.local \
    && chown runner:runner /data /app/.local
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    TEMPO_BACKEND=duckdb TEMPO_ANALYTICS_DIR=/data/analytics SQLMESH_HOME=/data/sqlmesh
USER runner
VOLUME ["/data"]
ENTRYPOINT ["python", "-m"]
CMD ["analytics.cli", "--help"]
