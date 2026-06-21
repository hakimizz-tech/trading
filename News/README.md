# News Signal Module

The `News` module converts free-text market news into strategy-ready features.
It follows the framework in `News/news.md`:

1. extract relevant financial events from text,
2. assign each event a signed market impact,
3. aggregate the impacts into a reusable `news_score`,
4. expose `BUY`, `SELL`, or `HOLD` news signals for strategies and agents.

The first implementation is deterministic and dependency-light. It uses curated
event patterns and keyword sentiment instead of external APIs, so it can be used
in backtests, agents, and Linux development before live broker integration.
The feature schema also follows the FinBERT-style workflow in `News/news-2.md`:
title/topic sentiment, body sentiment, no-neutral body sentiment, positive and
negative probability-style columns, and horizon-ready supervised labels.

Typical usage:

```python
import pandas as pd

from News import build_news_signals, merge_news_features

news = pd.DataFrame(
    [
        {
            "timestamp": "2026-06-21",
            "symbol": "AAPL",
            "headline": "AAPL earnings beat expectations and price target raised",
        }
    ]
)

signals = build_news_signals(news, symbols=["AAPL"])
print(signals.features)

strategy_frame = merge_news_features(ohlcv_frame, signals.features, symbol="AAPL")
```

Core feature columns include:

- `news_score`, `news_signal`, `news_buy`, `news_sell`, `news_hold`
- `title_sentiment_score`, `body_sentiment_score`, `body_sentiment_no_neutral`
- `positive_probability`, `negative_probability`, `neutral_probability`
- `article_count`, `news_count`, `event_count`, `has_enough_news`
- macro/forex-aware events such as inflation, interest-rate, labor-market,
  GDP, trade-balance, and geopolitical-risk categories

For supervised research or walk-forward experiments, build timeframe features
and forward labels separately:

```python
from News import (
    NewsFeatureConfig,
    build_news_feature_matrix,
    merge_news_features_and_labels,
)

matrices = build_news_feature_matrix(
    news,
    symbols=["EURUSD"],
    index=ohlcv_frame.index,
    frequencies=("5min", "1h", "1D"),
)

training_frame = merge_news_features_and_labels(
    ohlcv_frame,
    matrices["1h"],
    symbol="EURUSD",
    config=NewsFeatureConfig(horizons=(1, 6, 24), return_threshold=0.0005),
)
```

Strategies should treat news as a confirming or filtering feature, not as a
standalone trade recommendation. Live trading should only use timestamped news
that was available before the strategy decision time.

## Optional OKX Provider

Crypto strategies and agents can use `News.providers.okx` as a live provider for
OKX news, coin sentiment, sentiment trends, and macro-economic calendar data.
The provider is optional and requires the OKX CLI plus a configured live profile.
It does not replace `News.core`; it only normalizes OKX output into the generic
news signal flow.

```python
from News.providers.okx import fetch_okx_coin_news, okx_news_to_signals

articles = fetch_okx_coin_news(["BTC", "ETH"], limit=10)
signals = okx_news_to_signals(articles, symbols=["BTC", "ETH"])
```

For tests and backtests, pass fixture JSON or DataFrames into
`normalize_okx_news(...)` / `okx_news_to_signals(...)` instead of calling the live
CLI.

## Provider Priority

All provider adapters normalize into the same canonical object:

```python
{
    "timestamp": ...,
    "symbol": ...,
    "source": ...,
    "title": ...,
    "body": ...,
    "url": ...,
    "provider": ...,
    "asset_class": ...,
    "event_type": ...,
    "country": ...,
    "currency": ...,
    "importance": ...,
    "text": ...,
}
```

Recommended live-use order:

1. `News.providers.official_macro`: production backbone for central-bank and
   official macro headlines.
2. `News.providers.yfinance_news`: supplemental stock and ETF news.
3. `News.providers.google_news`: broad discovery and recall layer.
4. `News.providers.okx`: optional crypto news, sentiment, and macro calendar.
5. `News.providers.forex_factory`: internal/research-only calendar importer;
   prefer official macro sources for production trading gates.
