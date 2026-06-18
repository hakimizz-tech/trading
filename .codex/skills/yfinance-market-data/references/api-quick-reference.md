# yfinance API Quick Reference

## Import convention

```python
import yfinance as yf
```

## Main objects and when to use them

### `yf.Ticker`

Use for one instrument and rich metadata.

```python
t = yf.Ticker("AAPL")
hist = t.history(period="1y", interval="1d")
info = t.info
fast = t.fast_info
dividends = t.dividends
splits = t.splits
actions = t.actions
calendar = t.calendar
news = t.news
```

### `yf.Tickers`

Use when the user wants multiple `Ticker` objects rather than one combined OHLCV table.

```python
tickers = yf.Tickers("AAPL MSFT SPY")
print(tickers.tickers["AAPL"].history(period="1mo"))
```

### `yf.download`

Use for bulk historical data.

```python
data = yf.download(["AAPL", "MSFT"], period="1y", interval="1d", progress=False)
```

Important parameters:

- `tickers`: ticker string or list.
- `start`, `end`: explicit date range.
- `period`: alternative to `start` and `end`, such as `"1y"` or `"max"`.
- `interval`: `"1d"`, `"1wk"`, `"1mo"`, or intraday intervals such as `"1m"`, `"5m"`, `"15m"`, `"1h"`.
- `auto_adjust`: adjust OHLC automatically.
- `actions`: include dividends and stock splits.
- `repair`: attempt to repair Yahoo price errors.
- `threads`: use multithreading for many symbols.
- `multi_level_index`: keep pandas MultiIndex columns.

### `yf.Search`

Use when the user asks to find tickers from a company name or keyword.

```python
s = yf.Search("Tesla", max_results=10, news_count=0)
quotes = s.quotes
```

### `yf.Lookup`

Use for quote lookup by category.

```python
lookup = yf.Lookup("Apple")
stocks = lookup.get_stock(count=10)
crypto = lookup.get_cryptocurrency(count=10)
```

### `yf.EquityQuery`, `yf.FundQuery`, `yf.ETFQuery`, and `yf.screen`

Use for Yahoo Finance screeners.

```python
query = yf.EquityQuery("gt", ["intradaymarketcap", 10_000_000_000])
result = yf.screen(query, size=25)
```

### `yf.Sector` and `yf.Industry`

Use for sector and industry metadata and summaries.

```python
tech = yf.Sector("technology")
print(tech.overview)
print(tech.industries)
```

### `yf.WebSocket` and `yf.AsyncWebSocket`

Use for live price streaming.

```python
ws = yf.WebSocket()
ws.subscribe(["AAPL"])
ws.listen()
```

### `yf.set_tz_cache_location`

Use when the user wants cache control or a custom cache path.

```python
yf.set_tz_cache_location("./.cache/yfinance")
```

### `yf.config.debug.logging`

Use only when debugging connection or parsing problems.

```python
yf.config.debug.logging = True
```

## Decision table

| User asks for | Use |
|---|---|
| One ticker with metadata | `yf.Ticker` |
| Several tickers historical prices | `yf.download` |
| Multiple rich ticker objects | `yf.Tickers` |
| Company-name search | `yf.Search` or `yf.Lookup` |
| Filters such as market cap, region, sector | `yf.EquityQuery` and `yf.screen` |
| ETF or fund filters | `yf.ETFQuery`, `yf.FundQuery`, and `yf.screen` |
| Live prices | `yf.WebSocket` or `yf.AsyncWebSocket` |
| Cache path | `yf.set_tz_cache_location` |
| Debug output | `yf.config.debug.logging = True` |
