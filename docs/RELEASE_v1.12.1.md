# Release v1.12.1 — metadata fix

No functional changes. `v1.12.0` was tagged before the README was switched to the
PyPI install instructions, so the published package description still said
«not on PyPI yet» and «59 tools». PyPI file metadata is immutable, so the only way
to correct the project page is a new patch release.

## What is in this release

- the package is identical to 1.12.0 (67 tools, 8 prompts, 241 tests);
- the long description now matches the repository README: `pip install
  workspace-operator-mcp`, 67 tools, PyPI badge;
- `[project.urls]` now includes the PyPI project page.

## Install

```bash
pip install workspace-operator-mcp==1.12.1
```
