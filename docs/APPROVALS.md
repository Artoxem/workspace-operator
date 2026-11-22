# Human approval for destructive actions

Workspace Operator keeps destructive tools available to the agent, but the
server does not execute them until a human approves the exact call.

This is a server-side gate, not a request in the prompt. The agent can still ask
to delete something; it cannot approve its own request.

## Flow

1. The agent calls a destructive tool, for example:

   ```json
   {"name": "drive_trash", "arguments": {"file_id": "..."}}
   ```

2. If the client supports MCP elicitation, the server asks the human in the
client UI: **Approve this action?** Accepting runs it once; declining cancels it.

   If the client does not support elicitation, the server does **not** touch
   Drive and returns a normal tool result with an `approval_id`:

   ```text
   ⚠️ APPROVAL REQUIRED — the action has NOT run.
   {"status": "approval_required", "approval_id": "apr_…", ...}
   ```

3. The operator decides outside the chat, in the CLI or on the browser page (see
   below). The tool result that reaches the agent carries no commands and no
   link, so the agent cannot release the call by itself.

   ```bash
   workspace-operator approvals list
   workspace-operator approvals show apr_…
   workspace-operator approvals approve apr_…
   # or deny
   workspace-operator approvals deny apr_…
   ```

4. The agent retries the **same** call with the id:

   ```json
   {"name": "drive_trash", "arguments": {
     "file_id": "...",
     "approval_id": "apr_…"
   }}
   ```

5. The server verifies and consumes the approval, then executes the action once.

A successful result is returned as a normal tool result. Pending, denied,
expired, reused or mismatched approval is also returned as a normal result with
instructions — the MCP session does not crash. The decision link is written to the
server log (the operator's console), never into a tool result.

## Binding and expiry

An approval is bound to:

- the tool name;
- the `action` (for consolidated tools);
- a SHA-256 hash of all arguments except `approval_id` and `confirm`;
- an expiry time (default 15 minutes, `approval_ttl`).

Changing the file id, plan id, range or any other argument invalidates the
approval. Approvals are one-time: after execution the id cannot be reused.
`confirm=true` is still accepted as an intent flag, but it is not sufficient by
itself; the human approval is what releases the action.

## CLI

```bash
workspace-operator approvals list          # pending requests
workspace-operator approvals show apr_…    # details for one request
workspace-operator approvals link apr_…    # browser link (contains a secret)
workspace-operator approvals approve apr_… # allow exactly this call
workspace-operator approvals deny apr_…    # block it
```

The approval store is `~/.google/approvals` by default: the same folder as the
token. The CLI finds it from any working directory, and the container gets the
same folder through the credentials mount, so the host CLI and the container
see the same requests:

```bash
workspace-operator approvals list
```

Or run it inside the container:

```bash
docker compose exec workspace-operator workspace-operator approvals list
```

## Configuration

```yaml
# approval_dir: "~/.google/approvals"  # optional; this is the default
approval_ttl: 900               # seconds
approval_url: "http://127.0.0.1:8765"  # browser page base
```

Environment: `MCP_APPROVAL_DIR`, `MCP_APPROVAL_TTL`, `MCP_APPROVAL_URL`. Set
`approval_dir` only to move the queue, and use an absolute path: a relative one
is resolved from the current folder.

## Open new requests automatically

For HTTP, set `MCP_APPROVAL_BROWSER_WAIT=45` on the server (in `.env` for Docker
Compose). On the operator's desktop, **outside the container**, run
`workspace-operator approvals watch` and leave it running. It must have access to
the same queue; use `--url BASE_URL` for a custom approval page URL. The helper
opens requests created after it starts. Approve resumes a waiting call and Deny
stops it. If the wait has elapsed, tell the agent your decision after clicking.
The automatic browser link is not sent to the MCP client or written to the server log.

## Reviewing Drive moves and uploads

- **Move**: call `bulk_plan` with `domain=drive`, `action=move`, `selector.ids`
  (one or more file IDs), and `options.target_folder_id`. Review the plan and call
  `bulk_run` with its ID. The browser shows the destination and **every file**
  with its original folder(s). There is no direct single-file move action.
- **Upload**: use `drive_write` with `action=upload` and `local_path`. The review
  shows the local source, upload name, output type, size and destination (My Drive
  root unless a parent is specified). The server checks the approved bytes again
  before sending them. The limit is 100 MiB per file.
- Use the browser page or `workspace-operator approvals show <id>` to see the
  full review: the agent sees only a compact summary. Review these operations
  outside the MCP elicitation dialog. If the server stopped waiting, retry only
  after the operator decides. Changed data may require a fresh approval.
- Shared drive access is opt-in with `MCP_BULK_ALLOW_SHARED_DRIVES=1`. Moves stay
  within My Drive or within a single shared drive and require the applicable
  permissions. Cross-drive and folder-tree moves are not supported. To reverse a
  move, use `previous_parents` from `bulk_result` to create fresh reviewed plans.

## Browser page

The browser page is optional and requires the HTTP transport. Each approval has
a random **secret** stored only in the approval record, and only its hash is kept
on disk. The agent never sees the secret: the tool result carries the
`approval_id` and no link. The human obtains the link locally:

```bash
workspace-operator approvals link apr_…
# http://127.0.0.1:8765/approvals/apr_…?k=<secret>
```

The page and the Approve/Deny POST both require the secret (constant-time
comparison). POSTs are additionally rejected when the `Origin` header does not
match the `Host` (CSRF), and pages are served with `no-store`,
`Referrer-Policy: no-referrer`, a restrictive CSP and `X-Frame-Options: DENY`.
Unknown ids and wrong secrets get the same 404 answer. After approving, return
to the chat and tell the agent to retry with the `approval_id`.

Without the secret, an agent that knows the `approval_id` and the server URL
cannot approve its own request over HTTP. Do not expose the HTTP server to an
untrusted network without a TLS proxy: the secret travels in the URL.

## What is gated

`confirm=true` + human approval applies to:

`drive_trash`, `drive_permissions`, `docs_edit`, `sheets_delete`,
`gmail_delete`, `calendar_delete`, `script_run`, `bulk_run`, `bulk_undo`.
`drive_write` → `upload` also requires human approval; `confirm=true` is not necessary.

Reads, ordinary writes, drafts and `dry_run` previews do not require approval.
`bulk_plan` is always a dry run; the approval is requested when `bulk_run`
executes the reviewed plan.

## Threat model

Approval protects against an agent acting alone through MCP. It does not protect
against an agent that can run arbitrary local commands or read the approval
directory (`~/.google/approvals/*.json` holds the secrets) outside MCP, nor against
a human who approves a call without reading its summary. Keep the approval
directory local, run the CLI as the same user as the server, and do not expose
the MCP endpoint to untrusted users.
