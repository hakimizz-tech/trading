"""Reusable news-event signal extraction for trading strategies.

This module follows the paper in ``News/news.md``:
1. extract events and entities from free text,
2. assign each event a signed impact,
3. aggregate those impacts into a news variable that strategies can consume.

The implementation is intentionally dependency-light. It uses deterministic
keyword/regex rules first, so it can run in research, tests, and aiomql-adjacent
code without requiring external news/NLP APIs.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class NewsEventPattern:
    """A machine-testable news event definition."""

    name: str
    impact: float
    keywords: tuple[str, ...]
    category: str
    description: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("event name must not be empty")
        if not -1.0 <= self.impact <= 1.0:
            raise ValueError("impact must be between -1 and 1")
        if not self.keywords:
            raise ValueError("keywords must not be empty")


@dataclass(frozen=True)
class NewsArticle:
    """Normalized news article input."""

    timestamp: pd.Timestamp
    text: str
    symbol: str | None = None
    source: str | None = None
    title: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class ExtractedNewsEvent:
    """One extracted event with a signed market-impact score."""

    timestamp: pd.Timestamp
    event_name: str
    impact: float
    confidence: float
    symbol: str | None
    source: str | None
    matched_keyword: str
    text: str

    @property
    def weighted_impact(self) -> float:
        return self.impact * self.confidence


@dataclass(frozen=True)
class SentimentBreakdown:
    """Keyword sentiment components shaped like model sentiment outputs."""

    sentiment_score: float
    positive_probability: float
    negative_probability: float
    neutral_probability: float
    positive_score: float
    negative_score: float
    token_count: int

    @property
    def no_neutral_score(self) -> float:
        total = self.positive_probability + self.negative_probability
        if total <= 0:
            return 0.0
        return float((self.positive_probability - self.negative_probability) / total)


@dataclass(frozen=True)
class NewsSignalConfig:
    """Configuration for news feature extraction and aggregation."""

    event_patterns: tuple[NewsEventPattern, ...] = ()
    bullish_threshold: float = 0.15
    bearish_threshold: float = -0.15
    sentiment_weight: float = 0.35
    event_weight: float = 0.65
    title_weight: float = 0.60
    body_weight: float = 0.40
    min_news_count: int = 1
    timestamp_frequency: str = "D"
    decay_halflife_periods: int | None = None
    max_abs_score: float = 1.0

    def __post_init__(self) -> None:
        if self.bullish_threshold <= self.bearish_threshold:
            raise ValueError("bullish_threshold must be greater than bearish_threshold")
        if self.sentiment_weight < 0 or self.event_weight < 0:
            raise ValueError("weights must not be negative")
        if self.sentiment_weight + self.event_weight <= 0:
            raise ValueError("at least one score weight must be positive")
        if self.title_weight < 0 or self.body_weight < 0:
            raise ValueError("title/body weights must not be negative")
        if self.title_weight + self.body_weight <= 0:
            raise ValueError("at least one title/body weight must be positive")
        if self.min_news_count < 0:
            raise ValueError("min_news_count must not be negative")
        if self.decay_halflife_periods is not None and self.decay_halflife_periods <= 0:
            raise ValueError("decay_halflife_periods must be positive when provided")
        if self.max_abs_score <= 0:
            raise ValueError("max_abs_score must be positive")

    @property
    def patterns(self) -> tuple[NewsEventPattern, ...]:
        return self.event_patterns or DEFAULT_EVENT_PATTERNS


@dataclass(frozen=True)
class NewsSignalResult:
    """News features plus extracted event diagnostics."""

    features: pd.DataFrame
    events: pd.DataFrame
    articles: pd.DataFrame
    config: NewsSignalConfig


DEFAULT_EVENT_PATTERNS: tuple[NewsEventPattern, ...] = (
    NewsEventPattern("profit_up", 0.75, ("profit rises", "profit rose", "profit up", "earnings beat", "beats expectations", "profit exceeds"), "earnings", "Profit or earnings improved."),
    NewsEventPattern("profit_down", -0.75, ("profit falls", "profit fell", "profit down", "earnings miss", "misses expectations", "profit warning"), "earnings", "Profit or earnings deteriorated."),
    NewsEventPattern("sales_up", 0.55, ("sales rise", "sales rose", "sales up", "revenue rises", "revenue rose", "revenue beat"), "sales", "Sales or revenue improved."),
    NewsEventPattern("sales_down", -0.55, ("sales fall", "sales fell", "sales down", "revenue falls", "revenue fell", "revenue miss"), "sales", "Sales or revenue deteriorated."),
    NewsEventPattern("rating_up", 0.60, ("upgraded", "upgrade", "rating raised", "raised to buy", "initiated at buy", "positive rating"), "analyst", "Analyst rating improved."),
    NewsEventPattern("rating_down", -0.60, ("downgraded", "downgrade", "rating cut", "rating lowered", "lowered to sell", "negative rating"), "analyst", "Analyst rating deteriorated."),
    NewsEventPattern("price_target_raised", 0.45, ("price target raised", "target price raised", "raises price target", "raises target price"), "analyst", "Price target increased."),
    NewsEventPattern("price_target_lowered", -0.45, ("price target lowered", "target price lowered", "cuts price target", "lowers target price"), "analyst", "Price target decreased."),
    NewsEventPattern("acquisition_start", 0.35, ("to acquire", "acquires", "acquisition of", "takeover bid", "merger agreement"), "corporate_action", "Acquisition or merger activity."),
    NewsEventPattern("collaboration_start", 0.25, ("partnership with", "partners with", "collaboration with", "joint venture", "strategic alliance"), "corporate_action", "New partnership or joint venture."),
    NewsEventPattern("business_expand", 0.35, ("expands", "expansion", "new market", "opens new", "launches in"), "operations", "Business expansion."),
    NewsEventPattern("management_change", 0.0, ("chief executive resigns", "ceo resigns", "appoints ceo", "management change", "chairman resigns"), "management", "Management change; impact is context-dependent."),
    NewsEventPattern("dividend_initiation", 0.45, ("initiates dividend", "starts dividend", "first dividend", "raises dividend", "dividend increase"), "capital_return", "Dividend initiation or increase."),
    NewsEventPattern("dividend_omission", -0.65, ("cuts dividend", "dividend cut", "suspends dividend", "omits dividend", "dividend omission"), "capital_return", "Dividend cut, suspension, or omission."),
    NewsEventPattern("stock_split", 0.20, ("stock split", "share split", "split-adjusted"), "corporate_action", "Stock split event."),
    NewsEventPattern("lawsuit_negative", -0.50, ("lawsuit", "sued by", "fraud probe", "investigation into", "regulatory probe"), "legal", "Legal or regulatory pressure."),
    NewsEventPattern("guidance_up", 0.65, ("raises guidance", "raises forecast", "guidance raised", "outlook improved"), "guidance", "Company raised guidance."),
    NewsEventPattern("guidance_down", -0.65, ("cuts guidance", "lowers forecast", "guidance cut", "outlook lowered"), "guidance", "Company lowered guidance."),
    NewsEventPattern("interest_rate_hike", -0.25, ("rate hike", "raises interest rates", "interest rate increase", "higher rates", "policy tightening"), "macro_rates", "Central bank tightening; risk and currency impact is context-dependent."),
    NewsEventPattern("interest_rate_cut", 0.25, ("rate cut", "cuts interest rates", "interest rate reduction", "lower rates", "policy easing"), "macro_rates", "Central bank easing; risk and currency impact is context-dependent."),
    NewsEventPattern("central_bank_hawkish", -0.20, ("hawkish", "tighter monetary policy", "restrictive policy", "higher for longer"), "macro_rates", "Hawkish central-bank communication."),
    NewsEventPattern("central_bank_dovish", 0.20, ("dovish", "easier monetary policy", "accommodative policy", "ready to ease"), "macro_rates", "Dovish central-bank communication."),
    NewsEventPattern("inflation_hot", -0.35, ("inflation hotter", "inflation accelerated", "cpi hotter", "cpi rose more", "price pressures increased"), "macro_inflation", "Hotter inflation print."),
    NewsEventPattern("inflation_cooling", 0.30, ("inflation cooled", "inflation eased", "cpi cooled", "cpi rose less", "price pressures eased"), "macro_inflation", "Cooling inflation print."),
    NewsEventPattern("nfp_strong", 0.25, ("nonfarm payrolls beat", "nfp beat", "job growth beat", "payrolls stronger"), "macro_labor", "Stronger labor-market data."),
    NewsEventPattern("nfp_weak", -0.25, ("nonfarm payrolls miss", "nfp miss", "job growth missed", "payrolls weaker"), "macro_labor", "Weaker labor-market data."),
    NewsEventPattern("unemployment_up", -0.30, ("unemployment rises", "jobless rate rises", "unemployment rate increased"), "macro_labor", "Unemployment worsened."),
    NewsEventPattern("unemployment_down", 0.30, ("unemployment falls", "jobless rate falls", "unemployment rate declined"), "macro_labor", "Unemployment improved."),
    NewsEventPattern("gdp_strong", 0.30, ("gdp beat", "growth accelerated", "economy expanded faster", "strong gdp"), "macro_growth", "Growth data improved."),
    NewsEventPattern("gdp_weak", -0.30, ("gdp miss", "growth slowed", "economy contracted", "weak gdp"), "macro_growth", "Growth data deteriorated."),
    NewsEventPattern("trade_balance_surplus", 0.20, ("trade surplus widened", "current account surplus", "exports beat"), "macro_trade", "Trade balance improved."),
    NewsEventPattern("trade_balance_deficit", -0.20, ("trade deficit widened", "current account deficit", "exports fell"), "macro_trade", "Trade balance deteriorated."),
    NewsEventPattern("geopolitical_risk", -0.50, ("geopolitical tensions", "military conflict", "sanctions imposed", "war risk", "escalating conflict"), "macro_risk", "Geopolitical risk event."),
)

BULLISH_KEYWORDS: dict[str, float] = {
    "beat": 1.0,
    "beats": 1.0,
    "bullish": 1.0,
    "gain": 0.5,
    "gains": 0.5,
    "growth": 0.7,
    "improved": 0.7,
    "outperform": 0.8,
    "positive": 0.7,
    "profit": 0.3,
    "rally": 0.6,
    "record": 0.5,
    "recovery": 0.5,
    "strong": 0.6,
    "surge": 0.8,
    "upgrade": 0.8,
    "upgraded": 0.8,
}

BEARISH_KEYWORDS: dict[str, float] = {
    "bearish": 1.0,
    "cut": 0.7,
    "cuts": 0.7,
    "decline": 0.6,
    "downgrade": 0.8,
    "downgraded": 0.8,
    "fall": 0.6,
    "falls": 0.6,
    "fraud": 1.0,
    "loss": 0.8,
    "miss": 0.9,
    "misses": 0.9,
    "negative": 0.7,
    "probe": 0.7,
    "recession": 0.8,
    "risk": 0.5,
    "sued": 0.8,
    "warning": 0.9,
    "weak": 0.6,
}


def extract_events_from_text(
    text: str,
    *,
    symbol: str | None = None,
    timestamp: pd.Timestamp | str | None = None,
    source: str | None = None,
    config: NewsSignalConfig | None = None,
) -> list[ExtractedNewsEvent]:
    """Extract signed events from a text string."""
    cfg = config or NewsSignalConfig()
    if not isinstance(text, str) or not text.strip():
        return []
    event_timestamp = pd.Timestamp(timestamp) if timestamp is not None else pd.Timestamp.utcnow()
    normalized_text = _normalize_text(text)
    events: list[ExtractedNewsEvent] = []
    for pattern in cfg.patterns:
        for keyword in pattern.keywords:
            if _keyword_matches(normalized_text, keyword):
                confidence = _keyword_confidence(normalized_text, keyword)
                events.append(
                    ExtractedNewsEvent(
                        timestamp=event_timestamp,
                        event_name=pattern.name,
                        impact=float(pattern.impact),
                        confidence=confidence,
                        symbol=_clean_symbol(symbol),
                        source=source,
                        matched_keyword=keyword,
                        text=text,
                    )
                )
                break
    return events


def score_text_sentiment(text: str) -> float:
    """Return keyword sentiment from -1.0 bearish to +1.0 bullish."""
    return score_text_sentiment_components(text).sentiment_score


def score_text_sentiment_components(text: str) -> SentimentBreakdown:
    """Return deterministic sentiment components for feature engineering.

    The probabilities are keyword-derived approximations, not calibrated model
    outputs. They intentionally mirror FinBERT-style columns so a model provider
    can be swapped in later without changing strategy feature schemas.
    """
    if not isinstance(text, str) or not text.strip():
        return SentimentBreakdown(0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0)
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-']+", text.lower())
    bull_score = sum(BULLISH_KEYWORDS.get(token, 0.0) for token in tokens)
    bear_score = sum(BEARISH_KEYWORDS.get(token, 0.0) for token in tokens)
    total = bull_score + bear_score
    if total <= 0:
        return SentimentBreakdown(0.0, 0.0, 0.0, 1.0, float(bull_score), float(bear_score), len(tokens))
    neutral_score = float(max(0.0, len(tokens) - total))
    probability_total = float(total + neutral_score)
    positive_probability = float(bull_score / probability_total)
    negative_probability = float(bear_score / probability_total)
    neutral_probability = float(neutral_score / probability_total)
    sentiment_score = float((bull_score - bear_score) / total)
    return SentimentBreakdown(
        sentiment_score=sentiment_score,
        positive_probability=positive_probability,
        negative_probability=negative_probability,
        neutral_probability=neutral_probability,
        positive_score=float(bull_score),
        negative_score=float(bear_score),
        token_count=len(tokens),
    )


def build_news_signals(
    news: pd.DataFrame | Iterable[NewsArticle | dict[str, Any]],
    *,
    symbols: Iterable[str] | None = None,
    index: pd.DatetimeIndex | None = None,
    config: NewsSignalConfig | None = None,
) -> NewsSignalResult:
    """Build strategy-ready news features by timestamp and symbol."""
    cfg = config or NewsSignalConfig()
    articles = _normalize_articles(news, cfg)
    symbol_list = sorted({_clean_symbol(symbol) for symbol in symbols or [] if _clean_symbol(symbol)})
    if articles.empty:
        return NewsSignalResult(_empty_features(index, symbol_list), _empty_events(), articles, cfg)

    if symbol_list:
        articles = articles.loc[articles["symbol"].isin(symbol_list)]
    if articles.empty:
        return NewsSignalResult(_empty_features(index, symbol_list), _empty_events(), articles, cfg)

    event_rows: list[dict[str, Any]] = []
    article_scores: list[dict[str, Any]] = []
    for _, row in articles.iterrows():
        text = str(row["text"])
        title_sentiment = score_text_sentiment_components(str(row.get("title_text") or ""))
        body_sentiment = score_text_sentiment_components(str(row.get("body_text") or ""))
        sentiment = _weighted_average(
            (title_sentiment.sentiment_score, body_sentiment.sentiment_score),
            (cfg.title_weight, cfg.body_weight),
        )
        positive_probability = _weighted_average(
            (title_sentiment.positive_probability, body_sentiment.positive_probability),
            (cfg.title_weight, cfg.body_weight),
        )
        negative_probability = _weighted_average(
            (title_sentiment.negative_probability, body_sentiment.negative_probability),
            (cfg.title_weight, cfg.body_weight),
        )
        neutral_probability = _weighted_average(
            (title_sentiment.neutral_probability, body_sentiment.neutral_probability),
            (cfg.title_weight, cfg.body_weight),
        )
        events = extract_events_from_text(
            text,
            symbol=row.get("symbol"),
            timestamp=row["timestamp"],
            source=row.get("source"),
            config=cfg,
        )
        event_score = float(sum(event.weighted_impact for event in events))
        combined = _clip_score(cfg.event_weight * event_score + cfg.sentiment_weight * sentiment, cfg.max_abs_score)
        article_scores.append(
            {
                "timestamp": row["timestamp"],
                "symbol": row["symbol"],
                "article_count": 1,
                "event_count": len(events),
                "positive_event_count": sum(1 for event in events if event.impact > 0),
                "negative_event_count": sum(1 for event in events if event.impact < 0),
                "event_score": _clip_score(event_score, cfg.max_abs_score),
                "sentiment_score": sentiment,
                "title_sentiment_score": title_sentiment.sentiment_score,
                "body_sentiment_score": body_sentiment.sentiment_score,
                "body_sentiment_no_neutral": body_sentiment.no_neutral_score,
                "positive_probability": positive_probability,
                "negative_probability": negative_probability,
                "neutral_probability": neutral_probability,
                "news_score": combined,
            }
        )
        for event in events:
            event_rows.append(
                {
                    "timestamp": event.timestamp,
                    "symbol": event.symbol,
                    "event_name": event.event_name,
                    "impact": event.impact,
                    "confidence": event.confidence,
                    "weighted_impact": event.weighted_impact,
                    "source": event.source,
                    "matched_keyword": event.matched_keyword,
                }
            )

    article_frame = pd.DataFrame(article_scores)
    article_frame["bucket"] = article_frame["timestamp"].dt.floor(cfg.timestamp_frequency)
    grouped = article_frame.groupby(["bucket", "symbol"], dropna=False).agg(
        article_count=("article_count", "sum"),
        event_count=("event_count", "sum"),
        positive_event_count=("positive_event_count", "sum"),
        negative_event_count=("negative_event_count", "sum"),
        event_score=("event_score", "mean"),
        sentiment_score=("sentiment_score", "mean"),
        title_sentiment_score=("title_sentiment_score", "mean"),
        body_sentiment_score=("body_sentiment_score", "mean"),
        body_sentiment_no_neutral=("body_sentiment_no_neutral", "mean"),
        positive_probability=("positive_probability", "mean"),
        negative_probability=("negative_probability", "mean"),
        neutral_probability=("neutral_probability", "mean"),
        news_score=("news_score", "mean"),
    )
    grouped = grouped.reset_index().rename(columns={"bucket": "timestamp"})
    grouped["news_count"] = grouped["article_count"]
    grouped["has_enough_news"] = grouped["article_count"].ge(cfg.min_news_count)
    grouped["news_score"] = grouped["news_score"].map(lambda value: _clip_score(float(value), cfg.max_abs_score))
    grouped["news_signal"] = grouped["news_score"].map(lambda value: decision_from_score(float(value), cfg))
    grouped["news_buy"] = grouped["news_signal"].eq("BUY")
    grouped["news_sell"] = grouped["news_signal"].eq("SELL")
    grouped["news_hold"] = grouped["news_signal"].eq("HOLD")
    features = grouped.set_index(["timestamp", "symbol"]).sort_index()
    features = _apply_decay(features, cfg)
    features = _align_features(features, index=index, symbols=symbol_list)
    events_frame = pd.DataFrame(event_rows)
    if events_frame.empty:
        events_frame = _empty_events()
    return NewsSignalResult(features, events_frame, articles, cfg)


def merge_news_features(
    market_data: pd.DataFrame,
    news_features: pd.DataFrame,
    *,
    symbol: str | None = None,
    fill_neutral: bool = True,
) -> pd.DataFrame:
    """Join one symbol's news features onto an OHLCV/indicator DataFrame."""
    if not isinstance(market_data, pd.DataFrame):
        raise TypeError("market_data must be a pandas DataFrame")
    if not isinstance(market_data.index, pd.DatetimeIndex):
        raise TypeError("market_data must use a DatetimeIndex")
    if not isinstance(news_features, pd.DataFrame):
        raise TypeError("news_features must be a pandas DataFrame")
    result = market_data.copy()
    if isinstance(news_features.index, pd.MultiIndex):
        if symbol is None:
            symbols = news_features.index.get_level_values("symbol").dropna().unique()
            if len(symbols) != 1:
                raise ValueError("symbol is required when news_features contains multiple symbols")
            symbol = str(symbols[0])
        selected = news_features.xs(_clean_symbol(symbol), level="symbol", drop_level=True)
    else:
        selected = news_features
    merged = result.join(selected.reindex(result.index), how="left")
    return _fill_neutral_news_columns(merged) if fill_neutral else merged


