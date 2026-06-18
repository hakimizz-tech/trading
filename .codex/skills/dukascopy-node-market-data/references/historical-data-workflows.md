# Historical Data Workflows

## Fast CLI workflow

Use this for a one-off download.

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv --cache --retries 5 --retry-on-empty
```

Recommended defaults:

- `-f csv` when the user wants backtesting or spreadsheet-ready data
- `--cache` for repeated requests
- `--retries 5 --retry-on-empty` for better resilience
- `-bs 5 -bp 2000` or lower batch size and higher pause for larger requests

## Historical OHLC candles through Node.js

```js
const { getHistoricalRates } = require("dukascopy-node");

(async () => {
  const data = await getHistoricalRates({
    instrument: "eurusd",
    dates: {
      from: new Date("2024-02-13"),
      to: new Date("2024-02-15"),
    },
    timeframe: "m1",
    format: "json",
    priceType: "bid",
    volumes: true,
    useCache: true,
    retryCount: 5,
    retryOnEmpty: true,
  });

  console.log(data);
})();
```

## Historical tick data

Tick data is raw bid/ask price change data. It does not contain OHLC columns.

CLI:

```bash
npx dukascopy-node -i btcusd -from 2019-01-13 -to 2019-01-14 -t tick -f csv
```

Node.js:

```js
const { getHistoricalRates } = require("dukascopy-node");

(async () => {
  const data = await getHistoricalRates({
    instrument: "eurusd",
    dates: {
      from: new Date("2021-03-30"),
      to: new Date("2021-03-31"),
    },
    timeframe: "tick",
    format: "json",
  });

  console.log(data);
})();
```

Expected tick JSON shape:

```json
[
  {
    "timestamp": 1585526400104,
    "askPrice": 1.11369,
    "bidPrice": 1.11361,
    "askVolume": 0.75,
    "bidVolume": 0.75
  }
]
```

## Large historical downloads

For large candle downloads, use cache and batching:

```bash
npx dukascopy-node -i eurusd -from 2019-06-01 -to 2019-07-01 -t m1 -f csv -bs 5 -bp 2000 --cache --retries 10 --retry-on-empty
```

For large tick downloads, chunk by day or week instead of one huge command:

```bash
python scripts/generate_cli_chunks.py --instrument eurusd --from 2023-01-01 --to 2023-01-08 --timeframe tick --format csv --chunk-days 1 --batch-size 2 --batch-pause 3000 --cache --retries 10 --retry-on-empty
```

## File naming convention

Use stable names that encode source, instrument, timeframe, date range, and format:

```text
dukascopy_eurusd_m1_2024-02-13_2024-02-15_bid.csv
dukascopy_eurusd_tick_2024-02-13_2024-02-14.csv
```
