# Real-Time Data Workflows

## Function

Use `getRealTimeRates` for recent live market data from Dukascopy's free server API.

```js
const { getRealTimeRates } = require("dukascopy-node");
```

## Last N ticks

```js
const { getRealTimeRates } = require("dukascopy-node");

(async () => {
  const data = await getRealTimeRates({
    instrument: "eurusd",
    timeframe: "tick",
    format: "json",
    last: 10,
  });

  console.log(data);
})();
```

## Config fields

| Field | Purpose |
|---|---|
| `instrument` | Required instrument id |
| `timeframe` | `tick`, `s1`, `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `d1`, `mn1` |
| `priceType` | `bid` or `ask` |
| `volumes` | Include volume data |
| `format` | `array`, `json`, or `csv` |
| `last` | Number of latest items to fetch if dates are not provided |
| `dates.from` | Start datetime for a ranged live query |
| `dates.to` | End datetime, defaults to current time when omitted |

## Date input forms

For `dates.from` and `dates.to`, acceptable forms include:

- JavaScript `Date` object: `new Date("2025-01-01")`
- ISO string: `"2025-01-01T00:00:00Z"`
- Unix timestamp in milliseconds: `1704067200000`

## Return shapes

### OHLC array

```js
[1704067200000, 1.0945, 1.0950, 1.0940, 1.0948, 123.45]
```

### Tick array

```js
[1704067200000, 1.0945, 1.0943, 10.5, 12.3]
```

### OHLC JSON

```json
{
  "timestamp": 1704067200000,
  "open": 1.0945,
  "high": 1.0950,
  "low": 1.0940,
  "close": 1.0948,
  "volume": 123.45
}
```

### Tick JSON

```json
{
  "timestamp": 1704067200000,
  "askPrice": 1.0945,
  "bidPrice": 1.0943,
  "askVolume": 10.5,
  "bidVolume": 12.3
}
```

## Usage guidance

- Use real-time data for snapshots, not historical backfills.
- Use `getHistoricalRates` when the user requests archived historical data.
- Always label real-time data as live or recent, because it changes over time.
