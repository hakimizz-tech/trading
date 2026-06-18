# Advanced yfinance Operations

## Debug logging

Use only when troubleshooting:

```python
import yfinance as yf
yf.config.debug.logging = True
```

Debug mode may print verbose output and should not be enabled in normal scripts.

## Cache location

Set the timezone cache location when you need deterministic project-local cache behavior:

```python
import yfinance as yf
yf.set_tz_cache_location("./.cache/yfinance")
```

This is useful for CI jobs, Docker containers, reproducible research repositories, and locked-down environments where the default user cache path is not writable.

## Persistent cache and network etiquette

Good practice:

- Reuse sessions for repeated calls.
- Avoid repeatedly downloading the same large dataset.
- Cache downloaded raw data to CSV or parquet.
- Add retries and backoff in production.
- Avoid hammering Yahoo Finance endpoints.

## Session pattern with caching and rate limiting

```python
import yfinance as yf
from requests_cache import CachedSession
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket
from pyrate_limiter import Duration, RequestRate, Limiter

class CachedLimiterSession(CachedSession, LimiterMixin):
    pass

session = CachedLimiterSession(
    cache_name="yfinance_cache",
    expire_after=3600,
    limiter=Limiter(RequestRate(2, Duration.SECOND * 5)),
    bucket_class=MemoryQueueBucket,
)

ticker = yf.Ticker("AAPL", session=session)
hist = ticker.history(period="1y")
```

Adjust rate limits based on your workflow.

## Locale and exchange suffixes

Yahoo symbols often require exchange suffixes:

- London: `.L`
- Toronto: `.TO`
- Australia: `.AX`
- Tokyo: `.T`
- Hong Kong: `.HK`

When the user asks for a local exchange ticker, search first, then verify by downloading a small sample.

## Data integrity workflow

For research pipelines:

1. Download raw data with explicit parameters.
2. Save raw file.
3. Validate non-empty, monotonic datetime index, no duplicated dates, positive OHLC prices, and non-negative volume.
4. Optionally download repaired version with `repair=True`.
5. Compare raw vs repaired.
6. Save cleaned research dataset separately.

## Reproducibility note

Yahoo Finance data may be revised or temporarily unavailable. For serious research, store snapshots of raw downloaded data with timestamp, package version, and parameters.
