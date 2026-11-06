# Release v1.13.0 — Docker image on GHCR

The server now ships as a container image, built for `linux/amd64` and
`linux/arm64`.

## Pull and run

```bash
docker pull ghcr.io/artoxem/workspace-operator:latest

docker run --rm -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -e MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  ghcr.io/artoxem/workspace-operator:latest
```

Tags: `1.13.0`, `1.13`, `latest`, and the commit sha. The workflow
`.github/workflows/docker-publish.yml` runs on every `v*` tag push and on manual
dispatch, authenticating with the built-in `GITHUB_TOKEN` (no secrets).

## Image details

- base `python:3.12-slim`, dependencies installed from `requirements.txt`;
- runs as an **unprivileged user** (uid 10001, `HOME=/home/app`);
- `HEALTHCHECK` on `GET /healthz`, so orchestration can tell a live server from a
  booted one;
- OCI labels: source, description, license, PyPI URL;
- the default command is the localhost-first HTTP server bound to `0.0.0.0`
  **inside** the container, published to `127.0.0.1` on the host.

## Configuration inside the container

`config.docker.yaml` uses container paths:

- `/home/app/.google` — OAuth client secrets and token (mounted read-write,
  because the server refreshes and rewrites the token);
- `/app/config.yaml` — mounted from `config.docker.yaml`;
- `/home/app/data` — logs, backups and the optional audit trail.

`MCP_AUTH_TOKEN` is required and should be passed as an environment variable.

## Notes

- A GHCR package created by a workflow starts private; make it public in the
  package settings if you want anonymous pulls.
- The image contains no credentials — they are mounted at runtime.
- The code is identical to 1.12.1: 67 tools, 8 prompts, 241 tests.

## Install without Docker

```bash
pip install workspace-operator-mcp==1.13.0
```
