"""Official macro and central-bank RSS provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import pandas as pd

from News.core import NewsSignalConfig, NewsSignalResult, build_news_signals
from News.providers.schema import normalize_provider_records


@dataclass(frozen=True)
class OfficialMacroFeed:
    """Metadata for one official macro RSS/Atom source."""

    name: str
    url: str
    country: str | None = None
    currency: str | None = None
    source: str | None = None
    importance: str | None = "high"
    event_type: str = "official_macro"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.url:
            raise ValueError("url must not be empty")


DEFAULT_OFFICIAL_MACRO_FEEDS: tuple[OfficialMacroFeed, ...] = (
    OfficialMacroFeed("fed_monetary_policy", "https://www.federalreserve.gov/feeds/press_monetary.xml", "United States", "USD", "Federal Reserve"),
    OfficialMacroFeed("ecb_press", "https://www.ecb.europa.eu/rss/press.html", "Euro Area", "EUR", "European Central Bank"),
    OfficialMacroFeed("boe_news", "https://www.bankofengland.co.uk/rss/news", "United Kingdom", "GBP", "Bank of England"),
    OfficialMacroFeed("boc_press", "https://www.bankofcanada.ca/content_type/press-releases/feed/", "Canada", "CAD", "Bank of Canada"),
    OfficialMacroFeed("rba_media", "https://www.rba.gov.au/rss/rss-cb-media-releases.xml", "Australia", "AUD", "Reserve Bank of Australia"),
    OfficialMacroFeed("boj_updates", "https://www.boj.or.jp/en/rss/whatsnew.xml", "Japan", "JPY", "Bank of Japan"),
)


class OfficialMacroProviderError(RuntimeError):
    """Raised when official macro feeds cannot be fetched or parsed."""


def fetch_official_macro_feed(feed: OfficialMacroFeed, *, timeout_seconds: int = 10) -> pd.DataFrame:
    """Fetch one official macro RSS/Atom feed and normalize it."""
    request = Request(feed.url, headers={"User-Agent": "Mozilla/5.0 NewsSignalModule/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - configured official feed URL
            payload = response.read()
    except Exception as exc:  # pragma: no cover - network defensive path
        raise OfficialMacroProviderError(f"failed to fetch {feed.name}: {exc}") from exc
    return normalize_official_macro_feed(payload, feed=feed)


def fetch_default_official_macro_feeds(*, timeout_seconds: int = 10) -> pd.DataFrame:
    """Fetch all configured official macro feeds."""
    frames = [fetch_official_macro_feed(feed, timeout_seconds=timeout_seconds) for feed in DEFAULT_OFFICIAL_MACRO_FEEDS]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True) if frames else normalize_provider_records([])


def normalize_official_macro_feed(payload: str | bytes, *, feed: OfficialMacroFeed) -> pd.DataFrame:
    """Normalize RSS/Atom items into canonical provider rows."""
    root = _parse_xml(payload)
    rows = []
    for item in _iter_feed_items(root):
        rows.append(
            {
                "timestamp": _first_xml_text(item, "pubDate", "updated", "published"),
                "symbol": feed.currency,
                "source": feed.source or feed.name,
                "title": _first_xml_text(item, "title"),
                "body": _first_xml_text(item, "description", "summary"),
                "url": _first_xml_text(item, "link") or _atom_link(item),
                "provider": "official_macro",
                "asset_class": "macro",
                "event_type": feed.event_type,
                "country": feed.country,
                "currency": feed.currency,
                "importance": feed.importance,
            }
        )
    return normalize_provider_records(rows)


def official_macro_to_signals(
    payload_or_frame: Any,
    *,
    symbols: Iterable[str] | None = None,
    index: pd.DatetimeIndex | None = None,
    config: NewsSignalConfig | None = None,
) -> NewsSignalResult:
    """Normalize official macro records and pass them through the signal engine."""
    articles = payload_or_frame if isinstance(payload_or_frame, pd.DataFrame) else normalize_provider_records(payload_or_frame)
    return build_news_signals(articles, symbols=symbols, index=index, config=config)


def _parse_xml(payload: str | bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise OfficialMacroProviderError("official macro payload is not valid RSS/XML") from exc


def _iter_feed_items(root: ElementTree.Element) -> list[ElementTree.Element]:
    items = root.findall(".//item")
    if items:
        return items
    namespace = "{http://www.w3.org/2005/Atom}"
    return root.findall(f".//{namespace}entry")


def _first_xml_text(item: ElementTree.Element, *tags: str) -> str | None:
    namespace = "{http://www.w3.org/2005/Atom}"
    for tag in tags:
        for candidate in (tag, f"{namespace}{tag}"):
            node = item.find(candidate)
            if node is not None and node.text:
                return node.text.strip()
    return None


def _atom_link(item: ElementTree.Element) -> str | None:
    namespace = "{http://www.w3.org/2005/Atom}"
    for candidate in ("link", f"{namespace}link"):
        node = item.find(candidate)
        if node is not None:
            return node.attrib.get("href")
    return None
