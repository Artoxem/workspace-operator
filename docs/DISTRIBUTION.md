# Distribution playbook

How to get Workspace Operator in front of people who run AI agents.

Ready-to-post copy and submission fields: [LAUNCH_PACKAGE.md](LAUNCH_PACKAGE.md).

Current baseline: 132 tools, 14 OAuth scopes, 328 unit tests, PyPI and GHCR
releases, MIT. Discovery is the bottleneck, not the feature set.

## 1. Positioning

Use one sentence everywhere:

> **Google Workspace automation for AI agents: 132 tools, local OAuth, and bulk
> operations that plan, confirm and undo.**

Three differentiators worth repeating:

1. **Breadth** — Drive, Docs, Sheets, Slides, Gmail, Calendar, Tasks, Forms,
   Apps Script and Postmaster in one server, not ten.
2. **Bulk with a safety net** — `plan → confirm → run → undo` for thousands of
   files or messages; a five-item sample, not a wall of text.
3. **Local and auditable** — stdio or Docker/HTTP on your machine, your OAuth
   client, read-only profile, JSONL audit, no hosted middleman.

Avoid claiming "the best" or "official". Compare honestly with Google's
remote MCP preview and single-service servers.

## 2. Asset checklist

- [x] GitHub description with the tool count and domains.
- [x] GitHub topics: `mcp`, `mcp-server`, `model-context-protocol`,
      `google-workspace`, `gmail`, `google-drive`, `google-sheets`,
      `google-docs`, `google-calendar`, `ai-agents`, `claude`, `cursor`,
      `automation`, `python`, `docker`.
- [x] Homepage points at PyPI.
- [ ] 30–60 second demo GIF at the top of the README: "move 500 files, then undo".
- [ ] 2-minute video for YouTube/X/LinkedIn.
- [ ] Two screenshots: a plan with counts, a finished job with undo.
- [ ] "Works with" line: Claude Desktop, Cursor, Continue, Cline, DeepSeek
      Harness, any MCP client.
- [ ] `CHANGELOG.md` and pinned release notes.

## 3. Tier 1: directories and registries

Do these once, then update on every release.

| Channel | What is needed | Notes |
|---|---|---|
| Official MCP Registry (`registry.modelcontextprotocol.io`) | `server.json`, `mcp-name:` line in the README of the published PyPI package, `mcp-publisher` CLI, GitHub login | Highest-leverage listing; namespace `io.github.Artoxem/workspace-operator` |
| Docker MCP Catalog | PR to `docker/mcp-registry` with a YAML entry pointing at `ghcr.io/artoxem/workspace-operator` | The image already exists; Docker Desktop users browse this catalog |
| Glama (`glama.ai/mcp/servers`) | GitHub repo; claim the auto-generated listing | Add screenshots and a clear description |
| PulseMCP (`pulsemcp.com`) | Submission form | Popular with MCP client users |
| mcp.so | Submission form | Broad directory, links to GitHub |
| Smithery (`smithery.ai`) | `smithery.yaml` or remote URL | Remote hosting is optional; a local server can still be listed |
| `punkpeye/awesome-mcp-servers` | Pull request adding one line under the right category | Follow the contribution format exactly |
| Awesome lists for Google Workspace automation | Small PRs | Use the same one-liner |

## 4. Tier 2: launch content

Sequence matters: listings first, then one launch spike, then steady content.

**Show HN** (Tuesday–Thursday, 08:00–10:00 US Eastern):

> Show HN: Workspace Operator – 132 Google Workspace tools for AI agents
>
> I built an MCP server that gives agents the whole Google Workspace, not just
> Gmail. The part I care about is bulk: moving 1,000 files is one plan, one
> confirmation and one background job, with an undo. It runs locally over your
> own OAuth client; there is a Docker image and a read-only profile.
>
> Source: https://github.com/Artoxem/workspace-operator

**Reddit** — r/mcp and r/LocalLLaMA. Lead with the problem, include the repo,
answer questions; never post the same text in several subreddits on one day.

**X/LinkedIn** — a 4-post thread:

1. the problem: agents read Gmail but cannot reorganise 5,000 files;
2. the demo GIF: plan, confirm, undo;
3. the architecture: local OAuth, profiles, audit, Docker;
4. the link and one command to install.

**Habr (RU)** — a technical article: "132 инструмента Google Workspace в одном
MCP-сервере: как безопасно делать массовые операции". Habr rewards depth and
honest benchmarks, not a link drop.

## 5. Content calendar (4 weeks)

| Week | Action |
|---|---|
| 1 | Finish assets (GIF, screenshots, video), submit to registries/directories |
| 2 | Launch: Show HN, Reddit, X thread, LinkedIn, Habr |
| 3 | Publish two recipes: "organize a photo archive with one prompt" and "bulk-label a year of email"; post to dev.to and Medium |
| 4 | Integrations: Claude Desktop, Cursor, Continue and Docker setup guides; collect issues, fix, publish a patch release |

Repeat with one post per week. A single launch is not distribution; discoverability
compounds through listings and repeated useful content.

## 6. Copy-paste descriptions

Short (one line):

> Google Workspace automation for AI agents: 132 MCP tools with bulk
> plan/confirm/undo for Drive, Gmail, Docs, Sheets and Slides.

Medium (directories):

> Workspace Operator is a local MCP server for Google Workspace. It exposes 132
> tools across Drive, Docs, Sheets, Slides, Gmail, Calendar, Tasks, Forms, Apps
> Script and Postmaster. Bulk operations resolve a selector once, show a
> five-item plan, then run in the background with progress, cancellation, a
> result artifact and undo. Runs over stdio or Docker/HTTP with your own OAuth
> client; read-only and read-write profiles plus JSONL audit.

Install lines:

```bash
pip install workspace-operator-mcp
docker pull ghcr.io/artoxem/workspace-operator:1.22.1
```

## 7. Metrics

- PyPI downloads: `https://pypistats.org/packages/workspace-operator-mcp`
- GitHub: stars, forks, traffic (Insights → Traffic), clones.
- GHCR pulls and Docker Hub if mirrored.
- Issues and discussions: quality signal, not just counts.

Track weekly in a simple table; double down on the channel that produces
installs, not impressions.

## 8. Guardrails

- One post per community per launch; no cross-posting identical text.
- Disclose that you are the author.
- Never imply official Google affiliation.
- Keep security claims precise: local OAuth, scopes, read-only profile, audit,
  but no "unhackable" language.
- Respond to every issue in the first week; a small project wins on support.
