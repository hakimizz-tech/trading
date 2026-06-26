# Market Data

The `market_data` package normalizes price data before it reaches strategies, backtests, reports, or live execution gates. It gives the project one canonical shape for OHLCV candles and ticks, whether the source is a local CSV, yfinance export, Dukascopy file, MT5 rates, aiomql `Candles`, or aiomql `Ticks`.

## Canonical OHLCV Schema

Every strategy should receive OHLCV data in this shape after processing.

| Field | Type | Description |
| --- | --- | --- |
| `timestamp` | `DatetimeIndex` | UTC timestamp index, sorted ascending, with duplicate timestamps removed. |
| `open` | `float` | Opening price for the bar. |
| `high` | `float` | Highest price for the bar. |
| `low` | `float` | Lowest price for the bar. |
| `close` | `float` | Closing price for the bar. |
| `volume` | `float` | Volume for the bar. Missing volume is normalized to `0.0`. |
| `spread` | `float` | Optional spread column preserved when the source provides it. |
| `tick_volume` | `float` | Optional MT5 tick volume column preserved when requested. |
| `real_volume` | `float` | Optional MT5 real volume column preserved when requested. |
| `is_filled` | `bool` | Added by gap handling to mark rows created by filling missing bars. |
| `anomaly_spike` | `bool` | Added by quality processing when a return exceeds the rolling volatility threshold. |
| `anomaly_zero_vol` | `bool` | Added by quality processing when volume is zero or below zero. |
| `anomaly_impossible` | `bool` | Added by quality processing when OHLC constraints are violated. |
| `anomaly_any` | `bool` | Composite anomaly flag. |

## Canonical Tick Schema

Ticks are normalized separately because they are used by spread checks, execution gates, and live broker snapshots.

| Field | Type | Description |
| --- | --- | --- |
| `timestamp` | `DatetimeIndex` | UTC tick timestamp index, sorted ascending, with duplicate timestamps removed. |
| `bid` | `float` | Current bid price. Required. |
| `ask` | `float` | Current ask price. Required. |
| `last` | `float` | Last traded price. Defaults to `0.0` when missing. |
| `volume` | `float` | Tick volume. Defaults to `0.0` when missing. |
| `mid` | `float` | Mid price, computed as `(bid + ask) / 2` when missing. |
| `spread` | `float` | Ask minus bid, computed when missing. |
| `flags` | `float` | Optional MT5 tick flags. |
| `volume_real` | `float` | Optional real tick volume. |
| `time_msc` | `float` | Optional millisecond timestamp from MT5/aiomql. |

## Public API

Import from `market_data` unless you are working on internals.

| Field | Type | Description |
| --- | --- | --- |
| `load_ohlcv_csv(path, symbol=None)` | `Callable[..., DataFrame]` | Loads known local CSV formats into canonical UTC OHLCV. |
| `to_ohlcv_frame(data, source=None, symbol=None, preserve_extra=True)` | `Callable[..., DataFrame]` | Converts DataFrame-like data, MT5 rates, or aiomql `Candles` into canonical OHLCV. |
| `process_ohlcv(data, expected_freq=None, fill_gaps=False, max_gap=5, flag_quality=True)` | `Callable[..., DataFrame]` | Runs validation, optional gap filling, and optional anomaly flags. |
| `validate_ohlcv(df)` | `Callable[..., DataFrame]` | Enforces required columns, UTC index, numeric types, sorting, and deduplication. |
| `ensure_utc(df)` | `Callable[..., DataFrame]` | Returns a copy with a UTC `DatetimeIndex`. |
| `detect_gaps(df, expected_freq)` | `Callable[..., DatetimeIndex]` | Returns missing timestamps for a declared frequency. |
| `handle_gaps(df, freq, method="ffill", max_gap=5)` | `Callable[..., DataFrame]` | Fills short gaps and marks filled bars with `is_filled`. |
| `find_impossible_candles(df)` | `Callable[..., DataFrame]` | Returns rows that violate OHLC rules or contain negative price/volume. |
| `detect_price_spikes(df, window=20, threshold=3.0)` | `Callable[..., Series]` | Flags large returns relative to rolling volatility. |
| `flag_anomalies(df)` | `Callable[..., DataFrame]` | Adds anomaly columns without dropping source rows. |
| `resample_ohlcv(df, target_freq)` | `Callable[..., DataFrame]` | Resamples OHLCV to a coarser timeframe using standard OHLCV aggregation. |
| `normalize_prices(df, method="returns")` | `Callable[..., DataFrame]` | Adds return, log-return, min-max, or z-score price features. |
| `quality_report(df, source="", symbol=None, timeframe=None)` | `Callable[..., OhlcvReport]` | Builds a data-quality summary object for one dataset. |
| `to_tick_frame(data, source=None, symbol=None, preserve_extra=True)` | `Callable[..., DataFrame]` | Converts DataFrame-like data, MT5 ticks, or aiomql `Ticks` into canonical ticks. |
| `validate_tick_frame(df)` | `Callable[..., DataFrame]` | Validates tick timestamps, required bid/ask fields, numeric types, sorting, and duplicates. |
| `latest_tick(data, symbol=None)` | `Callable[..., dict]` | Returns the latest normalized tick as a plain dictionary. |
| `OhlcvReport` | `dataclass` | Data-quality report returned by `quality_report`. |
| `OHLCV_COLUMNS` | `list[str]` | Canonical OHLCV column order. |
| `OHLCV_RESAMPLE_RULES` | `dict[str, str]` | Standard aggregation rules for resampling. |
| `TICK_COLUMNS` | `list[str]` | Canonical tick column order. |

