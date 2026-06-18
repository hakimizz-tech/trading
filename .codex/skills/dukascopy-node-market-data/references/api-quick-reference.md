# Dukascopy Node API Quick Reference

## Installation

```bash
npm install dukascopy-node --save
# or
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv
```

Node.js 12 or newer is required.

## Main Node.js functions

```js
const { getHistoricalRates, getRealTimeRates } = require("dukascopy-node");
```

- `getHistoricalRates(config)`: fetches historical candles or tick data from Dukascopy historical datafeed artifacts.
- `getRealTimeRates(config)`: fetches recent or ranged live market data from Dukascopy free server API.

## Supported timeframes

- `tick`: raw price changes, no OHLC columns
- `s1`: 1 second candles
- `m1`: 1 minute candles
- `m5`: 5 minute candles
- `m15`: 15 minute candles
- `m30`: 30 minute candles
- `h1`: 1 hour candles
- `h4`: 4 hour candles
- `d1`: daily candles
- `mn1`: monthly candles

## Price types

- `bid`: default for historical CLI downloads
- `ask`: use when the user specifically needs ask-side candles

For tick data, the JSON shape uses both bid and ask fields:

```json
{
  "timestamp": 1585526400104,
  "askPrice": 1.11369,
  "bidPrice": 1.11361,
  "askVolume": 0.75,
  "bidVolume": 0.75
}
```

## Output formats

### CSV

Best for backtesting tools, spreadsheets, and Python ingestion.

```text
timestamp,open,high,low,close,volume
1612137600000,1.21225,1.21363,1.2056,1.20676,165569.8187
```

### JSON

Best for JavaScript pipelines and structured processing.

```json
[
  {
    "timestamp": 1612137600000,
    "open": 1.21225,
    "high": 1.21363,
    "low": 1.2056,
    "close": 1.20676,
    "volume": 165569.8187
  }
]
```

### Array

Best for compact storage and custom numerical processing.

```json
[
  [1612137600000, 1.21225, 1.21363, 1.2056, 1.20676, 165569.8187]
]
```

## CLI flag mapping

| Purpose | CLI flag | Node config field |
|---|---:|---|
| Instrument | `-i`, `--instrument` | `instrument` |
| From date | `-from`, `--date-from` | `dates.from` |
| To date | `-to`, `--date-to` | `dates.to` |
| Timeframe | `-t`, `--timeframe` | `timeframe` |
| Price type | `-p`, `--price-type` | `priceType` |
| Volumes | `-v`, `--volumes` | `volumes` |
| Format | `-f`, `--format` | `format` |
| Directory | `-dir`, `--directory` | output handling is CLI-specific |
| Batch size | `-bs`, `--batch-size` | `batchSize` |
| Batch pause | `-bp`, `--batch-pause` | `pauseBetweenBatchesMs` |
| Cache | `-ch`, `--cache` | `useCache` |
| Cache path | `-chpath`, `--cache-path` | `cacheFolderPath` |
| Retries | `-r`, `--retries` | `retryCount` |
| Retry empty | `-re`, `--retry-on-empty` | `retryOnEmpty` |
| No fail after retries | `-fr`, `--no-fail-after-retries` | `failAfterRetryCount` set to false |
| Retry pause | `-rp`, `--retry-pause` | `pauseBetweenRetriesMs` |
| Debug | `-d`, `--debug` | `debug` |
| Date format | `-df`, `--date-format` | `dateFormat` |
| Time zone | `-tz`, `--time-zone` | `timeZone` |

## Instrument categories

The documentation lists many categories including bonds, crypto assets, agriculture, energy, metals, ETFs, forex currencies, forex metals, regional indices, and country-specific stocks. Always verify the exact instrument id from the official list when an instrument is unfamiliar.
