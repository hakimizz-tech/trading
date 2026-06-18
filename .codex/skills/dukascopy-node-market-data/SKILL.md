---
name: dukascopy-node-market-data
description: Builds Dukascopy historical and real-time market data workflows using dukascopy-node. Use when the user asks to download Dukascopy data, fetch tick data, get forex or crypto candles, export CSV or JSON, configure batching, cache, retries, date formatting, timezone conversion, or use getHistoricalRates and getRealTimeRates.
license: MIT
compatibility: Requires Node.js 12 or newer and network access to Dukascopy datafeed servers. Optional Python scripts need Python 3.
metadata:
  author: Hakeem Keem
  version: 1.0.0
  package: dukascopy-node
  category: market-data
---

# Dukascopy Node Market Data Skill

## Purpose

Use this skill to create reliable `dukascopy-node` workflows for downloading and processing Dukascopy historical candles, historical ticks, and real-time tick or candle snapshots.

Prefer this skill when the user mentions:

- `dukascopy-node`, Dukascopy historical data, Dukascopy tick data, or Dukascopy real-time rates
- `getHistoricalRates`, `getRealTimeRates`, `npx dukascopy-node`, or `dukascopy-cli`
- exporting market data to CSV, JSON, or array format
- batching, cache, retries, empty responses, date formatting, or timezone conversion
- forex, crypto, metals, commodities, ETFs, stocks, or other instruments available from Dukascopy

## Operating Principles

1. **Clarify the market data request before downloading.** Confirm instrument, date range, timeframe, output format, price type, and destination file when any are missing.
2. **Default to safe, small downloads.** For tick data, never assume that a long date range is acceptable. Tick data can become gigabytes. Suggest chunking by day or week.
3. **Use CLI for quick one-off downloads.** Use `npx dukascopy-node` when the user needs a fast terminal command.
4. **Use Node.js API for repeatable pipelines.** Use `getHistoricalRates` for historical data and `getRealTimeRates` for live snapshots.
5. **Respect Dukascopy servers.** For large jobs, reduce `batchSize`, increase `pauseBetweenBatchesMs`, enable cache, and add retries.
6. **Preserve timestamp semantics.** Unless the user asks otherwise, explain that timestamps are Unix milliseconds in UTC. Use date formatting and timezone conversion only when requested.
7. **Do not hide data limitations.** Some instruments, weekends, holidays, or datafeed artifacts may return empty data. Use retries and handle empty outputs explicitly.

## Quick Setup

Check Node.js version:

```bash
node --version
```

Install locally in a project:

```bash
npm install dukascopy-node --save
```

Or use without permanent installation:

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv
```

For reusable scripts in this skill folder, run from the skill root or copy the scripts into the user's project.

## Decision Workflow

### 1. Identify request type

- Historical OHLC candles: use timeframe `s1`, `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `d1`, or `mn1`.
- Historical tick data: use timeframe `tick`. Warn that output is bid/ask ticks, not OHLC.
- Real-time snapshot: use `getRealTimeRates` and usually `last: 10` unless the user specifies another count.
- Data engineering pipeline: plan file naming, date chunking, cache directory, retries, and storage format.

### 2. Validate required fields

Required for historical downloads:

- `instrument`: lowercase Dukascopy instrument id, for example `eurusd`, `btcusd`, `xauusd`
- `from`: `yyyy-mm-dd`
- `to`: `yyyy-mm-dd` or `now`
- `timeframe`: one of `tick`, `s1`, `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `d1`, `mn1`
- `format`: `csv`, `json`, or `array`

Recommended optional fields:

- `priceType`: `bid` or `ask`
- `volumes`: true when volume columns are needed
- `useCache`: true for repeated work
- `batchSize` and `pauseBetweenBatchesMs` for large ranges
- `retryCount`, `retryOnEmpty`, and `failAfterRetryCount` for unstable or empty artifacts

### 3. Choose a command or script

Quick CLI command:

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv --cache --retries 5 --retry-on-empty
```

Reusable Node script:

```bash
node scripts/fetch_historical_rates.js --instrument eurusd --from 2024-02-13 --to 2024-02-15 --timeframe m1 --format csv --output data/eurusd_m1.csv --cache
```

Real-time snapshot:

```bash
node scripts/fetch_realtime_rates.js --instrument eurusd --timeframe tick --format json --last 10
```

### 4. Handle large tick downloads

For tick data over multiple days, recommend chunked commands such as:

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-14 -t tick -f csv -bs 2 -bp 3000 --cache --retries 10 --retry-on-empty
```

Then repeat day-by-day or generate a batch plan using `scripts/generate_cli_chunks.py`.

## Reference Files

Use these bundled references when the task needs detail:

- `references/api-quick-reference.md` for function names, CLI flags, config mapping, output fields, and timeframes
- `references/historical-data-workflows.md` for historical candle and tick recipes
- `references/output-formats-timezones.md` for CSV, JSON, array, date formatting, and timezone conversion
- `references/batching-cache-retries.md` for large downloads, cache, retries, and empty response handling
- `references/real-time-data.md` for `getRealTimeRates` usage
- `references/data-engineering-practices.md` for chunking, storage, validation, and pipeline conventions
- `references/troubleshooting.md` for common installation, runtime, and empty-data issues

## Bundled Scripts

- `scripts/check_environment.js`: checks Node.js version and whether `dukascopy-node` is resolvable
- `scripts/fetch_historical_rates.js`: reusable historical downloader using `getHistoricalRates`
- `scripts/fetch_realtime_rates.js`: reusable real-time snapshot script using `getRealTimeRates`
- `scripts/generate_cli_chunks.py`: generates day or week CLI commands for large jobs
- `scripts/validate_output_file.py`: basic validation for generated CSV or JSON files

## Examples

### Example 1: User wants EURUSD M1 candles as CSV

User says: "Download EURUSD 1-minute data from Dukascopy for February 2024 as CSV."

Action:

```bash
npx dukascopy-node -i eurusd -from 2024-02-01 -to 2024-03-01 -t m1 -f csv --cache --retries 5 --retry-on-empty
```

Explain that this outputs OHLC candles with timestamps in Unix milliseconds unless date formatting is requested.

### Example 2: User wants tick data for a long period

User says: "Get EURUSD tick data for 2023."

Action:

- Warn that tick data for a full year can be very large.
- Propose chunking by day or week.
- Use cache and conservative batching.
- Generate commands with `scripts/generate_cli_chunks.py`.

Example:

```bash
python scripts/generate_cli_chunks.py --instrument eurusd --from 2023-01-01 --to 2023-02-01 --timeframe tick --format csv --chunk-days 1 --batch-size 2 --batch-pause 3000 --cache
```

### Example 3: User wants live data

User says: "Fetch the last 10 live ticks for EURUSD."

Action:

```bash
node scripts/fetch_realtime_rates.js --instrument eurusd --timeframe tick --format json --last 10
```

## Quality Checklist

Before giving a final command or script:

- Instrument id is lowercase and likely valid.
- Date range uses `yyyy-mm-dd` for historical data.
- Timeframe is supported.
- Tick data requests include a size warning when the range is large.
- Large downloads use cache, batching, and retries.
- Output format matches the user's downstream need.
- File names include instrument, timeframe, and date range when saving data.
- Empty outputs are treated as a data availability or server-response issue, not automatically as a code failure.
