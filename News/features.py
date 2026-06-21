"""Feature engineering helpers for news-aware strategy research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from News.core import NewsSignalConfig, build_news_signals, merge_news_features


@dataclass(frozen=True)
class NewsFeatureConfig:
    """Configuration for supervised news feature and label generation."""

    horizons: tuple[int, ...] = (1,)
    return_threshold: float = 0.0
    close_column: str = "close"
    target_prefix: str = "target"

    def __post_init__(self) -> None:
        if not self.horizons:
            raise ValueError("horizons must not be empty")
        if any(horizon <= 0 for horizon in self.horizons):
            raise ValueError("horizons must be positive integers")
        if self.return_threshold < 0:
            raise ValueError("return_threshold must not be negative")
        if not self.close_column:
            raise ValueError("close_column must not be empty")
        if not self.target_prefix:
            raise ValueError("target_prefix must not be empty")


def build_news_feature_matrix(
    news: pd.DataFrame | Iterable[dict],
    *,
    symbols: Iterable[str],
    index: pd.DatetimeIndex,
    frequencies: Iterable[str] = ("5min", "1h", "1D"),
    signal_config: NewsSignalConfig | None = None,
) -> dict[str, pd.DataFrame]:
    """Build one aligned news feature matrix per timeframe.

    The output is keyed by frequency so strategies can test the short-horizon
    and daily windows described in ``News/news-2.md`` without changing the core
    signal builder.
    """
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("index must be a pandas DatetimeIndex")
    reusable_news = news if isinstance(news, pd.DataFrame) else list(news)
    matrices: dict[str, pd.DataFrame] = {}
    for frequency in frequencies:
        config = _replace_signal_frequency(signal_config or NewsSignalConfig(), frequency)
        matrices[frequency] = build_news_signals(reusable_news, symbols=symbols, index=index, config=config).features
    return matrices


def create_forward_return_labels(
    market_data: pd.DataFrame,
    *,
    config: NewsFeatureConfig | None = None,
) -> pd.DataFrame:
    """Create forward-return labels without lookahead in feature columns."""
    cfg = config or NewsFeatureConfig()
    if cfg.close_column not in market_data.columns:
        raise ValueError(f"market_data must contain {cfg.close_column!r}")
    close = pd.to_numeric(market_data[cfg.close_column], errors="coerce")
    labels = pd.DataFrame(index=market_data.index)
    for horizon in cfg.horizons:
        forward_return = close.shift(-horizon) / close - 1.0
        labels[f"forward_return_{horizon}"] = forward_return
        labels[f"{cfg.target_prefix}_up_{horizon}"] = forward_return.gt(cfg.return_threshold)
        labels[f"{cfg.target_prefix}_down_{horizon}"] = forward_return.lt(-cfg.return_threshold)
        labels[f"{cfg.target_prefix}_direction_{horizon}"] = _direction_label(forward_return, cfg.return_threshold)
    return labels


def merge_news_features_and_labels(
    market_data: pd.DataFrame,
    news_features: pd.DataFrame,
    *,
    symbol: str,
    config: NewsFeatureConfig | None = None,
    fill_neutral: bool = True,
) -> pd.DataFrame:
    """Join market data, aligned news features, and supervised labels."""
    labels = create_forward_return_labels(market_data, config=config)
    features = merge_news_features(market_data, news_features, symbol=symbol, fill_neutral=fill_neutral)
    return features.join(labels, how="left")


def _direction_label(forward_return: pd.Series, threshold: float) -> pd.Series:
    label = pd.Series(0, index=forward_return.index, dtype="Int64")
    label = label.mask(forward_return.gt(threshold), 1)
    label = label.mask(forward_return.lt(-threshold), -1)
    label = label.mask(forward_return.isna(), pd.NA)
    return label


def _replace_signal_frequency(config: NewsSignalConfig, frequency: str) -> NewsSignalConfig:
    return NewsSignalConfig(
        event_patterns=config.event_patterns,
        bullish_threshold=config.bullish_threshold,
        bearish_threshold=config.bearish_threshold,
        sentiment_weight=config.sentiment_weight,
        event_weight=config.event_weight,
        title_weight=config.title_weight,
        body_weight=config.body_weight,
        min_news_count=config.min_news_count,
        timestamp_frequency=frequency,
        decay_halflife_periods=config.decay_halflife_periods,
        max_abs_score=config.max_abs_score,
    )