def decision_from_score(score: float, config: NewsSignalConfig | None = None) -> str:
    """Map a numeric news score to BUY, SELL, or HOLD."""
    cfg = config or NewsSignalConfig()
    if score >= cfg.bullish_threshold:
        return "BUY"
    if score <= cfg.bearish_threshold:
        return "SELL"
    return "HOLD"


def _normalize_articles(
    news: pd.DataFrame | Iterable[NewsArticle | dict[str, Any]],
    config: NewsSignalConfig,
) -> pd.DataFrame:
    if isinstance(news, pd.DataFrame):
        frame = news.copy()
    else:
        rows = []
        for item in news:
            if isinstance(item, NewsArticle):
                rows.append(
                    {
                        "timestamp": item.timestamp,
                        "symbol": item.symbol,
                        "source": item.source,
                        "title": item.title,
                        "url": item.url,
                        "text": item.text,
                    }
                )
            else:
                rows.append(dict(item))
        frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "source", "title", "url", "title_text", "body_text", "text"])

    if "timestamp" not in frame.columns:
        raise ValueError("news must contain a timestamp column")
    title_columns = [column for column in ("title", "headline", "topic") if column in frame.columns]
    body_columns = [column for column in ("body", "summary", "description", "content", "text") if column in frame.columns]
    if not title_columns and not body_columns:
        raise ValueError("news must contain text, body, summary, headline, or title")
    title_text = _combine_text_columns(frame, title_columns)
    body_text = _combine_text_columns(frame, body_columns)
    text = (title_text + " " + body_text).str.strip()
    normalized = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(frame["timestamp"], errors="coerce"),
            "symbol": frame.get("symbol", pd.Series(pd.NA, index=frame.index)).map(_clean_symbol),
            "source": frame.get("source", pd.Series(pd.NA, index=frame.index)),
            "title": frame.get("title", pd.Series(pd.NA, index=frame.index)),
            "url": frame.get("url", pd.Series(pd.NA, index=frame.index)),
            "title_text": title_text,
            "body_text": body_text,
            "text": text,
        }
    )
    normalized = normalized.dropna(subset=["timestamp"])
    normalized["timestamp"] = normalized["timestamp"].dt.tz_localize(None) if normalized["timestamp"].dt.tz is not None else normalized["timestamp"]
    return normalized.sort_values("timestamp").reset_index(drop=True)


