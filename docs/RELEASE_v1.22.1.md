# Workspace Operator 1.22.1

Distribution metadata release. No tool behaviour changed.

## Added

- `server.json` for the official MCP Registry namespace
  `io.github.Artoxem/workspace-operator`, with the PyPI package descriptor.
- `mcp-name: io.github.Artoxem/workspace-operator` in the README. The registry
  verifies PyPI ownership through this token in the published package
  description, so it ships with this release.
- OCI label `io.modelcontextprotocol.server.name` in the Dockerfile for the
  registry's container ownership check.
- GitHub topics and homepage URL, so the repository is discoverable through
  search.
- `docs/DISTRIBUTION.md`: a concrete channel checklist, launch copy and a
  four-week content plan.

## Why a patch release

The MCP Registry checks the README of the package currently on PyPI. Version
1.22.0 was published before the `mcp-name` token existed, so 1.22.1 exists to
carry the metadata. Tooling is identical.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.22.1
# or
docker compose pull && docker compose up -d
```

## Verification

- 328 unit tests.
- `docker build` and the published image remain unchanged apart from labels.
- Registry publish is a separate interactive step (`mcp-publisher login github`
  then `mcp-publisher publish`).
