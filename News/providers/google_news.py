"""Google News RSS provider for broad headline discovery."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import pandas as pd

from News.core import NewsSignalConfig, NewsSignalResult, build_news_signals
from News.providers.schema import normalize_provider_records


GOOGLE_NEWS_TOP_STORIES_URL = "https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"
GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"


class GoogleNewsProviderError(RuntimeError):
    """Raised when Google News RSS cannot be fetched or parsed."""


def build_google_news_rss_url(
    query: str | None = None,
    *,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
) -> str:
    """Build a Google News RSS URL for top stories or a search query."""
    if query and query.strip():
        return GOOGLE_NEWS_SEARCH_URL.format(query=quote_plus(query.strip()), hl=hl, gl=gl, ceid=quote_plus(ceid, safe=":"))
    return GOOGLE_NEWS_TOP_STORIES_URL.format(hl=hl, gl=gl, ceid=quote_plus(ceid, safe=":"))


def fetch_google_news_rss(
    query: str | None = None,
    *,
    symbol: str | None = None,
    asset_class: str | None = None,
    timeout_seconds: int = 10,
) -> pd.DataFrame:
    """Fetch and normalize Google News RSS headlines."""
    url = build_google_news_rss_url(query)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 NewsSignalModule/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - user-selected public RSS endpoint
            payload = response.read()
    except Exception as exc:  # pragma: no cover - network defensive path
        raise GoogleNewsProviderError(f"failed to fetch Google News RSS: {exc}") from exc
    return normalize_google_news_rss(payload, symbol=symbol, asset_class=asset_class)


def normalize_google_news_rss(
    payload: str | bytes,
    *,
    symbol: str | None = None,
    asset_class: str | None = None,
) -> pd.DataFrame:
    """Normalize Google News RSS XML into canonical provider rows."""
    root = _parse_xml(payload)
    rows = []
    for item in root.findall(".//item"):
        source_node = item.find("source")
        rows.append(
            {
                "timestamp": _node_text(item, "pubDate"),
                "symbol": symbol,
                "source": source_node.text if source_node is not None else "Google News",
                "title": _node_text(item, "title"),
                "body": _node_text(item, "description"),
                "url": _node_text(item, "link"),
                "provider": "google_news",
                "asset_class": asset_class,
                "event_type": "headline",
                "country": None,
                "currency": None,
                "importance": None,
            }
        )
    return normalize_provider_records(rows)


def google_news_to_signals(
    payload_or_frame: Any,
    *,
    symbols: list[str] | None = None,
    index: pd.DatetimeIndex | None = None,
    config: NewsSignalConfig | None = None,
) -> NewsSignalResult:
    """Normalize Google News RSS and pass it through the generic signal engine."""
    articles = payload_or_frame if isinstance(payload_or_frame, pd.DataFrame) else normalize_google_news_rss(payload_or_frame)
    return build_news_signals(articles, symbols=symbols, index=index, config=config)


def _parse_xml(payload: str | bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise GoogleNewsProviderError("Google News payload is not valid RSS/XML") from exc


def _node_text(item: ElementTree.Element, tag: str) -> str | None:
    node = item.find(tag)
    return node.text.strip() if node is not None and node.text else None
