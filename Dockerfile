# syntax=docker/dockerfile:1
#
# Workspace Operator — Streamable HTTP image.
#
# The container binds 0.0.0.0 internally (required for port publishing) and is
# expected to be published to the host loopback only, e.g. `-p 127.0.0.1:8765:8765`.
# It runs as an unprivileged user (uid 10001) with HOME=/home/app.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Workspace Operator" \
      org.opencontainers.image.description="Google Workspace automation over MCP: 39 tools, human-approved deletes, bulk undo, staged writes" \
      org.opencontainers.image.source="https://github.com/Artoxem/workspace-operator" \
      org.opencontainers.image.url="https://pypi.org/project/workspace-operator-mcp/" \
      org.opencontainers.image.licenses="MIT" \
      io.modelcontextprotocol.server.name="io.github.Artoxem/workspace-operator"

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

# Install the package itself so the `workspace-operator` command exists in the
# image (dependencies are already installed from requirements.txt above).
RUN pip install --no-cache-dir --no-deps . \
    && rm -rf build *.egg-info

RUN useradd --create-home --uid 10001 app \
    && chown -R app:app /app

USER app
ENV HOME=/home/app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2).status == 200 else 1)"

ENTRYPOINT ["python", "-m", "workspace_operator", "serve"]
# Safe default: bind inside the container only. Publishing the port to the network
# is a deliberate decision; docker-compose.yml passes --allow-network/--insecure
# together with a loopback-only port mapping. For a plain `docker run` add them
# yourself:  docker run -p 127.0.0.1:8765:8765 IMAGE --http --host 0.0.0.0 \
#            --allow-network --insecure
CMD ["--http", "--host", "127.0.0.1", "--port", "8765"]
