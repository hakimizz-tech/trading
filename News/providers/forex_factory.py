"""ForexFactory calendar export provider.

This adapter is intentionally marked internal/research only. ForexFactory's
weekly export is technically convenient, but the research notes in
``News/deep-research-report.md`` flag licensing and redistribution concerns.
Prefer official macro feeds for production trading gates.
"""

from __future__ import annotations

import json
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import pandas as pd

from News.core import NewsSignalConfig, NewsSignalResult, build_news_signals
from News.providers.schema import normalize_provider_records


FOREX_FACTORY_WEEKLY_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FOREX_FACTORY_WEEKLY_XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

COUNTRY_TO_CURRENCY: dict[str, str] = {
    "united states": "USD",
    "us": "USD",
    "euro zone": "EUR",
    "eurozone": "EUR",
    "european union": "EUR",
    "united kingdom": "GBP",
    "uk": "GBP",
    "canada": "CAD",
    "australia": "AUD",
    "new zealand": "NZD",
    "japan": "JPY",
    "switzerland": "CHF",
    "china": "CNY",
}


class ForexFactoryProviderError(RuntimeError):
    """Raised when ForexFactory export data cannot be fetched or parsed."""


def build_forex_factory_export_url(*, format: str = "json", version: str | None = None) -> str:
    """Build the official weekly export URL pattern observed in the UI."""
    if format not in {"json", "xml"}:
        raise ValueError("format must be 'json' or 'xml'")
    base_url = FOREX_FACTORY_WEEKLY_JSON_URL if format == "json" else FOREX_FACTORY_WEEKLY_XML_URL
    return f"{base_url}?{urlencode({'version': version})}" if version else base_url


def fetch_forex_factory_weekly_export(
    *,
    format: str = "json",
    version: str | None = None,
    timeout_seconds: int = 10,
) -> pd.DataFrame:
    """Fetch ForexFactory's weekly export for internal research use."""
    url = build_forex_factory_export_url(format=format, version=version)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 NewsSignalModule/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - explicit user/provider URL
            payload = response.read()
    except Exception as exc:  # pragma: no cover - network defensive path
        raise ForexFactoryProviderError(f"failed to fetch ForexFactory weekly export: {exc}") from exc
    return normalize_forex_factory_export(payload, format=format)


def normalize_forex_factory_export(payload: Any, *, format: str = "json") -> pd.DataFrame:
    """Normalize ForexFactory JSON/XML calendar exports into provider rows."""
    if format == "json":
        records = _json_records(payload)
    elif format == "xml":
        records = _xml_records(payload)
    else:
        raise ValueError("format must be 'json' or 'xml'")

    rows = []
    for item in records:
        country = _first_present(item, "country", "region")
        currency = _first_present(item, "currency") or _currency_from_country(country)
        title = _first_present(item, "title", "event", "name")
        rows.append(
            {
                "timestamp": _first_present(item, "date", "timestamp", "time"),
                "symbol": currency,
                "source": "ForexFactory",
                "title": title,
                "body": _calendar_body(item),
                "url": None,
                "provider": "forex_factory",
                "asset_class": "forex_macro",
                "event_type": "economic_calendar",
                "country": country,
                "currency": currency,
                "importance": _first_present(item, "impact", "importance"),
            }
        )
    return normalize_provider_records(rows)


def forex_factory_to_signals(
    payload_or_frame: Any,
    *,
    symbols: Iterable[str] | None = None,
    index: pd.DatetimeIndex | None = None,
    config: NewsSignalConfig | None = None,
) -> NewsSignalResult:
    """Normalize ForexFactory data and pass it through the generic signal engine."""
    articles = payload_or_frame if isinstance(payload_or_frame, pd.DataFrame) else normalize_forex_factory_export(payload_or_frame)
    return build_news_signals(articles, symbols=symbols, index=index, config=config)


def _json_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "events", "calendar", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _xml_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ForexFactoryProviderError("ForexFactory payload is not valid XML") from exc
    records = []
    for event in root.findall(".//event"):
        records.append({child.tag.lower(): child.text for child in event})
    return records


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _calendar_body(item: dict[str, Any]) -> str:
    parts = []
    for label, key in (("actual", "actual"), ("forecast", "forecast"), ("previous", "previous")):
        value = _first_present(item, key)
        if value not in (None, ""):
            parts.append(f"{label}: {value}")
    return "; ".join(parts)


def _currency_from_country(country: Any) -> str | None:
    if country in (None, ""):
        return None
    return COUNTRY_TO_CURRENCY.get(str(country).strip().lower())