## OhlcvReport Fields

| Field | Type | Description |
| --- | --- | --- |
| `source` | `str` | Source path or source label for the dataset. |
| `symbol` | `str \| None` | Symbol inferred from the file or passed explicitly. |
| `timeframe` | `str \| None` | Timeframe inferred from the file or passed explicitly. |
| `rows` | `int` | Number of validated rows. |
| `start` | `str \| None` | First timestamp in ISO format. |
| `end` | `str \| None` | Last timestamp in ISO format. |
| `missing_values` | `int` | Missing values across OHLC columns after validation. |
| `duplicate_timestamps` | `int` | Duplicate timestamps found in the original index. |
| `impossible_candles` | `int` | Bars where OHLC relationships are impossible. |
| `negative_prices` | `int` | Bars with any negative OHLC price. |
| `negative_volume` | `int` | Bars with negative volume. |
| `zero_volume_bars` | `int` | Bars with zero volume. |
| `anomaly_spikes` | `int` | Bars flagged by rolling-volatility spike detection. |
| `anomaly_any` | `int` | Sum of major anomaly categories. |
| `filled_bars` | `int` | Rows marked as filled by `handle_gaps`. |
| `completeness_pct` | `float` | Percentage of non-null close values after validation. |
| `price_only` | `bool` | True when a price-only file was converted into flat OHLC candles. |

## Load A Local Dataset

```python
from market_data import load_ohlcv_csv, process_ohlcv, quality_report

df = load_ohlcv_csv("datasets/EURUSD/EURUSD_d1_dukascopy_bid.csv", symbol="EURUSD")
df = process_ohlcv(df, expected_freq="1D", fill_gaps=True, max_gap=3)

report = quality_report(df, source="EURUSD D1", symbol="EURUSD", timeframe="D1")
print(report.as_dict())
```

## Normalize aiomql Candles

```python
from aiomql import Account, Symbol, TimeFrame
from market_data import to_ohlcv_frame

async with Account():
    symbol = Symbol(name="EURUSD")
    await symbol.init()
    candles = await symbol.copy_rates_from_pos(timeframe=TimeFrame.H1, count=500, start_position=0)

df = to_ohlcv_frame(candles, source="aiomql", symbol="EURUSD")
```

`to_ohlcv_frame` accepts aiomql `Candles`, individual candle-like iterables, dictionaries, pandas DataFrames, and MT5-style rate arrays.

## Normalize aiomql Ticks

```python
from aiomql import Account, Symbol
from market_data import latest_tick, to_tick_frame

async with Account():
    symbol = Symbol(name="EURUSD")
    await symbol.init()
    tick = await symbol.info_tick()

latest = latest_tick([tick], symbol="EURUSD")
print(latest["bid"], latest["ask"], latest["spread"])
```

Use `to_tick_frame` when you need a full tick table and `latest_tick` when an execution gate only needs the latest bid, ask, mid, and spread.

## Resample For Strategy Research

```python
from market_data import load_ohlcv_csv, resample_ohlcv

m15 = load_ohlcv_csv("datasets/GBPUSD/GBPUSD_PERIOD_M15.csv", symbol="GBPUSD")
h1 = resample_ohlcv(m15, "1h")
```

Resampling uses:

| Field | Type | Description |
| --- | --- | --- |
| `open` | `first` | First open in the target window. |
| `high` | `max` | Highest high in the target window. |
| `low` | `min` | Lowest low in the target window. |
| `close` | `last` | Last close in the target window. |
| `volume` | `sum` | Total volume in the target window. |

## Developer Rules

- Run market data through `market_data` before sending it into strategies.
- Keep strategy modules free of CSV-format parsing logic.
- Preserve `spread`, `tick_volume`, and `real_volume` when they are useful for execution gates or cost modeling.
- Treat `price_only=True` reports as research-limited data, not execution-grade OHLCV.
- Use `quality_report` before trusting a new dataset in walk-forward research.
- Use tick normalization for live spread checks instead of deriving spread from candle data.
