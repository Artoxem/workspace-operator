# syntax=docker/dockerfile:1
#
# Workspace Operator — Streamable HTTP image.
#
# The container binds 0.0.0.0 internally (required for port publishing) and is
# expected to be published to the host loopback only, e.g. `-p 127.0.0.1:8765:8765`.
# It runs as an unprivileged user (uid 10001) with HOME=/home/app.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Workspace Operator" \
      org.opencontainers.image.description="Google Workspace automation over MCP: 106 tools, staged writes, tool profiles" \
      org.opencontainers.image.source="https://github.com/Artoxem/workspace-operator" \
      org.opencontainers.image.url="https://pypi.org/project/workspace-operator-mcp/" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_CONFIG_FILE=/app/config.yaml

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml server.py README.md LICENSE ./
COPY workspace_operator ./workspace_operator
COPY skills ./skills

RUN useradd --create-home --uid 10001 app \
    && chown -R app:app /app

USER app
ENV HOME=/home/app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2).status == 200 else 1)"

ENTRYPOINT ["python", "-m", "workspace_operator", "serve"]
CMD ["--http", "--host", "0.0.0.0", "--port", "8765", "--allow-network", "--insecure"]
