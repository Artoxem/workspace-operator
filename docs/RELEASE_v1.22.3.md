# Workspace Operator 1.22.3

Bug fix: Gmail delete tools no longer require a scope the server does not ask
for. No new scopes, no migration.

## Fixed

`delete_email` and `batch_delete_emails` called Gmail's permanent-delete
endpoints (`messages.delete`, `messages.batchDelete`). Those require the full
`https://mail.google.com/` scope. The default configuration uses
`gmail.modify`, which deliberately excludes permanent deletion, so the tools
failed with:

```
403 insufficientPermissions
```

Both tools now move messages to **Trash** instead:

- `delete_email(message_id, confirm=true)` calls `messages.trash`.
- `batch_delete_emails(message_ids, dry_run=false)` calls `messages.batchModify`
  with `addLabelIds: ["TRASH"]`, in chunks of 1,000.
- `dry_run` stays on by default for the batch tool.
- Messages remain recoverable in Gmail for 30 days.

Permanent deletion is not exposed. It would require the
`https://mail.google.com/` scope, which the default configuration intentionally
does not request.

## Documentation

Tool descriptions in the README, the tool reference (EN/RU) and the server
catalog now say "move to Trash" instead of "delete".

## Compatibility

- 132 tools, profiles unchanged.
- No new OAuth scopes; no re-authorization.
- Tool names and arguments are unchanged.
- 332 unit tests, including four new trash-behaviour tests.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.22.3
# or
docker compose pull && docker compose up -d
```
