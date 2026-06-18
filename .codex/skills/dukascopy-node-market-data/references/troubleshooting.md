# Troubleshooting

## `node: command not found`

Install Node.js 12 or newer, then verify:

```bash
node --version
npm --version
```

## `Cannot find module 'dukascopy-node'`

Install it in the current project:

```bash
npm install dukascopy-node --save
```

Or run the CLI through `npx`:

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv
```

## CLI output is huge

Use `--directory` and `--file-name` to write to disk instead of printing everything to terminal:

```bash
npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv --directory ./data --file-name dukascopy_eurusd_m1.csv
```

Use `--inline` only for JSON or array outputs when smaller file size is preferred over readability.

## Tick data file is enormous

This is expected. Tick data is raw price-change data and can be gigabytes over long periods.

Fix:

- Download by day or week.
- Use cache.
- Use low batch size and higher pause.
- Save to disk, do not print to terminal.
- Convert to compressed storage after validation.

## Empty response

Possible causes:

- Instrument is unavailable or incorrectly typed.
- Date range falls on a weekend, holiday, or inactive market period.
- Dukascopy server returned an empty artifact.
- Requested instrument has no data for that period.

Fix:

```bash
--retries 10 --retry-on-empty
```

If an empty result is acceptable in a batch pipeline:

```bash
--no-fail-after-retries
```

## Download fails midway

Use cache and retries so reruns do not start from zero:

```bash
npx dukascopy-node -i eurusd -from 2024-01-01 -to 2024-02-01 -t m1 -f csv --cache --retries 10 --retry-on-empty -bs 5 -bp 2000
```

## Dates appear shifted

By default, timestamps are UTC milliseconds. If the user needs local display, use both `--date-format` and `--time-zone`:

```bash
--date-format "YYYY-MM-DD HH:mm:ss" --time-zone Africa/Nairobi
```

For research pipelines, prefer UTC internally.

## Wrong command name

The current documented command is:

```bash
npx dukascopy-node ...
```

Some examples may mention `dukascopy-cli`. If a command fails, use `npx dukascopy-node` first.
