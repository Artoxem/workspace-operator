# Publishing Workspace Operator

The package name is **`workspace-operator-mcp`** (checked free on PyPI on
2026-11-06). The version lives in two places and they must match:

- `pyproject.toml` → `[project] version`
- `workspace_operator/__init__.py` → `__version__`

## Before every release

```bash
python -m unittest discover -s tests -v     # 241 tests, no network
python tests/live_smoke.py                  # 51 checks, needs a Google account
python -m build                             # sdist + wheel into dist/
python -m twine check dist/*                # optional, needs twine
```

Tag and push:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z — summary"
git push origin master && git push origin vX.Y.Z
```

## Option A — Trusted Publishing (recommended, no tokens)

The workflow `.github/workflows/python-publish.yml` publishes on
`release: published` using OpenID Connect.

1. On PyPI: **Publishing → Add a new pending publisher**
   - PyPI project name: `workspace-operator-mcp`
   - Owner: `Artoxem`
   - Repository: `workspace-operator`
   - Workflow name: `python-publish.yml`
   - Environment: `pypi`
2. On GitHub: **Settings → Environments → New environment** named `pypi`.
3. Create a release from the tag (**Releases → Draft a new release → tag vX.Y.Z**).
4. The workflow builds the distributions and uploads them; the new project page
   appears at `https://pypi.org/project/workspace-operator-mcp/`.

No repository secrets are needed.

## Option B — API token

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*        # username: __token__, password: the token
```

Use a project-scoped token, and delete it after the release.

## Docker image

`.github/workflows/docker-publish.yml` builds and pushes
`ghcr.io/artoxem/workspace-operator` on every `v*` tag push (and on manual
dispatch):

- tags: `X.Y.Z`, `X.Y`, `latest`, plus the commit sha;
- platforms: `linux/amd64`, `linux/arm64`;
- authentication: the built-in `GITHUB_TOKEN` — no secrets required.

A new package starts **private** even in a public repository. To let anyone pull
it: GitHub → your profile → **Packages** → `workspace-operator` → *Package settings*
→ **Change visibility** → Public.

## After the first publication

1. Verify from a clean environment:
   ```bash
   python -m pip install workspace-operator-mcp
   workspace-operator version
   workspace-operator doctor --offline
   ```
2. Switch the README quick start from «install from source» to
   `pip install workspace-operator-mcp` and keep the git clone as the
   development path.
3. Add the PyPI badge to both READMEs.

## Rolling back

PyPI does not allow re-uploading the same version. If a release is broken:
`yank` it on PyPI (project → Releases → Options → Yank), fix, and publish the
next patch version. Never reuse a version number.

## Checklist

- [ ] versions match in `pyproject.toml` and `__init__.py`
- [ ] tests green, live smoke green
- [ ] `python -m build` produces both artifacts
- [ ] tag pushed
- [ ] pending publisher / token ready
- [ ] release created → workflow green
- [ ] `pip install` works in a clean environment
