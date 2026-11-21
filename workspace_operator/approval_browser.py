"""Operator-side browser launcher. Run in the operator's desktop session."""

import time
import webbrowser
from urllib.parse import urlsplit

from .approvals import ApprovalError, ApprovalStore


def watch(store: ApprovalStore, url: str, *, interval: float = 0.5) -> None:
    """Open each new pending request once; never approve or deny a request."""
    try:
        parts = urlsplit(url)
        _ = parts.port  # Reject malformed or out-of-range ports.
    except ValueError:
        raise ApprovalError("Invalid approval browser URL.") from None
    if (
        not parts.hostname or parts.username is not None or parts.query or parts.fragment
        or (parts.scheme != "https" and not (
            parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
        ))
    ):
        raise ApprovalError("Use a loopback HTTP or an HTTPS approval browser URL without credentials.")

    # Do not open old requests on startup. In particular, restarting the helper
    # should not suddenly put a pending operation from an earlier session on screen.
    seen = {record["id"] for record in store.list_pending()}
    print("Watching for new browser approvals. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            pending = store.list_pending()
            seen.intersection_update(record["id"] for record in pending)
            for record in pending:
                if record["id"] in seen:
                    continue
                seen.add(record["id"])
                try:
                    opened = webbrowser.open(store.browser_link(record, url), new=2)
                except (OSError, webbrowser.Error):
                    opened = False
                if not opened:
                    print(f"Could not open the browser for {record['id']}.", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        return
