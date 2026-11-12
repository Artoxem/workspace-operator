# Launch package

Copy-paste material for directories and launch posts. Everything here is written
for the current release, 1.22.4. Update the version in install lines before
posting a newer release.

## One-liners

**Short (≤ 100 chars)**

> Google Workspace automation for AI agents: 132 tools, safe bulk operations, undo.

**Medium**

> Workspace Operator is a local MCP server for Google Workspace. 132 tools across
> Drive, Docs, Sheets, Slides, Gmail, Calendar, Tasks, Forms, Apps Script and
> Postmaster, with bulk operations that plan, confirm and undo. MIT, stdio or
> Docker.

**Long**

> Workspace Operator is an open-source MCP server that gives AI agents the whole
> Google Workspace instead of a single API. It exposes 132 tools across Drive,
> Docs, Sheets, Slides, Gmail, Calendar, Tasks, Forms, Apps Script and Postmaster.
> Bulk changes use a plan → confirm → run → undo flow: resolve the selector once,
> review counts and a five-item sample, then run in the background with progress,
> cancellation and a result artifact. Runs locally over your own OAuth client,
> over stdio or in a loopback-only Docker container, with read-only / read-write /
> full profiles and a JSONL audit log. MIT licensed.

## Links

- GitHub: https://github.com/Artoxem/workspace-operator
- PyPI: https://pypi.org/project/workspace-operator-mcp/
- Release: https://github.com/Artoxem/workspace-operator/releases/tag/v1.22.4
- Registry: https://registry.modelcontextprotocol.io/v0/servers?search=workspace-operator
- Security / deployment: https://github.com/Artoxem/workspace-operator/blob/master/docs/SECURITY.md

Install lines:

```bash
pip install workspace-operator-mcp
docker pull ghcr.io/artoxem/workspace-operator:1.22.4
```


## Assets

Use absolute URLs so the same asset works on GitHub, PyPI and directory pages.

| Asset | URL | Use |
|---|---|---|
| Banner | https://raw.githubusercontent.com/Artoxem/workspace-operator/master/docs/images/workspace-operator-banner.jpg | README hero, social preview, directory cards |
| Gmail demo GIF | https://raw.githubusercontent.com/Artoxem/workspace-operator/master/docs/images/gmail-demo.gif | Show HN/Reddit/X, Glama |
| Doctor screenshot | https://raw.githubusercontent.com/Artoxem/workspace-operator/master/docs/images/doctor.png | AUTH_SETUP, PulseMCP |
| Docker health | https://raw.githubusercontent.com/Artoxem/workspace-operator/master/docs/images/docker-health.png | Docker section, mcp.so |

## Directory submissions

### Glama

- URL: https://glama.ai/mcp/servers
- Status: **claim the auto-generated listing** (GitHub login), then improve it.
- Repository field: `https://github.com/Artoxem/workspace-operator`
- Description: use the **long** copy above.
- Categories/tags: `google-workspace`, `gmail`, `google-drive`, `google-sheets`,
  `productivity`, `automation`, `mcp`.
- Add the banner, the Gmail demo GIF and the terminal screenshots from
  `docs/images/` (see Assets above).
- Note: Glama may already index the repository; search by name before creating a
  duplicate.

### PulseMCP

- URL: https://www.pulsemcp.com/submit
- Name: `Workspace Operator`
- Description: **medium** copy.
- Repository: GitHub link.
- Install command: `pip install workspace-operator-mcp`
- Transport: `stdio` (HTTP is optional, local only)
- Category: productivity / Google Workspace.
- Tags: same as Glama.

### mcp.so

- URL: https://mcp.so/submit
- Name: `Workspace Operator`
- Description: **medium** copy.
- GitHub: repository link.
- Install: `pip install workspace-operator-mcp` or the Docker image.
- Mention Python 3.10+, MIT, and the 132-tool count.

### Smithery

**Do not submit.** Smithery's proxy, CLI and managed identity shut down on
31 October 2026; only a non-proxied directory remains. Its old `smithery.yaml`
flow no longer applies.

### Docker MCP Catalog

- Repository: https://github.com/docker/mcp-registry
- Status: **hold, do not submit yet.** A local catalog entry expects
  environment/secret configuration; Workspace Operator additionally needs a
  read-write mount with `oauth.keys.json` and a token that the server refreshes
  in place. The catalog format does not cleanly express that volume, so a
  submission now would be rejected or unusable for Docker Desktop users.
- Prerequisite for a future submission: a wrapper image that performs the Google
  consent flow inside the container (or a catalog schema that supports the token
  volume). The image, Dockerfile and `ghcr.io` release already satisfy the other
  requirements.

### awesome-mcp-servers

