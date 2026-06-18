# yfinance Troubleshooting

## `ModuleNotFoundError: No module named 'yfinance'`

Install in the same environment running the script:

```bash
python -m pip install --upgrade yfinance
```

In notebooks:

```python
import sys
!{sys.executable} -m pip install --upgrade yfinance
```

## Empty DataFrame

Likely causes:

- Wrong ticker or missing exchange suffix.
- Date range has no trading days.
- Intraday range too long.
- Yahoo endpoint temporarily unavailable.
- Network, DNS, proxy, SSL, or firewall issue.

Small test:

```python
import yfinance as yf
data = yf.download("AAPL", period="5d", interval="1d", progress=False)
print(data.tail())
```

If this small test works, narrow the problem to ticker, date range, or interval.

## MultiIndex columns are confusing

Flatten:

```python
if data.columns.nlevels > 1:
    data.columns = ["_".join(map(str, col)).strip("_") for col in data.columns]
```

Or read a saved MultiIndex CSV with:

```python
df = pd.read_csv("file.csv", header=[0, 1], index_col=0, parse_dates=True)
```

## Prices look wrong by 100x

Try:

```python
data = yf.download("TICKER", period="max", repair=True, progress=False)
```

Also compare raw vs repaired data before trusting the result.

## Slow downloads

- Use `threads=True` for many tickers.
- Cache raw downloads locally.
- Reduce ticker count or date range.
- Use daily data instead of intraday.
- Add a cached session for repeated calls.

## `KeyError` from `Ticker.info`

Yahoo profile keys vary by ticker. Use `.get()`:

```python
info = t.info or {}
market_cap = info.get("marketCap")
```

## Options chain fails

Not every ticker has options or Yahoo options data. Check first:

```python
if t.options:
    chain = t.option_chain(t.options[0])
else:
    print("No options expirations available")
```

## Timezone cache permission error

Set a writable cache path:

```python
import yfinance as yf
yf.set_tz_cache_location("./.cache/yfinance")
```

## Data mismatch against broker

Common causes are adjusted vs raw prices, exchange timezone differences, missing pre/post market data, delayed Yahoo data, different corporate action treatment, and broker-specific symbols.
