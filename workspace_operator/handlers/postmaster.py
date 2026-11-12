"""Gmail Postmaster Tools handlers (v2 domain deliverability metrics)."""

import json
import logging
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List

from googleapiclient.discovery import build_from_document

from ..auth import get_creds
from ..config import Config

DISCOVERY_URL = (
    "https://gmailpostmastertools.googleapis.com/$discovery/rest?version=v2"
)
_DISCOVERY: Dict[str, Any] = {}

# Metric definitions sent to domains.domainStats.query. The key is the name
# echoed back in each DomainStat.metric field.
METRICS = [
    {"name": "spam_rate", "baseMetric": {"standardMetric": "SPAM_RATE"}},
    {"name": "delivery_errors", "baseMetric": {"standardMetric": "DELIVERY_ERROR_COUNT"}},
    {
        "name": "auth_spf",
        "baseMetric": {"standardMetric": "AUTH_SUCCESS_RATE"},
        "filter": 'auth_type = "spf"',
    },
    {
        "name": "auth_dkim",
        "baseMetric": {"standardMetric": "AUTH_SUCCESS_RATE"},
        "filter": 'auth_type = "dkim"',
    },
    {
        "name": "auth_dmarc",
        "baseMetric": {"standardMetric": "AUTH_SUCCESS_RATE"},
        "filter": 'auth_type = "dmarc"',
    },
]


def _service(config: Config):
    if not _DISCOVERY:
        with urllib.request.urlopen(DISCOVERY_URL, timeout=20) as response:
            _DISCOVERY.update(json.load(response))
    return build_from_document(
        json.dumps(_DISCOVERY), credentials=get_creds(config)
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
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if 0 <= number <= 1:
        number *= 100
    return f"{number:.2f}%"


def _stat_value(stat: Dict[str, Any]) -> Any:
    value = stat.get("value") or {}
    for key in ("doubleValue", "floatValue", "intValue"):
        if key in value and value[key] is not None:
            try:
                return float(value[key]) if key != "intValue" else int(value[key])
            except (TypeError, ValueError):
                return value[key]
    return value.get("stringValue")


def _date_label(stat: Dict[str, Any]) -> str:
    date_value = stat.get("date") or {}
    if date_value:
        return (
            f"{int(date_value.get('year', 0)):04d}-"
            f"{int(date_value.get('month', 0)):02d}-"
            f"{int(date_value.get('day', 0)):02d}"
        )
    return "overall"


def postmaster_list_domains_handler(config: Config, logger: logging.Logger) -> str:
    try:
        service = _service(config)
        domains: List[Dict[str, Any]] = []
        token = None
        while True:
            response = (
                service.domains().list(pageSize=100, pageToken=token).execute()
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
            state = entry.get("verificationState")
            lines.append(
                f"- {_normalize_domain(entry.get('name', ''))} "
                f"(permission: {entry.get('permission', 'unknown')}"
                + (f", state: {state}" if state else "")
                + ")"
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
        rows: List[Dict[str, Any]] = []
        token = None
        while True:
            body: Dict[str, Any] = {
                "timeQuery": {
                    "dateRanges": {
                        "dateRanges": [
                            {
                                "start": {
                                    "year": start.year,
                                    "month": start.month,
                                    "day": start.day,
                                },
                                "end": {
                                    "year": end.year,
                                    "month": end.month,
                                    "day": end.day,
                                },
                            }
                        ]
                    }
                },
                "metricDefinitions": METRICS,
                "aggregationGranularity": "DAILY",
                "pageSize": 200,
            }
            if token:
                body["pageToken"] = token
            response = (
                service.domains()
                .domainStats()
                .query(parent=f"domains/{name}", body=body)
                .execute()
            )
            rows.extend(response.get("domainStats", []))
            token = response.get("nextPageToken")
            if not token:
                break
        if not rows:
            return f"No traffic statistics for {name} in the last {window} day(s)."

        by_date: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            label = _date_label(row)
            by_date.setdefault(label, {})[row.get("metric", "")] = _stat_value(row)

        lines = [f"Postmaster stats for {name} ({window} day(s)):"]
        for label in sorted(by_date):
            metrics = by_date[label]
            lines.append(
                f"- {label}: spam={_percent(metrics.get('spam_rate'))}, "
                f"spf={_percent(metrics.get('auth_spf'))}, "
                f"dkim={_percent(metrics.get('auth_dkim'))}, "
                f"dmarc={_percent(metrics.get('auth_dmarc'))}, "
                f"delivery_errors={metrics.get('delivery_errors', 'n/a')}"
            )
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error("postmaster_traffic_stats failed: %s", exc)
        return f"Error: cannot read Postmaster stats: {exc}"
