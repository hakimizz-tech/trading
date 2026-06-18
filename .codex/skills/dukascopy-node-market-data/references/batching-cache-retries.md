# Batching, Cache, Retries, and Empty Data

## Why batching matters

Dukascopy data is downloaded as many binary artifacts from datafeed servers. The library generates artifact URLs, downloads them, decompresses them, parses them, and aggregates them.

For large ranges, reduce the batch size and increase the pause so that downloads do not overwhelm the remote servers.

Default values:

- `batchSize`: `10`
- `pauseBetweenBatchesMs`: `1000`

Conservative large-download settings:

```bash
-bs 2 -bp 3000
```

or in Node.js:

```js
{
  batchSize: 2,
  pauseBetweenBatchesMs: 3000
}
```

## Custom batching example

CLI:

```bash
npx dukascopy-node -i eurusd -from 2019-06-01 -to 2019-07-01 -t m1 -bs 15 -bp 2000
```

Node.js:

```js
const data = await getHistoricalRates({
  instrument: "eurusd",
  dates: {
    from: new Date("2019-06-01"),
    to: new Date("2019-07-01"),
  },
  timeframe: "m1",
  batchSize: 15,
  pauseBetweenBatchesMs: 2000,
});
```

## Cache

Enable cache for repeated work:

```bash
npx dukascopy-node -i eurusd -from 2021-02-01 -to 2021-03-01 -t m1 -f json --cache
```

Node.js:

```js
const data = await getHistoricalRates({
  instrument: "eurusd",
  dates: {
    from: new Date("2021-02-01"),
    to: new Date("2021-03-01"),
  },
  timeframe: "m1",
  format: "json",
  useCache: true,
});
```

Default cache folder:

```text
.dukascopy-cache
```

Use a project-level cache path when running repeatable research:

```bash
--cache --cache-path ./data/.dukascopy-cache
```

## Retrying failed requests

For network errors:

```bash
npx dukascopy-node -i usdcad -from 2023-05-11 -to 2023-05-12 -t tick -f csv --retries 15
```

Node.js:

```js
{
  retryCount: 15,
  pauseBetweenRetriesMs: 500
}
```

## Retrying empty responses

For successful but empty responses:

```bash
npx dukascopy-node -i usdcad -from 2023-05-11 -to 2023-05-12 -t tick -f csv --retries 15 --retry-on-empty
```

Node.js:

```js
{
  retryCount: 15,
  retryOnEmpty: true
}
```

## Do not fail after exhausted retries

Use only when an empty result is acceptable and the pipeline should continue:

```bash
npx dukascopy-node -i usdcad -from 2023-05-11 -to 2023-05-12 -t tick -f csv --retries 15 --retry-on-empty --no-fail-after-retries
```

Node.js equivalent intent:

```js
{
  retryCount: 15,
  retryOnEmpty: true,
  failAfterRetryCount: false
}
```

## Recommended profiles

### Small one-off candle download

```bash
--cache --retries 5 --retry-on-empty
```

### Month of M1 data

```bash
--cache -bs 5 -bp 2000 --retries 10 --retry-on-empty
```

### Tick data

```bash
--cache -bs 1 -bp 3000 --retries 15 --retry-on-empty
```

Prefer day-by-day chunks for tick data.
