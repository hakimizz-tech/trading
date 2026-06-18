# Search, Screening, Sector, Industry, Market, and Calendar Patterns

## Search

Use `yf.Search` when the user has a company name, keyword, or fuzzy query.

```python
import yfinance as yf

s = yf.Search("Safaricom", max_results=10, news_count=0)
print(s.quotes)
```

## Lookup

Use `yf.Lookup` for categorized lookups.

```python
lookup = yf.Lookup("Apple")
stocks = lookup.get_stock(count=10)
funds = lookup.get_mutualfund(count=10)
crypto = lookup.get_cryptocurrency(count=10)
currency = lookup.get_currency(count=10)
```

Method availability can vary by yfinance version. If a method fails, inspect `dir(lookup)` or check the installed version.

## Equity screen

```python
import yfinance as yf

query = yf.EquityQuery("and", [
    yf.EquityQuery("eq", ["region", "us"]),
    yf.EquityQuery("gt", ["intradaymarketcap", 10_000_000_000]),
])

result = yf.screen(
    query,
    size=25,
    sortField="intradaymarketcap",
    sortAsc=False,
)
```

## Query construction

Value operations include `eq`, `is-in`, `btwn`, `gt`, `lt`, `gte`, and `lte`. Logical operations include `and` and `or`.

Build nested queries with a small number of rules first, then add complexity after the query returns valid results.

## Fund and ETF screens

```python
fund_query = yf.FundQuery("eq", ["region", "us"])
funds = yf.screen(fund_query, size=10)

etf_query = yf.ETFQuery("eq", ["region", "us"])
etfs = yf.screen(etf_query, size=10)
```

## Sector

```python
tech = yf.Sector("technology")
print(tech.overview)
print(tech.industries)
print(tech.top_companies)
print(tech.top_etfs)
print(tech.top_mutual_funds)
```

## Industry

```python
industry = yf.Industry("software-application")
print(industry.overview)
print(industry.top_companies)
```

## Market and calendars

Use `yf.Market` and `yf.Calendars` when the user specifically asks for market summaries or calendar event data. APIs can differ by version, so write exploratory code with `dir()` when necessary.

```python
import yfinance as yf
print([name for name in dir(yf) if name in ["Market", "Calendars"]])
```

## Output normalization

Yahoo screen and search responses may be dictionaries, lists, or DataFrames depending on method and version. Normalize before saving:

```python
import pandas as pd

def to_dataframe(obj):
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, list):
        return pd.DataFrame(obj)
    if isinstance(obj, dict):
        for key in ["quotes", "finance", "results"]:
            if key in obj and isinstance(obj[key], list):
                return pd.DataFrame(obj[key])
        return pd.json_normalize(obj)
    return pd.DataFrame({"value": [obj]})
```
