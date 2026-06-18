# Data Retrieval Patterns

## Timeframes

Common constants:

- `mt5.TIMEFRAME_M1`
- `mt5.TIMEFRAME_M5`
- `mt5.TIMEFRAME_M15`
- `mt5.TIMEFRAME_M30`
- `mt5.TIMEFRAME_H1`
- `mt5.TIMEFRAME_H4`
- `mt5.TIMEFRAME_D1`

## UTC date ranges

MetaTrader stores bar and tick times in UTC. Use timezone-aware UTC datetimes.

```python
from datetime import datetime, timezone

utc_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
utc_to = datetime(2024, 2, 1, tzinfo=timezone.utc)
```

## Fetch bars and convert to DataFrame

```python
import pandas as pd
import MetaTrader5 as mt5

rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, utc_from, utc_to)
if rates is None:
    raise RuntimeError(f"copy_rates_range failed: {mt5.last_error()}")
if len(rates) == 0:
    raise RuntimeError("No bars returned. Check symbol, timeframe, date range, and terminal chart history.")

df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
```

## Fetch ticks

```python
ticks = mt5.copy_ticks_range("EURUSD", utc_from, utc_to, mt5.COPY_TICKS_ALL)
if ticks is None:
    raise RuntimeError(f"copy_ticks_range failed: {mt5.last_error()}")

ticks_df = pd.DataFrame(ticks)
if not ticks_df.empty:
    ticks_df["time"] = pd.to_datetime(ticks_df["time"], unit="s", utc=True)
    if "time_msc" in ticks_df.columns:
        ticks_df["time_msc"] = pd.to_datetime(ticks_df["time_msc"], unit="ms", utc=True)
```

## Symbol visibility helper

```python
def ensure_symbol(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol not found: {symbol}")
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Could not select symbol {symbol}: {mt5.last_error()}")
```

## Export to CSV

```python
df.to_csv("EURUSD_H1.csv", index=False)
```

## Common no-data causes

- Wrong broker symbol name.
- Symbol is not visible in MarketWatch.
- Requested dates are outside terminal history.
- Terminal chart history limit is too low.
- Market closed or broker has no ticks for that interval.
