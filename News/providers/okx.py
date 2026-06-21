"""OKX crypto news, sentiment, and macro calendar provider.

This adapter is intentionally optional. It shells out to the installed ``okx``
CLI only when fetch functions are called, then normalizes JSON output into the
generic ``News`` module structures used by strategies and agents.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import pandas as pd

from News.core import NewsSignalConfig, NewsSignalResult, build_news_signals
from News.providers.schema import normalize_provider_records


@dataclass(frozen=True)
class OkxNewsProviderConfig:
    """Runtime settings for the OKX news provider."""

    cli: str = "okx"
    profile: str = "live"
    lang: str = "en-US"
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if not self.cli:
            raise ValueError("cli must not be empty")
        if not self.profile:
            raise ValueError("profile must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class OkxNewsProviderError(RuntimeError):
    """Raised when the OKX CLI is unavailable or returns an error."""


def build_okx_latest_command(
    *,
    limit: int = 10,
    begin_ms: int | None = None,
    end_ms: int | None = None,
    importance: str | None = None,
    coins: Iterable[str] | None = None,
    config: OkxNewsProviderConfig | None = None,
) -> list[str]:
    """Build an ``okx news latest`` command."""
    cfg = config or OkxNewsProviderConfig()
    command = _base_command(cfg, "latest")
    _append_common_news_args(command, limit=limit, begin_ms=begin_ms, end_ms=end_ms, importance=importance, coins=coins, lang=cfg.lang)
    return command


def build_okx_by_coin_command(
    coins: Iterable[str],
    *,
    limit: int = 10,
    begin_ms: int | None = None,
    end_ms: int | None = None,
    importance: str | None = None,
    config: OkxNewsProviderConfig | None = None,
) -> list[str]:
    """Build an ``okx news by-coin`` command."""
    cfg = config or OkxNewsProviderConfig()
    command = _base_command(cfg, "by-coin")
    command.extend(["--coins", _coin_arg(coins)])
    _append_common_news_args(command, limit=limit, begin_ms=begin_ms, end_ms=end_ms, importance=importance, coins=None, lang=cfg.lang)
    return command


def build_okx_search_command(
    keyword: str,
    *,
    coins: Iterable[str] | None = None,
    limit: int = 10,
    begin_ms: int | None = None,
    end_ms: int | None = None,
    importance: str | None = None,
    sentiment: str | None = None,
    sort_by: str | None = None,
    config: OkxNewsProviderConfig | None = None,
) -> list[str]:
    """Build an ``okx news search`` command."""
    if not keyword.strip():
        raise ValueError("keyword must not be empty")
    cfg = config or OkxNewsProviderConfig()
    command = _base_command(cfg, "search")
    command.extend(["--keyword", keyword])
    if sentiment:
        command.extend(["--sentiment", sentiment])
    if sort_by:
        command.extend(["--sort-by", sort_by])
    _append_common_news_args(command, limit=limit, begin_ms=begin_ms, end_ms=end_ms, importance=importance, coins=coins, lang=cfg.lang)
    return command


def build_okx_coin_sentiment_command(
    coins: Iterable[str],
    *,
    period: str = "24h",
    config: OkxNewsProviderConfig | None = None,
) -> list[str]:
    """Build an ``okx news coin-sentiment`` command."""
    cfg = config or OkxNewsProviderConfig()
    return [cfg.cli, "--profile", cfg.profile, "news", "coin-sentiment", "--coins", _coin_arg(coins), "--period", period, "--json"]


def build_okx_coin_trend_command(
    coin: str,
    *,
    period: str = "1h",
    points: int = 24,
    config: OkxNewsProviderConfig | None = None,
) -> list[str]:
    """Build an ``okx news coin-trend`` command."""
    clean_coin = _normalize_coin(coin)
    if not clean_coin:
        raise ValueError("coin must not be empty")
    cfg = config or OkxNewsProviderConfig()
    return [cfg.cli, "--profile", cfg.profile, "news", "coin-trend", clean_coin, "--period", period, "--points", str(points), "--json"]


def build_okx_economic_calendar_command(
    *,
    before_ms: int,
    after_ms: int,
    region: str | None = None,
    importance: int | None = None,
    limit: int = 100,
    config: OkxNewsProviderConfig | None = None,
) -> list[str]:
    """Build an ``okx news economic-calendar`` command with both bounds."""
    cfg = config or OkxNewsProviderConfig()
    command = [cfg.cli, "--profile", cfg.profile, "news", "economic-calendar", "--before", str(before_ms), "--after", str(after_ms), "--limit", str(limit), "--json"]
    if region:
        command.extend(["--region", region])
    if importance is not None:
        command.extend(["--importance", str(importance)])
    return command


def fetch_okx_latest_news(
    *,
    limit: int = 10,
    begin_ms: int | None = None,
    end_ms: int | None = None,
    importance: str | None = None,
    coins: Iterable[str] | None = None,
    config: OkxNewsProviderConfig | None = None,
) -> pd.DataFrame:
    """Fetch latest OKX news and return normalized article rows."""
    cfg = config or OkxNewsProviderConfig()
    payload = _run_okx_json(build_okx_latest_command(limit=limit, begin_ms=begin_ms, end_ms=end_ms, importance=importance, coins=coins, config=cfg), cfg)
    return normalize_okx_news(payload)


def fetch_okx_coin_news(
    coins: Iterable[str],
    *,
    limit: int = 10,
    begin_ms: int | None = None,
    end_ms: int | None = None,
    importance: str | None = None,
    config: OkxNewsProviderConfig | None = None,
) -> pd.DataFrame:
    """Fetch OKX coin news and return normalized article rows."""
    cfg = config or OkxNewsProviderConfig()
    payload = _run_okx_json(build_okx_by_coin_command(coins, limit=limit, begin_ms=begin_ms, end_ms=end_ms, importance=importance, config=cfg), cfg)
    return normalize_okx_news(payload)


def fetch_okx_coin_sentiment(
    coins: Iterable[str],
    *,
    period: str = "24h",
    config: OkxNewsProviderConfig | None = None,
) -> pd.DataFrame:
    """Fetch OKX coin sentiment snapshots."""
    cfg = config or OkxNewsProviderConfig()
    payload = _run_okx_json(build_okx_coin_sentiment_command(coins, period=period, config=cfg), cfg)
    return normalize_okx_coin_sentiment(payload)


def fetch_okx_coin_trend(
    coin: str,
    *,
    period: str = "1h",
    points: int = 24,
    config: OkxNewsProviderConfig | None = None,
) -> pd.DataFrame:
    """Fetch OKX coin sentiment trend points."""
    cfg = config or OkxNewsProviderConfig()
    payload = _run_okx_json(build_okx_coin_trend_command(coin, period=period, points=points, config=cfg), cfg)
    return normalize_okx_coin_trend(payload, fallback_symbol=coin)


def fetch_okx_economic_calendar(
    *,
    before_ms: int,
    after_ms: int,
    region: str | None = None,
    importance: int | None = None,
    limit: int = 100,
    config: OkxNewsProviderConfig | None = None,
) -> pd.DataFrame:
    """Fetch OKX macro calendar events."""
    cfg = config or OkxNewsProviderConfig()
    payload = _run_okx_json(
        build_okx_economic_calendar_command(
            before_ms=before_ms,
            after_ms=after_ms,
            region=region,
            importance=importance,
            limit=limit,
            config=cfg,
        ),
        cfg,
    )
    return normalize_okx_economic_calendar(payload)


def okx_news_to_signals(
    okx_payload_or_frame: Any,
    *,
    symbols: Iterable[str] | None = None,
    index: pd.DatetimeIndex | None = None,
    config: NewsSignalConfig | None = None,
) -> NewsSignalResult:
    """Normalize OKX news and pass it through the generic signal engine."""
    articles = okx_payload_or_frame if isinstance(okx_payload_or_frame, pd.DataFrame) else normalize_okx_news(okx_payload_or_frame)
    return build_news_signals(articles, symbols=symbols, index=index, config=config)


def normalize_okx_news(payload: Any) -> pd.DataFrame:
    """Normalize OKX news JSON into ``News.core`` article columns."""
    rows = []
    for item in _records_from_payload(payload):
        timestamp = _first_present(item, "timestamp", "time", "publishTime", "publishedAt", "createdAt", "date")
        title = _first_present(item, "title", "headline", "name")
        summary = _first_present(item, "summary", "brief", "content", "body", "description")
        coins = _coins_from_item(item)
        if not coins:
            coins = [None]
        for coin in coins:
            rows.append(
                {
                    "timestamp": _parse_okx_time(timestamp),
                    "symbol": coin,
                    "source": _first_present(item, "platform", "source", "domain", "publisher"),
                    "title": title,
                    "body": summary,
                    "url": _first_present(item, "url", "link", "sourceUrl"),
                    "provider": "okx",
                    "asset_class": "crypto",
                    "event_type": "headline",
                    "country": None,
                    "currency": coin,
                    "importance": _first_present(item, "importance", "level"),
                    "okx_id": _first_present(item, "id", "newsId", "articleId"),
                    "okx_sentiment": _first_present(item, "sentiment", "label"),
                    "okx_importance": _first_present(item, "importance", "level"),
                }
            )
    frame = normalize_provider_records(rows)
    if frame.empty:
        return frame
    return frame


def normalize_okx_coin_sentiment(payload: Any) -> pd.DataFrame:
    """Normalize OKX sentiment snapshot JSON into feature rows."""
    rows = []
    for item in _records_from_payload(payload):
        symbol = _normalize_coin(_first_present(item, "symbol", "coin", "instId", "currency"))
        bullish = _ratio_value(_first_present(item, "bullishRatio", "bullish_ratio", "bullish"))
        bearish = _ratio_value(_first_present(item, "bearishRatio", "bearish_ratio", "bearish"))
        mention_count = _numeric_or_none(_first_present(item, "mentionCount", "mention_count", "mentions", "hot"))
        rows.append(
            {
                "timestamp": _parse_okx_time(_first_present(item, "timestamp", "time", "ts")) or pd.Timestamp.utcnow().tz_localize(None),
                "symbol": symbol,
                "okx_sentiment_label": _first_present(item, "label", "sentiment"),
                "okx_bullish_ratio": bullish,
                "okx_bearish_ratio": bearish,
                "okx_mention_count": mention_count,
                "okx_sentiment_score": _sentiment_score_from_ratios(bullish, bearish),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values(["timestamp", "symbol"]).reset_index(drop=True) if not frame.empty else frame


def normalize_okx_coin_trend(payload: Any, *, fallback_symbol: str | None = None) -> pd.DataFrame:
    """Normalize OKX sentiment trend JSON into feature rows."""
    rows = []
    records = _records_from_payload(payload)
    for item in records:
        symbol = _normalize_coin(_first_present(item, "symbol", "coin", "instId", "currency") or fallback_symbol)
        bullish = _ratio_value(_first_present(item, "bullishRatio", "bullish_ratio", "bullish"))
        bearish = _ratio_value(_first_present(item, "bearishRatio", "bearish_ratio", "bearish"))
        mention_count = _numeric_or_none(_first_present(item, "mentionCount", "mention_count", "mentions"))
        rows.append(
            {
                "timestamp": _parse_okx_time(_first_present(item, "timestamp", "time", "ts", "begin", "date")),
                "symbol": symbol,
                "okx_bullish_ratio": bullish,
                "okx_bearish_ratio": bearish,
                "okx_mention_count": mention_count,
                "okx_sentiment_score": _sentiment_score_from_ratios(bullish, bearish),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    return frame.dropna(subset=["timestamp"]).sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def normalize_okx_economic_calendar(payload: Any) -> pd.DataFrame:
    """Normalize OKX economic calendar JSON into macro-event rows."""
    rows = []
    for item in _records_from_payload(payload):
        previous = _numeric_or_none(_first_present(item, "previous", "prev"))
        forecast = _numeric_or_none(_first_present(item, "forecast", "consensus"))
        actual = _numeric_or_none(_first_present(item, "actual"))
        surprise = actual - forecast if actual is not None and forecast is not None else None
        rows.append(
            {
                "timestamp": _parse_okx_time(_first_present(item, "timestamp", "time", "eventTime", "date")),
                "event": _first_present(item, "event", "title", "name"),
                "region": _first_present(item, "region", "country"),
                "importance": _numeric_or_none(_first_present(item, "importance", "level")),
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
                "surprise": surprise,
                "released": actual is not None,
                "source": "okx_economic_calendar",
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def _run_okx_json(command: Sequence[str], config: OkxNewsProviderConfig) -> Any:
    if shutil.which(config.cli) is None:
        raise OkxNewsProviderError("OKX CLI is not installed or not on PATH. Install @okx_ai/okx-trade-cli and configure a live profile.")
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=config.timeout_seconds,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        if "demo" in message.lower():
            message = "News module does not support demo mode. Please switch to a live profile."
        raise OkxNewsProviderError(message or f"OKX CLI exited with status {completed.returncode}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise OkxNewsProviderError("OKX CLI did not return valid JSON") from exc


def _base_command(config: OkxNewsProviderConfig, command_name: str) -> list[str]:
    return [config.cli, "--profile", config.profile, "news", command_name, "--json"]


def _append_common_news_args(
    command: list[str],
    *,
    limit: int,
    begin_ms: int | None,
    end_ms: int | None,
    importance: str | None,
    coins: Iterable[str] | None,
    lang: str,
) -> None:
    command.extend(["--limit", str(limit), "--lang", lang])
    if begin_ms is not None:
        command.extend(["--begin", str(begin_ms)])
    if end_ms is not None:
        command.extend(["--end", str(end_ms)])
    if importance:
        command.extend(["--importance", importance])
    if coins:
        command.extend(["--coins", _coin_arg(coins)])


def _coin_arg(coins: Iterable[str]) -> str:
    normalized = [_normalize_coin(coin) for coin in coins]
    normalized = [coin for coin in normalized if coin]
    if not normalized:
        raise ValueError("at least one coin is required")
    return ",".join(normalized)


def _normalize_coin(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper()
    if "-" in text:
        text = text.split("-", 1)[0]
    return text or None


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "news", "result", "records", "list", "trendPoints"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _records_from_payload(value)
            if nested:
                return nested
    return [payload]


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _coins_from_item(item: dict[str, Any]) -> list[str | None]:
    value = _first_present(item, "coins", "symbols", "coin", "symbol", "currencies")
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = value
    else:
        parts = [value]
    coins = []
    for part in parts:
        if isinstance(part, dict):
            part = _first_present(part, "symbol", "coin", "name")
        coin = _normalize_coin(part)
        if coin:
            coins.append(coin)
    return coins


def _parse_okx_time(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        unit = "ms" if number > 10_000_000_000 else "s"
        return pd.to_datetime(number, unit=unit, utc=True).tz_convert(None)
    text = str(value).strip()
    if text.isdigit():
        return _parse_okx_time(int(text))
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.tz_convert(None)


def _ratio_value(value: Any) -> float | None:
    number = _numeric_or_none(value)
    if number is None:
        return None
    return number / 100.0 if abs(number) > 1.0 else number


def _numeric_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def _sentiment_score_from_ratios(bullish: float | None, bearish: float | None) -> float | None:
    if bullish is None and bearish is None:
        return None
    bull = bullish or 0.0
    bear = bearish or 0.0
    total = bull + bear
    if total <= 0:
        return 0.0
    return max(-1.0, min(1.0, (bull - bear) / total))


def now_ms() -> int:
    """Return current UTC epoch milliseconds for OKX time windows."""
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)
