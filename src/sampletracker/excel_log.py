"""Push saved sample requests to an Excel log via Power Automate HTTP webhook."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any

from sampletracker.dates import format_display_date, format_display_datetime

MANUAL_CODE_PLACEHOLDER = "MANUAL"
_WEBHOOK_TIMEOUT_SECONDS = 30


def resolve_excel_webhook_url() -> str | None:
    """Read EXCEL_WEBHOOK_URL from environment or Streamlit secrets."""
    url = os.environ.get("EXCEL_WEBHOOK_URL", "").strip()
    if url:
        return url

    try:
        import streamlit as st

        if "EXCEL_WEBHOOK_URL" in st.secrets:
            secret_url = str(st.secrets["EXCEL_WEBHOOK_URL"]).strip()
            if secret_url:
                return secret_url
    except Exception:
        pass

    return None


def is_excel_sync_enabled() -> bool:
    """True when a Power Automate webhook URL is configured."""
    return resolve_excel_webhook_url() is not None


def _format_due_date_for_excel(record: dict[str, Any]) -> str:
    if record.get("due_date_display"):
        return str(record["due_date_display"])
    raw = record.get("due_date")
    if not raw:
        return ""
    if isinstance(raw, date):
        return format_display_date(raw)
    return format_display_date(date.fromisoformat(str(raw)[:10]))


def _format_created_at_for_excel(record: dict[str, Any]) -> str:
    raw = record.get("created_at")
    if not raw:
        return ""
    if isinstance(raw, datetime):
        return format_display_datetime(raw)
    text = str(raw)
    if "T" in text:
        return format_display_datetime(datetime.fromisoformat(text))
    return format_display_date(date.fromisoformat(text[:10]))


def _rows_for_webhook(saved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format database rows for the Power Automate payload."""
    rows: list[dict[str, Any]] = []
    for record in saved:
        formula_code = record["formula_code"]
        rows.append(
            {
                "request_number": record["request_number"],
                "formula_code": (
                    "-"
                    if formula_code == MANUAL_CODE_PLACEHOLDER
                    else formula_code
                ),
                "formula_name": record["formula_name"],
                "num_samples": record["num_samples"],
                "due_date": _format_due_date_for_excel(record),
                "destination": record.get("destination", ""),
                "request_origin": record["request_origin"],
                "email": record["email"],
                "created_at": _format_created_at_for_excel(record),
            }
        )
    return rows


def sync_saved_requests_to_excel(saved: list[dict[str, Any]]) -> None:
    """
    POST saved rows to the Power Automate flow.

    Raises on HTTP or network errors when EXCEL_WEBHOOK_URL is set.
  """
    webhook_url = resolve_excel_webhook_url()
    if not webhook_url:
        return

    payload = json.dumps({"rows": _rows_for_webhook(saved)}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=_WEBHOOK_TIMEOUT_SECONDS) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Excel log webhook returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Excel log webhook request failed: {exc.reason}") from exc
