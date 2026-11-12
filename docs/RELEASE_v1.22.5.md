# Workspace Operator 1.22.5

Documentation release. No tool behaviour changed.

## Added

- A 1280×640 banner at the top of the README (English and Russian), above the
  intro and the demo GIF. It is a 117 KB JPEG, down from the original 1 MB PNG.
- The launch package now points at the optimized banner and lists every public
  asset with an absolute URL.

## Removed

- The original `workspace-operator.png` banner: superseded by the JPEG and no
  longer referenced anywhere.
- `docs/images/mcp-manager.png`: a DSH-local management page, not part of the
  server; its references in the screenshot guide and launch package are gone.
- Local build leftovers (`dist/`, egg-info, test bulk jobs, `__pycache__`) from
  the working tree; none of them were tracked.

## Changed

- `LEARN.md` rewritten for the current project: 132 tools across ten APIs, stdio
  and HTTP, profiles, plan → run → undo, current install and IDE commands.
- `docs/SCREENSHOTS.md` and `docs/LAUNCH_PACKAGE.md` now describe only shipped
  assets: the banner, the Gmail demo GIF, `doctor.png` and `docker-health.png`.

## Why a release

PyPI renders the package description from the README of the published version,
so the banner and the cleaned-up documentation reach the PyPI page only with a
new release.

## Compatibility

- 132 tools, profiles 132 / 113 / 39, 14 OAuth scopes.
- No code changes, no new scopes, no migration.
- 332 unit tests.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.22.5
# or
docker compose pull && docker compose up -d
```
