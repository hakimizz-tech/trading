---
name: yfinance-market-data
description: Builds Python workflows using yfinance for Yahoo Finance market data. Use when user asks for yfinance code, stock or ETF historical data, Ticker or Tickers usage, yf.download, market data CSV exports, financial statements, dividends, splits, options chains, search, lookup, screeners, sector or industry data, WebSocket streaming, caching, price repair, MultiIndex columns, or Yahoo Finance troubleshooting.
license: MIT
compatibility: Requires Python 3.9 or newer, internet access, yfinance, pandas, and optional plotting or caching dependencies.
metadata:
  author: Hakeem Keem
  version: 1.0.0
  category: finance-data
  tags:
    - yfinance
    - yahoo-finance
    - market-data
    - pandas
    - stocks
---

# yfinance Market Data Skill

## Purpose

Use this skill to build reliable Python workflows around `yfinance`, including historical price downloads, single-ticker research, multi-ticker datasets, corporate actions, financial statements, search and lookup, screening, sector and industry analysis, cache configuration, WebSocket streaming, and common troubleshooting.

This skill is for market-data retrieval and analysis workflows. Do not present outputs as financial advice, trade recommendations, or guaranteed investment signals.

## Default workflow

1. Clarify the instrument universe:
   - Single ticker: use `yf.Ticker("AAPL")`.
   - Multiple tickers or bulk OHLCV data: use `yf.download(...)`.
   - Search by company name or ambiguous symbol: use `yf.Search` or `yf.Lookup`.
   - Screens: use `yf.EquityQuery`, `yf.FundQuery`, `yf.ETFQuery`, then `yf.screen`.
   - Sector or industry summaries: use `yf.Sector` or `yf.Industry`.
   - Live stream: use `yf.WebSocket` or `yf.AsyncWebSocket`.
2. Clarify the required output: DataFrame preview, CSV, parquet, JSON, chart, notebook cell, backtest input, or reusable script.
3. Generate defensive code:
   - Validate ticker inputs.
   - Check for empty DataFrames.
   - Normalize dates and timezones.
   - Flatten MultiIndex columns when saving to CSV unless the user wants pandas MultiIndex.
   - Use `repair=True` when the user asks for data quality repair or international market price anomalies.
4. Make the workflow reproducible:
   - Pin parameters explicitly: `period`, `start`, `end`, `interval`, `auto_adjust`, `actions`, `repair`, `threads`, and `multi_level_index`.
   - Save raw data before transformation when doing research or backtesting.

## Quick install pattern

```bash
python -m pip install --upgrade yfinance pandas
```

Optional packages:

```bash
python -m pip install matplotlib requests-cache requests-ratelimiter pyrate-limiter
```

## Common code patterns

### Single ticker research

```python
import yfinance as yf

ticker = yf.Ticker("MSFT")

history = ticker.history(period="6mo", interval="1d", auto_adjust=True)
info = ticker.info
fast_info = ticker.fast_info
dividends = ticker.dividends
splits = ticker.splits
calendar = ticker.calendar
news = ticker.news

print(history.tail())
print(fast_info)
```

Use `Ticker` when the user wants one instrument and related metadata, financials, options chains, corporate actions, recommendations, or news.

### Multi-ticker historical data

```python
import yfinance as yf

data = yf.download(
    tickers=["AAPL", "MSFT", "SPY"],
    start="2024-01-01",
    end="2025-01-01",
    interval="1d",
    auto_adjust=True,
    actions=True,
    repair=False,
    threads=True,
    group_by="column",
    multi_level_index=True,
    progress=False,
)

if data.empty:
    raise RuntimeError("No data returned. Check tickers, date range, interval, or network access.")

print(data.tail())
```

### Flatten MultiIndex columns before CSV

```python
if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
    data.columns = ["_".join(str(part) for part in col if str(part)) for col in data.columns]
data.to_csv("prices.csv")
```

### Price repair

