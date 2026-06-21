"""Shared provider schema for normalized news records."""

from __future__ import annotations

import pandas as pd
from typing import Any, Iterable


CANONICAL_NEWS_COLUMNS: list[str] = [
    "timestamp",
    "symbol",
    "source",
    "title",
    "body",
    "url",
    "provider",
    "asset_class",
    "event_type",
    "country",
    "currency",
    "importance",
    "text",
]


def normalize_provider_records(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Normalize provider records into the canonical News provider schema."""
    rows = []
    for record in records:
        title = _clean_text(record.get("title"))
        body = _clean_text(record.get("body"))
        rows.append(
            {
                "timestamp": parse_provider_timestamp(record.get("timestamp")),
                "symbol": clean_symbol(record.get("symbol")),
                "source": _clean_text(record.get("source")),
                "title": title,
                "body": body,
                "url": _clean_text(record.get("url")),
                "provider": _clean_text(record.get("provider")),
                "asset_class": _clean_text(record.get("asset_class")),
                "event_type": _clean_text(record.get("event_type")),
                "country": _clean_text(record.get("country")),
                "currency": clean_symbol(record.get("currency")),
                "importance": record.get("importance"),
                "text": " ".join(part for part in (title, body) if part).strip(),
            }
        )
    frame = pd.DataFrame(rows, columns=CANONICAL_NEWS_COLUMNS)
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return frame


def parse_provider_timestamp(value: Any) -> pd.Timestamp | None:
    """Parse common provider timestamp formats into naive UTC pandas timestamps."""
    if value in (None, ""):
        return None
    if isinstance(value, pd.Timestamp):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        unit = "ms" if number > 10_000_000_000 else "s"
        parsed = pd.to_datetime(number, unit=unit, utc=True)
    else:
        parsed = pd.to_datetime(str(value), errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    if getattr(parsed, "tzinfo", None) is not None:
        return parsed.tz_convert(None)
    return parsed


def clean_symbol(value: Any) -> str | None:
    if value in (None, "") or _is_missing(value):
        return None
    text = str(value).strip().upper()
    return text or None


def _clean_text(value: Any) -> str | None:
    if value in (None, "") or _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _is_missing(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(missing, bool):
        return missing
    return False
