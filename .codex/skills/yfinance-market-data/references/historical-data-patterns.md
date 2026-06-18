# Historical Data Patterns

## Use `yf.download` for bulk OHLCV

```python
import yfinance as yf

data = yf.download(
    tickers=["SPY", "QQQ"],
    start="2020-01-01",
    end="2025-01-01",
    interval="1d",
    auto_adjust=True,
    actions=True,
    repair=False,
    progress=False,
)
```

## Use `Ticker.history` for single ticker workflows

```python
import yfinance as yf

spy = yf.Ticker("SPY")
hist = spy.history(period="5y", interval="1d", auto_adjust=True)
```

## Recommended parameter discipline

Always set these explicitly in research code:

- `tickers`
- `start` and `end`, or `period`
- `interval`
- `auto_adjust`
- `actions`
- `repair`
- `progress`
- `threads` for multi-ticker downloads
- `multi_level_index` when saving or post-processing

## Adjustment policy

Use `auto_adjust=True` when building return research, comparing long historical periods, or creating ML features from adjusted returns.

Use `auto_adjust=False` when reproducing broker charts, simulating execution from raw prices, or handling dividends and splits manually.

## Empty result guard

```python
if data is None or data.empty:
    raise ValueError("No data returned. Check ticker, exchange suffix, date range, interval, and network.")
```

## Flatten MultiIndex columns

```python
def flatten_columns(df):
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df = df.copy()
        df.columns = ["_".join(str(part) for part in col if str(part)) for col in df.columns]
    return df

flat = flatten_columns(data)
flat.to_csv("prices.csv")
```

## Preserve MultiIndex columns

```python
data.to_csv("prices_multiindex.csv")

import pandas as pd
restored = pd.read_csv("prices_multiindex.csv", header=[0, 1], index_col=0, parse_dates=True)
```

## Intraday limitations

When intraday data returns empty or partial:

- Reduce the requested lookback.
- Use a larger interval such as `5m`, `15m`, or `1h`.
- Check whether the market was open.
- Confirm the ticker has active Yahoo intraday data.
- Retry later if Yahoo is throttling or temporarily unavailable.

## Price repair

```python
raw = yf.download("VOD.L", period="10y", repair=False, progress=False)
repaired = yf.download("VOD.L", period="10y", repair=True, progress=False)
```

Use `repair=True` if prices show suspicious 100x jumps, missing rows, dividend adjustment problems, or currency-unit mixups. Keep raw data separately for audit.
