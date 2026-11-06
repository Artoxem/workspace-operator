# Release v1.12.0 — scenario prompts

Prompts are the one part of MCP that clients surface as a menu, so they double as
the product's «recipes». Four universal scenarios were added; none of them assumes
which account, table or mailbox is behind them.

## New prompts

| Prompt | Arguments | What the model gets |
|---|---|---|
| `weekly_review` | `days_back` (7) | One digest across mail, changed files and the coming agenda, with review instructions |
| `inbox_triage` | `query`, `max_results` (15) | A mail slice plus a triage frame: reply today / waiting / informational / archive |
| `sheet_brief` | `spreadsheet_id`, `range` | Column statistics from any range, plus briefing questions — **no document created** |
| `compare_brief` | `spreadsheet_id`, `range_a`, `range_b`, `key_column` | The diff of two ranges, framed as a reconciliation report |

Existing prompts are unchanged: `summarize_inbox`, `analyze_spreadsheet`,
`plan_week`, `search_drive`. Total: **8**.

## Why they are thin

Each prompt delegates to a composite tool and wraps the result in a question:

```
sheet_brief(spreadsheet_id, range)
    → report_from_sheet(..., output="text")      # no file is created
    → "Brief me on this table: outliers, data-quality issues, two questions…"
```

That keeps one implementation of the analysis and makes prompts cheap to add.
The catalog moved into `_prompts()` so it is importable and unit-tested.

## Tests

- 241 unit tests: 5 for the prompt catalog (names, required arguments, descriptions)
  and one documentation check that every prompt appears in both READMEs and both
  `TOOLS_REFERENCE` files.
- 51 live checks: `prompts/list` returns 8, `inbox_triage` renders real mail,
  `sheet_brief` renders a real range.

## Counts

- Tools: 67 (unchanged)
- Prompts: 8
- Unit tests: 241
- Live checks: 51
