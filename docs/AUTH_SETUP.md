# Google OAuth setup

Workspace Operator uses Google's **installed application** flow: you click
**Allow** in a browser once, the token is saved locally, and the server refreshes
it automatically afterwards. No service account and no shared server is needed.

Budget about ten minutes. You only repeat this when you add scopes or move to a
new machine.

## What you need

- A Google account.
- A Google Cloud project (the free tier is enough).
- Python 3.10+ with the package installed, or the Docker image.
- A browser for the first authorization.

## Two secrets, do not mix them up

| Secret | What it is | Where it comes from |
|---|---|---|
| `oauth.keys.json` | OAuth **client** credentials (client id + secret) | Google Cloud Console, downloaded once |
| `token.json` | OAuth **token** with the granted scopes | Created by the browser consent flow |
| `mcp_auth_token` | Local MCP bearer string, not a Google credential | You generate any long random string |

`token.json` is the file that gives the server access to your Google account.
`mcp_auth_token` only gates the MCP server itself and is used as the HTTP
`Authorization: Bearer` value. Rotating `mcp_auth_token` does not require Google
re-authorization, and deleting `token.json` does not change `mcp_auth_token`.

## Step 1 — Create or select a project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Pick a project from the top bar, or click **New Project**.
3. Give it a name such as `workspace-operator` and create it.

## Step 2 — Enable APIs

**APIs & Services → Library**, then enable:

| API | Needed for |
|---|---|
| Google Drive API | files, folders, permissions |
| Google Docs API | documents |
| Google Sheets API | spreadsheets |
| Google Slides API | presentations |
| Gmail API | mail, labels, filters |
| Google Calendar API | events |
| Google Apps Script API | script projects, deployments |
| Google Tasks API | task lists and tasks |
| Google Forms API | forms and responses |
| Gmail Postmaster Tools API | domain deliverability (optional) |

Postmaster is optional and only returns data for domains you have verified in
Search Console and registered in Postmaster Tools.

> Enabling an API and granting an OAuth scope are two different switches. The
> API must be enabled in the project, and the user must approve the scope in
> the consent screen. The server asks for all scopes in `config.yaml`.

## Step 3 — Configure the consent screen

1. **APIs & Services → OAuth consent screen**.
2. Choose **External** if you use a personal Google account.
3. Fill in **App name**, **User support email** and **Developer contact email**.
4. While the app is in **Testing**, add your own account under **Test users**.
5. You do not need to add scopes manually here: the server requests the ones
   listed in `config.yaml` during authorization.

Publishing the app is not required for personal use. The "app is not verified"
warning is expected in Testing mode.

## Step 4 — Create the OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**.
3. Name it, for example `workspace-operator desktop`.
4. Click **Create**, then **Download JSON**.

## Step 5 — Put the files in place

Create a private folder and save the downloaded JSON as `oauth.keys.json`:

- Linux/macOS: `~/.google/oauth.keys.json`
- Windows: `C:\Users\<you>\.google\oauth.keys.json`

`token.json` will appear in the same folder after the first authorization.
Do not commit either file; both are in `.gitignore`.

Configure the paths in `config.yaml`:

```yaml
client_secrets_file: "/home/you/.google/oauth.keys.json"
token_file: "/home/you/.google/token.json"
backup_dir: "/home/you/.google/backups"
```

Windows example:

```yaml
client_secrets_file: "C:/Users/you/.google/oauth.keys.json"
token_file: "C:/Users/you/.google/token.json"
```

Environment overrides also work: `GOOGLE_CLIENT_SECRETS_FILE`, `GOOGLE_TOKEN_FILE`,
`GOOGLE_BACKUP_DIR`, and `MCP_CONFIG_FILE` to point at the YAML file.

## Step 6 — Authorize once

### stdio or a local server

```bash
workspace-operator doctor
```

The first run opens a browser. Sign in, review the scopes, click **Allow**. The
token is written to `token_file`. `doctor` then checks the token, the granted
scopes and a few live APIs.

You can also simply start the server — the same flow runs on the first tool call
that needs Google:

```bash
workspace-operator serve
```

### Docker or a headless machine

A container cannot open a browser. Authorize on a machine that has one:

1. Run `workspace-operator doctor` on the desktop machine, complete the consent.
2. Copy `token.json` into the same folder as `oauth.keys.json` on the server.
3. Mount that folder **read-write** into the container, for example
   `-v "$HOME/.google:/home/app/.google"`.

The read-write mount matters: the server refreshes the token in place. A
read-only mount will fail as soon as the access token expires.

### The "app isn't verified" screen

Expected for a personal app in Testing mode. Click **Advanced → Go to
workspace-operator (unsafe)** only if you created this OAuth client yourself.

## Step 7 — Scopes

The default configuration requests 14 scopes (Drive, Docs, Sheets, Slides,
Gmail, Calendar, Apps Script, Tasks, Forms, Postmaster). The full list and the
read-only variants live in [SECURITY.md](SECURITY.md).

To narrow access, edit `scopes:` in `config.yaml`, delete `token.json` and run
`workspace-operator doctor` again. The doctor compares configured scopes with
granted scopes and prints the missing ones instead of leaving you with a silent
403.

Re-authorize whenever you:

- add or remove scopes;
- upgrade across a major release that added scopes;
- move to another machine or copy the project to a new Google account.

The procedure is always the same: delete `token.json`, run
`workspace-operator doctor`, approve the browser prompt.

## Step 8 — Verify

```bash
workspace-operator version
workspace-operator doctor
```

A healthy setup shows the token, a matching scope list and reachable APIs. If an
API probe fails with `403 insufficientPermissions`, the token predates that
scope: re-authorize.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `FileNotFoundError: Client secrets file not found` | Check `client_secrets_file`; use an absolute path and forward slashes on Windows |
| Browser never opens, URL printed instead | Open the URL manually; on SSH use the desktop-machine flow above |
| `Access blocked: This app's request is invalid` | Consent screen is not configured, or you are not a test user |
| `403 insufficientPermissions` | Token lacks a scope; delete `token.json` and re-authorize |
| `invalid_grant` / token expired | Delete `token.json` and authorize again |
| Docker works, then fails after an hour | The Google folder is mounted read-only; remount read-write |
| Postmaster returns an empty list | No verified domain yet; add it in Search Console and Postmaster Tools |

More failure modes: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Security notes

- Never commit `oauth.keys.json` or `token.json`.
- The token can do everything the granted scopes allow. Prefer the `read-only`
  profile and read-only scopes when you do not need writes.
- Keep `mcp_auth_token` random and out of git; it is the HTTP bearer value.
- The audit log records tool names and argument names, never values.
