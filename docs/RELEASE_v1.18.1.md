# Release v1.18.1 — doctor treats missing scopes as critical

`workspace-operator doctor` used to print `[FAIL] scopes` and still finish with
«configuration looks good» and exit code 0. That hid the most common upgrade problem:
a token issued before a scope was added.

## Changed

- a missing scope is now a **critical** check: it prints the missing scopes together
  with the fix (`delete token.json and re-authorize`) and exits with code 1;
- the summary line is explicit: `configuration has problems: N critical check(s) failed`.

Everything else is unchanged: 115 tools, profiles 115/96/29, 284 unit tests and the
same live suites.