def _align_features(
    features: pd.DataFrame,
    *,
    index: pd.DatetimeIndex | None,
    symbols: list[str],
) -> pd.DataFrame:
    if index is None:
        return features
    target_symbols = symbols or sorted(features.index.get_level_values("symbol").dropna().unique())
    if not target_symbols:
        return _empty_features(index, [])
    frames = []
    for symbol in target_symbols:
        try:
            selected = features.xs(symbol, level="symbol", drop_level=True)
        except KeyError:
            selected = pd.DataFrame(index=pd.DatetimeIndex([], name="timestamp"))
        aligned = selected.reindex(index).pipe(_fill_neutral_news_columns)
        aligned.index.name = "timestamp"
        aligned["symbol"] = symbol
        frames.append(aligned.reset_index().set_index(["timestamp", "symbol"]))
    return pd.concat(frames).sort_index()


def _apply_decay(features: pd.DataFrame, config: NewsSignalConfig) -> pd.DataFrame:
    if config.decay_halflife_periods is None or features.empty:
        return features
    frames = []
    numeric_columns = [
        "event_score",
        "sentiment_score",
        "title_sentiment_score",
        "body_sentiment_score",
        "body_sentiment_no_neutral",
        "positive_probability",
        "negative_probability",
        "neutral_probability",
        "news_score",
        "news_count",
        "article_count",
        "event_count",
        "positive_event_count",
        "negative_event_count",
    ]
    for symbol, frame in features.groupby(level="symbol", sort=False):
        local = frame.droplevel("symbol").sort_index()
        local[numeric_columns] = local[numeric_columns].ewm(halflife=config.decay_halflife_periods, adjust=False).mean()
        local["news_signal"] = local["news_score"].map(lambda value: decision_from_score(float(value), config))
        local["news_buy"] = local["news_signal"].eq("BUY")
        local["news_sell"] = local["news_signal"].eq("SELL")
        local["news_hold"] = local["news_signal"].eq("HOLD")
        local["has_enough_news"] = local["article_count"].ge(config.min_news_count)
        local["symbol"] = symbol
        frames.append(local.reset_index().set_index(["timestamp", "symbol"]))
    return pd.concat(frames).sort_index()


