"""Yahoo Finance news provider via optional yfinance dependency."""

from __future__ import annotations
from typing import Any, Iterable
import pandas as pd
from News.core import NewsSignalConfig, NewsSignalResult, build_news_signals
from News.providers.schema import normalize_provider_records, parse_provider_timestamp


class YFinanceNewsProviderError(RuntimeError):
    """Raised when yfinance is unavailable or returns unusable news."""


def fetch_yfinance_news(tickers: Iterable[str], *, limit: int = 20) -> pd.DataFrame:
    """Fetch Yahoo Finance news for stock/ETF tickers.

    Yahoo/yfinance news should be treated as supplemental stock and ETF context;
    payload fields and latency can vary.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise YFinanceNewsProviderError("yfinance is not installed. Install it with: python -m pip install yfinance") from exc

    frames = []
    for ticker in tickers:
        symbol = str(ticker).strip().upper()
        if not symbol:
            continue
        try:
            payload = yf.Ticker(symbol).news
        except Exception as exc:  # pragma: no cover - provider/network defensive path
            raise YFinanceNewsProviderError(f"failed to fetch yfinance news for {symbol}: {exc}") from exc
        frames.append(normalize_yfinance_news(payload, symbol=symbol, limit=limit))
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True) if frames else normalize_provider_records([])


def normalize_yfinance_news(payload: Any, *, symbol: str | None = None, limit: int | None = None) -> pd.DataFrame:
    """Normalize yfinance ``Ticker.news`` payloads into canonical provider rows."""
    rows = []
    for item in _records_from_payload(payload)[:limit]:
        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        title = _first_present(item, "title") or _first_present(content, "title")
        body = _first_present(item, "summary", "description") or _first_present(content, "summary", "description")
        provider = _nested_present(item, ("publisher", "provider", "source"), ("displayName", "name")) or _nested_present(content, ("provider", "publisher"), ("displayName", "name"))
        url = _first_present(item, "link", "url") or _nested_present(content, ("canonicalUrl", "clickThroughUrl"), ("url",))
        timestamp = (
            _first_present(item, "providerPublishTime", "publishTime", "publishedAt", "pubDate", "displayTime")
            or _first_present(content, "pubDate", "displayTime", "providerPublishTime")
        )
        related = _related_tickers(item) or _related_tickers(content) or [symbol]
        for related_symbol in related:
            rows.append(
                {
                    "timestamp": parse_provider_timestamp(timestamp) or pd.Timestamp.utcnow().tz_localize(None),
                    "symbol": related_symbol or symbol,
                    "source": provider or "Yahoo Finance",
                    "title": title,
                    "body": body,
                    "url": url,
                    "provider": "yfinance",
                    "asset_class": "equity_etf",
                    "event_type": "headline",
                    "country": None,
                    "currency": None,
                    "importance": None,
                }
            )
    return normalize_provider_records(rows)


def yfinance_news_to_signals(
    payload_or_frame: Any,
    *,
    symbols: Iterable[str] | None = None,
    index: pd.DatetimeIndex | None = None,
    config: NewsSignalConfig | None = None,
) -> NewsSignalResult:
    """Normalize yfinance news and pass it through the generic signal engine."""
    articles = payload_or_frame if isinstance(payload_or_frame, pd.DataFrame) else normalize_yfinance_news(payload_or_frame)
    return build_news_signals(articles, symbols=symbols, index=index, config=config)


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, pd.DataFrame):
        return payload.to_dict("records")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "news", "result", "records", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _nested_present(item: dict[str, Any], parent_keys: tuple[str, ...], child_keys: tuple[str, ...]) -> Any:
    for parent_key in parent_keys:
        value = item.get(parent_key)
        if isinstance(value, dict):
            found = _first_present(value, *child_keys)
            if found is not None:
                return found
    return None


def _related_tickers(item: dict[str, Any]) -> list[str]:
    value = _first_present(item, "relatedTickers", "related_tickers", "symbols", "tickers")
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = value
    else:
        parts = [value]
    return [str(part).strip().upper() for part in parts if str(part).strip()]
