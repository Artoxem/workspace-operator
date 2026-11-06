# Workspace Operator — Streamable HTTP image.
#
# The container binds 0.0.0.0 internally (required for port publishing) and is
# expected to be published to the host loopback only, e.g. `-p 127.0.0.1:8765:8765`.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml server.py ./
COPY workspace_operator ./workspace_operator
COPY skills ./skills

EXPOSE 8765

ENTRYPOINT ["python", "-m", "workspace_operator", "serve"]
CMD ["--http", "--host", "0.0.0.0", "--port", "8765", "--allow-network", "--insecure"]