def _empty_features(index: pd.DatetimeIndex | None, symbols: list[str]) -> pd.DataFrame:
    columns = [
        "article_count",
        "event_count",
        "positive_event_count",
        "negative_event_count",
        "event_score",
        "sentiment_score",
        "title_sentiment_score",
        "body_sentiment_score",
        "body_sentiment_no_neutral",
        "positive_probability",
        "negative_probability",
        "neutral_probability",
        "news_score",
        "news_count",
        "news_signal",
        "news_buy",
        "news_sell",
        "news_hold",
        "has_enough_news",
    ]
    if index is None or not symbols:
        return pd.DataFrame(columns=columns).rename_axis(index=["timestamp", "symbol"])
    frames = []
    for symbol in symbols:
        frame = pd.DataFrame(index=index)
        frame["symbol"] = symbol
        frames.append(_fill_neutral_news_columns(frame).reset_index().set_index(["timestamp", "symbol"]))
    return pd.concat(frames).sort_index()[columns]


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["timestamp", "symbol", "event_name", "impact", "confidence", "weighted_impact", "source", "matched_keyword"]
    )


def _fill_neutral_news_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    numeric_defaults = {
        "article_count": 0.0,
        "event_count": 0.0,
        "positive_event_count": 0.0,
        "negative_event_count": 0.0,
        "event_score": 0.0,
        "sentiment_score": 0.0,
        "title_sentiment_score": 0.0,
        "body_sentiment_score": 0.0,
        "body_sentiment_no_neutral": 0.0,
        "positive_probability": 0.0,
        "negative_probability": 0.0,
        "neutral_probability": 1.0,
        "news_score": 0.0,
        "news_count": 0.0,
    }
    for column, default in numeric_defaults.items():
        if column not in result.columns:
            result[column] = default
        else:
            result[column] = pd.to_numeric(result[column], errors="coerce").fillna(default)
    if "news_signal" not in result.columns:
        result["news_signal"] = "HOLD"
    else:
        result["news_signal"] = result["news_signal"].fillna("HOLD")
    result["news_buy"] = _boolean_column(result, "news_buy", False)
    result["news_sell"] = _boolean_column(result, "news_sell", False)
    result["news_hold"] = _boolean_column(result, "news_hold", True)
    result["has_enough_news"] = _boolean_column(result, "has_enough_news", False)
    return result


