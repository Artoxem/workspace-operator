# Workspace Operator 1.22.4

Documentation release. No tool behaviour changed.

## Added

- A short Gmail demo GIF at the top of the README: find the last message, read
  it, then move it to Trash. The recording is 1.99 MB, 1100 px wide, 62 frames.
- English and Russian captions explaining the 30-day Trash recovery.
- The screenshot guide now marks the hero capture as done.

## Why a release

PyPI renders the package description from the README of the published release.
The GIF and the refreshed documentation from 1.22.2–1.22.3 were only on GitHub,
so this release brings the PyPI page in sync.

## Compatibility

- 132 tools, profiles 132 / 113 / 39, 14 OAuth scopes.
- No code changes, no new scopes, no migration.
- 332 unit tests.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.22.4
# or
docker compose pull && docker compose up -d
```
