# Output Formats, Date Formatting, and Timezones

## Timestamp defaults

By default, dates are returned as Unix timestamps in milliseconds. Treat them as UTC unless a date format and timezone conversion have been explicitly applied.

## CSV

Use CSV when the data will be consumed by Python, pandas, Excel, vectorbt, backtesting.py, Backtrader, or custom research scripts.

```bash
npx dukascopy-node -i eurusd -from 2021-02-01 -to 2021-03-01 -t d1 -f csv
```

## JSON

Use JSON when the user wants structured JavaScript or TypeScript processing.

```bash
npx dukascopy-node -i eurusd -from 2021-02-01 -to 2021-03-01 -t d1 -f json
```

## Array

Use array format for compact numeric output.

```bash
npx dukascopy-node -i eurusd -from 2021-02-01 -to 2021-03-01 -t d1 -f array
```

## Custom date format

Use `--date-format` with a Day.js-compatible format string.

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv --date-format "YYYY-MM-DD HH:mm:ss"
```

Common formats:

| Format | Example |
|---|---|
| `YYYY-MM` | `2024-02` |
| `YYYY-MM-DD` | `2024-02-13` |
| `YYYY-MM-DD HH:mm` | `2024-02-13 00:00` |
| `YYYY-MM-DD HH:mm:ss` | `2024-02-13 00:00:00` |
| `YYYY-MM-DD HH:mm:ss.SSS` | `2024-02-13 00:00:00.000` |
| `YYYY-MM-DD HH:mm:ss.SSSZ` | `2024-02-13 00:00:00.000+00:00` |
| `iso` | `2024-02-13T00:00:00.000Z` |

## Timezone conversion

`--time-zone` works together with `--date-format`.

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv --date-format "YYYY-MM-DD HH:mm" --time-zone Africa/Nairobi
```

Use timezone conversion only when the user explicitly wants local timestamps. For trading research, UTC timestamps are usually safer and less ambiguous.

## Volume handling

Use `--volumes` if the user needs volume columns. Use `--volume-units` when the unit matters:

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv --volumes --volume-units units
```
