# Screenshot plan

Screenshots are for trust and orientation, not decoration. Each one should answer
a question a new user has at that point in the README or setup guide.

Save originals in `docs/images/` as PNG, width 1440–1600 px. Retina/2x is welcome
but keep each file under ~500 KB. Dark UI matches the README's tone; light UI is
acceptable for Google Cloud screens.

## Shot list

### 1. Hero: plan, confirm, undo

**Status: captured** as `docs/images/gmail-demo.gif`. The recording shows finding
and reading the last message, then moving it to Trash (recoverable). A bulk
plan → undo recording is still desirable for the bulk section.

**Question it answers:** "What does this thing actually do that a chat client
cannot?"

- Split the screen or take three sequential crops:
  1. user prompt: «Перемести все фотографии из корня Drive в папку ФОТО, сначала
     покажи план»;
  2. the `bulk_plan` answer: matched count, total size, five sample names and the
     confirm prompt;
  3. `bulk_status` after confirmation: `completed`, `succeeded: N`, `failed: 0`,
     plus the `bulk_undo` next step.
- Crop to the conversation column; 1200–1400 px wide.
- File: `docs/images/hero-bulk-plan.png` (or a 15–25 s GIF, see below).
- Used in: README, directly under the intro paragraph.

**Redact:** account email, any real customer names, file names with personal
data, tokens.

### 2. Client connected

**Question:** "Will my editor see the server and its tools?"

- Open the MCP settings of the client you document (Cursor, Claude Desktop,
  VS Code, DSH). Show the `workspace-operator` row as connected/enabled and the
  tool count or tool list.
- File: `docs/images/client-connected.png`.
- Used in: README "Connect a client" and `docs/IDE_SETUP.md`.

**Redact:** other servers, account names, paths containing a username.

### 3. Google Cloud APIs

**Question:** "Which APIs do I enable?"

- **APIs & Services → Enabled APIs & services**, filtered to the ten APIs from
  `AUTH_SETUP.md`.
- File: `docs/images/cloud-apis.png`.
- Used in: `docs/AUTH_SETUP.md`, Step 2.

**Redact:** project name and project ID if you prefer; they are not sensitive but
add noise.

### 4. OAuth consent

**Question:** "What will Google ask me to approve?"

- The account chooser plus the consent screen with the scope list, or the
  "app isn't verified → Advanced" screen.
- File: `docs/images/oauth-consent.png`.
- Used in: `docs/AUTH_SETUP.md`, Step 6.

**Redact:** the email address in the account chip; blur it or use a test account.

### 5. Docker healthy

**Question:** "Did the container start correctly?"

- Terminal with `docker compose ps` showing `Up (healthy)` and
  `curl http://127.0.0.1:8765/healthz` returning `"version":"1.22.2"`.
- File: `docs/images/docker-health.png` — **captured**.
- Used in: README Docker section and `docs/TROUBLESHOOTING.md`.

**Redact:** hostname, username in the prompt, any token.

### 6. Doctor output

**Question:** "How do I know OAuth and scopes are fine?"

- Terminal running `workspace-operator doctor`: token check, scope comparison,
  API probes with `ok` marks.
- File: `docs/images/doctor.png` — **captured** (username redacted).
- Used in: `docs/AUTH_SETUP.md`, Step 8.

**Redact:** token path containing a username, email in API probe output.

### 7. Optional: bulk job result

**Question:** "What does a finished 1,000-file job look like?"

- `bulk_status` with `done/total`, `succeeded`, `failed`, `percent` and the
  result file path.
- File: `docs/images/bulk-status.png`.
- Used in: bulk operations section of the README.

## GIF instead of a static hero

A 15–25 second GIF converts better than three screenshots:

1. ask to move photos;
2. plan appears with counts and sample;
3. confirm;
4. progress reaches 100%;
5. `bulk_undo` returns the files.

Tools: **ScreenToGif** (Windows, free) or **LICEcap**. Record at 1200×720,
10–15 fps, then trim idle frames. Keep it under 5 MB; GitHub renders GIFs inline.
File: `docs/images/bulk-demo.gif`.

## Capture checklist

- [ ] Window width at least 1280 px; hide bookmarks bar and unrelated tabs.
- [ ] Dark theme for product UI; default light theme for Google Cloud is fine.
- [ ] Close notifications, Slack/Telegram popups and personal windows.
- [ ] Use a test folder with synthetic names (`photo-001.jpg`, `Client A`), not
      real customer data.
- [ ] Capture with `Win+Shift+S` (region) or Snipping Tool → **Window** mode.
- [ ] Crop empty margins; keep the relevant UI and captions readable.
- [ ] Redact emails, tokens, project IDs, file paths with usernames.
- [ ] Export PNG (screenshots) or GIF (demo), not JPEG.
- [ ] Add alt text and a one-line caption in the document where it is used.

## Placement map

| Image | Where |
|---|---|
| `hero-bulk-plan.png` or `bulk-demo.gif` | README, after the intro |
| `client-connected.png` | README "Connect a client", IDE_SETUP |
| `cloud-apis.png` | AUTH_SETUP, Step 2 |
| `oauth-consent.png` | AUTH_SETUP, Step 6 |
| `docker-health.png` | README Docker, TROUBLESHOOTING |
| `doctor.png` | AUTH_SETUP, Step 8 |
| `bulk-status.png` | README bulk/operations section |

## Captured so far

Two real captures are in the repository and already used in the docs:

| File | What it shows |
|---|---|
| `docs/images/gmail-demo.gif` | chat demo: find the last message, read it, move it to Trash |
| `docs/images/doctor.png` | `workspace-operator doctor`: token, scopes, API probes, `configuration looks good` |
| `docs/images/docker-health.png` | `docker compose ps` healthy and `/healthz` returning `1.22.2` |

Both were rendered from the real command output; the Windows username was replaced
with `you` before rendering.

## What to send back

Put raw screenshots in `docs/images/` (or any folder) and say which ones they
are. I will crop, redact, add alt text and insert them into the README, AUTH_SETUP
and IDE_SETUP, and optimize the GIF size.
