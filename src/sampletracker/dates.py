"""Display formatting for dates sent to Excel and external systems."""

from __future__ import annotations

from datetime import date, datetime

_MONTH_ABBREV = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


def format_display_date(value: date | None) -> str:
    """Format a date as DD/MON/YYYY, e.g. 02/JUN/2026."""
    if value is None:
        return ""
    month = _MONTH_ABBREV[value.month - 1]
    return f"{value.day:02d}/{month}/{value.year}"


def format_display_datetime(value: datetime | None) -> str:
    """Format a datetime's calendar date as DD/MON/YYYY."""
    if value is None:
        return ""
    return format_display_date(value.date())
