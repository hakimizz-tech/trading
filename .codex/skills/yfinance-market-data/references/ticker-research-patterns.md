# Ticker Research Patterns

## Company summary

```python
import yfinance as yf

t = yf.Ticker("MSFT")
print(t.fast_info)
print(t.info)
```

Prefer `fast_info` for quick price and market metadata when available. Use `info` when you need a broader Yahoo profile, but handle missing keys defensively.

```python
info = t.info or {}
sector = info.get("sector")
industry = info.get("industry")
market_cap = info.get("marketCap")
```

## Financial statements

Common properties:

```python
income = t.income_stmt
quarterly_income = t.quarterly_income_stmt
balance = t.balance_sheet
quarterly_balance = t.quarterly_balance_sheet
cashflow = t.cashflow
quarterly_cashflow = t.quarterly_cashflow
```

Defensive export pattern:

```python
for name, df in {
    "income_stmt": t.income_stmt,
    "balance_sheet": t.balance_sheet,
    "cashflow": t.cashflow,
}.items():
    if df is not None and not df.empty:
        df.to_csv(f"{name}.csv")
```

## Dividends, splits, and actions

```python
dividends = t.dividends
splits = t.splits
actions = t.actions
```

## Options chains

```python
expirations = t.options
if expirations:
    chain = t.option_chain(expirations[0])
    calls = chain.calls
    puts = chain.puts
```

Always check that `t.options` is non-empty.

## Calendar and events

```python
calendar = t.calendar
earnings_dates = t.get_earnings_dates(limit=12)
```

Calendar availability varies by ticker.

## News

```python
news = t.news
for item in news[:5]:
    title = item.get("title", "Untitled")
    link = item.get("link")
    print(title, link)
```

News payload structure can vary. Avoid assuming every item has all fields.

## Avoid fragile code

Do not write:

```python
market_cap = t.info["marketCap"]
```

Prefer:

```python
market_cap = (t.info or {}).get("marketCap")
```

Yahoo data is not uniformly populated across asset types.
