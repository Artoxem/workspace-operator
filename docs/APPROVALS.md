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

2. If the client supports MCP elicitation, the server asks the user directly in
the chat: **Approve this action?** Accepting runs it once; declining cancels it.

   If the client does not support elicitation, the server does **not** touch
   Drive and returns a normal tool result with an `approval_id`:

   ```text
   ⚠️ APPROVAL REQUIRED — the action has NOT run.
   {"status": "approval_required", "approval_id": "apr_…", ...}
   ```

3. In the fallback flow, the agent shows that id to the user, who approves locally:

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

A successful result is returned as a normal tool result. The in-chat dialog is
the preferred path; the CLI fallback is used only when the client does not
advertise elicitation. Pending, denied, expired, reused or mismatched approval
is also returned as a normal result with instructions — the MCP session does not
crash.

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
workspace-operator approvals approve apr_… # allow exactly this call
workspace-operator approvals deny apr_…    # block it
```

The CLI reads the same configuration as the server. In Docker, the approval
directory is mounted with the data directory:

```bash
# on the host, next to docker-compose.yml
MCP_APPROVAL_DIR=./data/approvals workspace-operator approvals list
```

Or run it inside the container:

```bash
docker compose exec workspace-operator workspace-operator approvals list
```

## Configuration

```yaml
approval_dir: "data/approvals"  # container: /home/app/data/approvals
approval_ttl: 900               # seconds
```

Environment: `MCP_APPROVAL_DIR`, `MCP_APPROVAL_TTL`.

## What is gated

`confirm=true` + human approval applies to:

`drive_trash`, `drive_permissions`, `docs_edit`, `sheets_delete`,
`gmail_delete`, `calendar_delete`, `script_run`, `bulk_run`, `bulk_undo`.

Reads, ordinary writes, drafts and `dry_run` previews do not require approval.
`bulk_plan` is always a dry run; the approval is requested when `bulk_run`
executes the reviewed plan.

## Threat model

Approval protects against an agent acting alone through MCP. It does not protect
against an agent that can run arbitrary local commands outside MCP, nor against
a human who approves a call without reading its summary. Keep the approval
directory local, run the CLI as the same user as the server, and do not expose
the MCP endpoint to untrusted users.
