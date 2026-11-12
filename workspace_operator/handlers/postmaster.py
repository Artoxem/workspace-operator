"""Gmail Postmaster Tools handlers (domain deliverability metrics)."""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config


def _service(config: Config):
    return build(
        "gmailpostmastertools", "v1beta1", credentials=get_creds(config), cache_discovery=False
    )


def _normalize_domain(domain: str) -> str:
    value = str(domain or "").strip().lower()
    if value.startswith("domains/"):
        value = value[len("domains/") :]
    return value


def _percent(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _date_of(name: str) -> str:
    tail = str(name or "").rsplit("/", 1)[-1]
    if len(tail) == 8 and tail.isdigit():
        return f"{tail[0:4]}-{tail[4:6]}-{tail[6:8]}"
    return tail


def postmaster_list_domains_handler(config: Config, logger: logging.Logger) -> str:
    try:
        service = _service(config)
        domains: List[Dict[str, Any]] = []
        token = None
        while True:
            response = (
                service.domains()
                .list(pageSize=100, pageToken=token)
                .execute()
            )
            domains.extend(response.get("domains", []))
            token = response.get("nextPageToken")
            if not token:
                break
        if not domains:
            return (
                "No verified domains found. Verify a domain in Search Console and "
                "add it to Postmaster Tools first."
            )
        lines = ["Postmaster domains:"]
        for entry in domains:
            lines.append(
                f"- {_normalize_domain(entry.get('name', ''))} "
                f"(permission: {entry.get('permission', 'unknown')})"
            )
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error("postmaster_list_domains failed: %s", exc)
        return f"Error: cannot list Postmaster domains: {exc}"


def postmaster_traffic_stats_handler(
    config: Config,
    logger: logging.Logger,
    domain: str,
    days: int = 7,
) -> str:
    try:
        name = _normalize_domain(domain)
        if not name:
            return "Error: domain is required."
        try:
            window = max(1, min(int(days or 7), 90))
        except (TypeError, ValueError):
            window = 7
        end = date.today()
        start = end - timedelta(days=window - 1)
        service = _service(config)
        entries: List[Dict[str, Any]] = []
        token = None
        while True:
            response = (
                service.domains()
                .trafficStats()
                .list(
                    parent=f"domains/{name}",
                    startDate_year=start.year,
                    startDate_month=start.month,
                    startDate_day=start.day,
                    endDate_year=end.year,
                    endDate_month=end.month,
                    endDate_day=end.day,
                    pageSize=90,
                    pageToken=token,
                )
                .execute()
            )
            entries.extend(response.get("trafficStats", []))
            token = response.get("nextPageToken")
            if not token:
                break
        if not entries:
            return f"No traffic statistics for {name} in the last {window} day(s)."
        lines = [f"Postmaster stats for {name} ({window} day(s)):"]
        for entry in sorted(entries, key=lambda item: item.get("name", "")):
            errors = entry.get("deliveryErrors") or []
            error_text = ", ".join(
                f"{error.get('errorType', '?')}={_percent(error.get('errorRatio'))}"
                for error in errors
            )
            line = (
                f"- {_date_of(entry.get('name', ''))}: "
                f"spam={_percent(entry.get('userReportedSpamRatio'))}, "
                f"reputation={entry.get('domainReputation', 'n/a')}, "
                f"dkim={_percent(entry.get('dkimSuccessRatio'))}, "
                f"dmarc={_percent(entry.get('dmarcSuccessRatio'))}, "
                f"spf={_percent(entry.get('spfSuccessRatio'))}"
            )
            if error_text:
                line += f", errors: {error_text}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error("postmaster_traffic_stats failed: %s", exc)
        return f"Error: cannot read Postmaster stats: {exc}"
