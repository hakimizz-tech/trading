# Data Engineering Practices for Dukascopy Data

## Chunking strategy

For candles:

- Daily or H4 data: monthly or yearly chunks are usually manageable.
- M1 data: use monthly chunks for moderate ranges and weekly chunks for cautious operation.
- S1 data: use daily or weekly chunks.
- Tick data: use daily chunks by default.

## Storage recommendations

- Use CSV for portability and quick inspection.
- Use compressed CSV or Parquet for large datasets after download.
- Use JSON only when the downstream system is JavaScript-first or the structure matters more than size.
- Use array format only when file size matters and column meanings are documented elsewhere.

## Directory convention

```text
data/
  raw/
    dukascopy/
      eurusd/
        tick/
        m1/
  processed/
    dukascopy/
  cache/
    dukascopy/
```

## File naming convention

```text
dukascopy_{instrument}_{timeframe}_{from}_{to}_{priceType}.{format}
```

Examples:

```text
dukascopy_eurusd_m1_2024-02-01_2024-03-01_bid.csv
dukascopy_btcusd_tick_2019-01-13_2019-01-14.csv
```

## Validation checks

After downloading:

- Confirm file exists and has non-zero size.
- Confirm expected columns exist.
- Confirm timestamps are parseable.
- Confirm no duplicated timestamp rows when the user expects one candle per interval.
- Confirm date range roughly matches request.
- For tick data, confirm bid and ask columns exist.
- For OHLC data, confirm `high` is greater than or equal to `low` and open or close are within the high-low range where appropriate.

Use:

```bash
python scripts/validate_output_file.py --file data/dukascopy_eurusd_m1.csv --kind ohlc
python scripts/validate_output_file.py --file data/dukascopy_eurusd_tick.csv --kind tick
```

## Backtesting preparation

For pandas-based workflows:

```python
import pandas as pd

df = pd.read_csv("dukascopy_eurusd_m1.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
df = df.set_index("timestamp").sort_index()
```

For formatted timestamps, parse directly:

```python
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
```

## Common pitfalls

- Treating tick output as OHLC candles.
- Downloading months or years of tick data in one command.
- Forgetting that default timestamps are milliseconds, not seconds.
- Mixing bid and ask data in the same strategy without labeling the source.
- Assuming empty data always means a code bug.