def _boolean_column(frame: pd.DataFrame, column: str, default: bool) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=bool)
    return frame[column].where(frame[column].notna(), default).astype(bool)


def _combine_text_columns(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    if not columns:
        return pd.Series("", index=frame.index, dtype=str)
    return frame[columns].fillna("").astype(str).agg(" ".join, axis=1).str.strip()


def _weighted_average(values: tuple[float, ...], weights: tuple[float, ...]) -> float:
    usable = [(float(value), float(weight)) for value, weight in zip(values, weights) if weight > 0]
    if not usable:
        return 0.0
    total_weight = sum(weight for _, weight in usable)
    if total_weight <= 0:
        return 0.0
    return float(sum(value * weight for value, weight in usable) / total_weight)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _keyword_matches(text: str, keyword: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _keyword_confidence(text: str, keyword: str) -> float:
    count = len(re.findall(re.escape(keyword.lower()), text))
    if count <= 1:
        return 0.75
    return float(min(1.0, 0.75 + math.log1p(count) / 10.0))


def _clip_score(value: float, max_abs_score: float) -> float:
    if pd.isna(value):
        return 0.0
    return float(max(-max_abs_score, min(max_abs_score, value)))


def _clean_symbol(symbol: Any) -> str | None:
    if symbol is None or pd.isna(symbol):
        return None
    value = str(symbol).strip().upper()
    return value or None