- Repository: https://github.com/punkpeye/awesome-mcp-servers
- Category: **Workplace & Productivity**.
- Add this line (alphabetical placement, near the other `A` entries):

```markdown
- [Artoxem/workspace-operator](https://github.com/Artoxem/workspace-operator) 🐍 ☁️ 🍎 🪟 🐧 - 132 Google Workspace tools with bulk plan/confirm/undo for Drive, Gmail, Docs, Sheets, Slides, Calendar, Tasks, Forms and Apps Script.
```

PR title: `Add Workspace Operator to Workplace & Productivity`.
PR body: one paragraph with the long description, install command and the
`docs/SECURITY.md` link. Keep the diff to one line.

## Launch posts

### Show HN

Title:

> Show HN: Workspace Operator – 132 Google Workspace tools for AI agents

Body:

> I built an MCP server that gives an agent the whole Google Workspace, not just
> Gmail or Drive alone.
>
> The part I care about is bulk work. Moving 1,000 files should be one plan, one
> confirmation and one background job with an undo — not 1,000 tool calls. The
> server resolves a selector once, shows the count and a five-item sample, then
> executes with progress, cancellation, a result file and a reverse job. Trash is
> reversible; public sharing needs an explicit second flag.
>
> It runs locally with your own OAuth client, over stdio or a loopback-only
> Docker container. There are read-only / read-write / full profiles, a JSONL
> audit log, and 132 tools across Drive, Docs, Sheets, Slides, Gmail, Calendar,
> Tasks, Forms, Apps Script and Postmaster.
>
> MIT, Python, 332 tests. Source: https://github.com/Artoxem/workspace-operator

Post Tuesday–Thursday, 08:00–10:00 US Eastern. Reply to every comment for the
first three hours.

### Reddit — r/mcp

Title:

> I built a Google Workspace MCP server with bulk plan/confirm/undo (132 tools, MIT)

Body:

> Most Google Workspace servers stop at reading mail or listing files. I wanted
> an agent that can actually reorganise a workspace safely, so I built Workspace
> Operator.
>
> What is different:
> - 132 tools across ten Google APIs, in one server.
> - Bulk operations: `bulk_plan` resolves a selector and shows counts + a sample;
>   `bulk_run` executes in the background; `bulk_status` reports progress;
>   `bulk_undo` reverses moves, renames and trashes.
> - Read-only profile, audit log, caps and protected ids.
> - stdio for one client, Docker/HTTP for several clients — one Google account per
>   instance.
>
> Install: `pip install workspace-operator-mcp`
> Repo: https://github.com/Artoxem/workspace-operator
>
> Demo GIF: https://raw.githubusercontent.com/Artoxem/workspace-operator/master/docs/images/gmail-demo.gif
>
> Feedback welcome, especially on the bulk safety model.

### Reddit — r/LocalLLaMA

Title:

> Local Google Workspace MCP server: 132 tools, bulk file operations with undo

Angle: local OAuth, no hosted middleman, Docker on loopback, read-only profile,
what runs where. Link the same repository, mention 332 tests and MIT.

### X / LinkedIn thread

1. Agents can read Gmail. Reorganising 5,000 files is where they break. I built
   an MCP server for that.
2. One plan, one confirmation, one background job: move, rename, trash and undo
   across Google Drive — plus batch Gmail actions.
3. 132 tools, ten Google APIs, read-only profile, audit log, local OAuth, Docker.
   MIT.
4. `pip install workspace-operator-mcp` · https://github.com/Artoxem/workspace-operator

Attach the Gmail demo GIF (`docs/images/gmail-demo.gif`) and the banner. A bulk
plan/undo recording is still desirable for the bulk section, but not required
for the first launch.

### Habr (RU)

Title:

> 132 инструмента Google Workspace в одном MCP-сервере: как безопасно делать
> массовые операции

Structure:

1. Проблема: агент умеет читать почту, но не может разложить 5 000 файлов.
2. Почему 10 000 отдельных tool calls — плохо: время, токены, отсутствие отката.
3. Решение: план → подтверждение → фоновая задача → откат.
4. Архитектура: локальный OAuth, stdio/Docker, профили, аудит, лимиты.
5. Цифры: 100 файлов за ~9 секунд, 132 инструмента, 332 теста.
6. Ограничения: один Google-аккаунт на инстанс, не multi-tenant.
7. Ссылки на GitHub, PyPI и SECURITY.md.

## Posting checklist

- [ ] Update the version in install lines if a newer release exists.
- [ ] Use a test folder with synthetic names for any screenshots.
- [ ] One post per community per day; no identical cross-posting.
- [ ] Disclose authorship.
- [ ] Do not claim Google affiliation or "official".
- [ ] Reply to comments and issues for the first week.
- [ ] Track installs and traffic in `pypistats` and GitHub Insights → Traffic.