```python
data = yf.download("7203.T", period="5y", interval="1d", repair=True, progress=False)
```

Use `repair=True` when the user suspects 100x currency-unit errors, missing rows, bad dividend adjustments, or non-US market anomalies. Mention that repaired rows may include a `Repaired?` column.

### Search and lookup

```python
import yfinance as yf

search = yf.Search("Safaricom", max_results=10, news_count=0)
print(search.quotes)

lookup = yf.Lookup("Apple")
print(lookup.get_stock(count=10))
```

### Screening

```python
import yfinance as yf

query = yf.EquityQuery("and", [
    yf.EquityQuery("eq", ["region", "us"]),
    yf.EquityQuery("gt", ["intradaymarketcap", 10_000_000_000]),
])

result = yf.screen(query, size=25, sortField="intradaymarketcap", sortAsc=False)
print(result)
```

### WebSocket streaming

```python
import yfinance as yf

ws = yf.WebSocket()
ws.subscribe(["AAPL", "MSFT"])
ws.listen()
```

For async workflows:

```python
import asyncio
import yfinance as yf

async def main():
    ws = yf.AsyncWebSocket()
    await ws.subscribe(["AAPL", "MSFT"])
    await ws.listen()

asyncio.run(main())
```

Use streaming examples carefully. Tell the user to add a stop condition or timeout in production scripts.

## Bundled references

- `references/api-quick-reference.md` for the public API map and when to use each object.
- `references/historical-data-patterns.md` for `download`, `Ticker.history`, intervals, date ranges, actions, adjustment, and CSV export.
- `references/ticker-research-patterns.md` for company metadata, statements, dividends, splits, options, news, and analyst data.
- `references/search-screening-sector-patterns.md` for `Search`, `Lookup`, `Market`, `Calendars`, `Sector`, `Industry`, and screeners.
- `references/advanced-operations.md` for logging, config, cache, persistent cache, timezones, price repair, and network/session patterns.
- `references/live-data-patterns.md` for `WebSocket` and `AsyncWebSocket`.
- `references/troubleshooting.md` for common failures.

## Script usage

```bash
python scripts/yf_health_check.py --ticker AAPL
python scripts/download_history_to_csv.py --tickers AAPL MSFT SPY --start 2024-01-01 --end 2025-01-01 --interval 1d --auto-adjust --actions --flatten --output prices.csv
python scripts/ticker_snapshot.py --ticker MSFT --period 1y --output msft_snapshot.json
python scripts/basic_equity_screen.py --region us --min-market-cap 10000000000 --size 25 --output screen.json
```

## Safety and data-quality rules

- Always state that Yahoo Finance data can be delayed, revised, incomplete, or unavailable for some exchanges.
- Avoid pretending that yfinance is a broker or execution API.
- Do not place trades or generate broker-order code from yfinance alone.
- For backtests, avoid look-ahead bias by using historical values as of the test date.
- Be careful with `auto_adjust`; adjusted OHLC is useful for total-return research, while raw OHLC may be required for execution-style simulations.
- For intraday intervals, expect stricter availability limits and possible missing data.
- For multi-ticker CSV exports, flatten MultiIndex columns unless the user specifically wants pandas MultiIndex preservation.
- Use `repair=True` for suspicious price jumps, but keep the original downloaded data for auditability when doing serious research.

## Test prompts

Should trigger this skill:

- "Write yfinance code to download SPY and QQQ daily data."
- "Use yf.download and save the data to CSV."
- "How do I flatten yfinance MultiIndex columns?"
- "Build a yfinance stock screener using EquityQuery."
- "Stream AAPL live prices with yfinance WebSocket."
- "Fetch dividends, splits, financial statements, and options chains for MSFT."
- "Set yfinance cache location."
- "Repair Yahoo Finance price errors."

Should not trigger this skill:

- "Explain forex lot sizing in MetaTrader."
- "Create a Django REST API."
- "Build a Cisco switch configuration."
- "Generate a marketing call script."
