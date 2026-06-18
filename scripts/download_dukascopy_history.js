#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const SUPPORTED_TIMEFRAMES = new Set(["tick", "s1", "m1", "m5", "m15", "m30", "h1", "h4", "d1", "mn1"]);
const SUPPORTED_FORMATS = new Set(["csv", "json"]);
const PRESETS = {
  "major-fx": ["eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad", "nzdusd"],
  "rising-fx": ["eurusd", "gbpusd", "xauusd"],
};

function parseArgs(argv) {
  const args = { instruments: [] };
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith("--")) {
      args[key] = true;
    } else {
      if (key === "instrument" || key === "instruments") {
        args.instruments.push(...splitList(next));
      } else {
        args[key] = next;
      }
      i += 1;
    }
  }
  return args;
}

function splitList(value) {
  return String(value)
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function printHelp() {
  console.log(`Download Dukascopy historical forex/market data into datasets/.

Usage:
  node scripts/download_dukascopy_history.js --instrument eurusd --from 2024-01-01 --to 2024-02-01 --timeframe h1
  node scripts/download_dukascopy_history.js --preset major-fx --from 2024-01-01 --to 2024-02-01 --timeframe d1

Options:
  --instrument, --instruments  Instrument id(s), comma-separated or repeated. Example: eurusd,gbpusd,xauusd
  --preset                    Preset universe: ${Object.keys(PRESETS).join(", ")}
  --from                      Start date yyyy-mm-dd. Default: 2024-01-01
  --to                        End date yyyy-mm-dd or now. Default: now
  --timeframe                 tick, s1, m1, m5, m15, m30, h1, h4, d1, mn1. Default: h1
  --price-type                bid or ask. Default: bid
  --format                    csv or json. Default: csv
  --output-dir                Destination root. Default: datasets
  --raw-dir                   Raw Dukascopy output root. Default: datasets/_raw_dukascopy
  --manifest                  Manifest path. Default: datasets/dukascopy_manifest.json
  --cache-path                Cache directory. Default: datasets/.dukascopy-cache
  --batch-size                Dukascopy batch size. Default: 5 for candles, 1 for tick
  --batch-pause               Pause between batches in ms. Default: 2000 for candles, 3000 for tick
  --retries                   Retry count. Default: 10 for candles, 15 for tick
  --retry-pause               Pause between retries in ms. Default: 750
  --no-cache                  Disable dukascopy-node cache
  --no-install                Do not install dukascopy-node if missing
  --allow-long-tick           Allow tick data longer than 7 days
  --help                      Show this help

Output:
  Candle CSV: datasets/<SYMBOL>/<SYMBOL>_<timeframe>_dukascopy_<priceType>_<from>_<to>.csv
  Raw JSON:    datasets/_raw_dukascopy/<SYMBOL>/...
`);
}

function toBool(value, fallback) {
  if (value === undefined) return fallback;
  if (value === true) return true;
  return ["1", "true", "yes", "y"].includes(String(value).toLowerCase());
}

function toNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeDate(value, fallback) {
  const raw = value || fallback;
  if (raw === "now") return raw;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    throw new Error(`Date must use yyyy-mm-dd or now: ${raw}`);
  }
  return raw;
}

function resolveInstruments(args) {
  const instruments = [...args.instruments];
  if (args.preset) {
    const preset = PRESETS[String(args.preset).toLowerCase()];
    if (!preset) {
      throw new Error(`Unknown --preset ${args.preset}. Expected one of: ${Object.keys(PRESETS).join(", ")}`);
    }
    instruments.push(...preset);
  }
  if (instruments.length === 0) instruments.push("eurusd");
  return [...new Set(instruments.map((item) => item.toLowerCase()))];
}

function resolveDukascopyNode({ installIfMissing }) {
  try {
    return require("dukascopy-node");
  } catch (error) {
    if (!installIfMissing) {
      throw new Error("dukascopy-node is not installed. Run: npm install dukascopy-node --save");
    }
  }

  console.log("dukascopy-node is not installed. Installing locally with npm...");
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  const install = spawnSync(npm, ["install", "dukascopy-node", "--save"], {
    cwd: process.cwd(),
    stdio: "inherit",
  });
  if (install.status !== 0) {
    throw new Error("npm install dukascopy-node --save failed");
  }
  return require("dukascopy-node");
}

function ensureNodeVersion() {
  const major = Number(process.version.replace(/^v/, "").split(".")[0]);
  if (!Number.isFinite(major) || major < 12) {
    throw new Error(`dukascopy-node requires Node.js 12 or newer. Current: ${process.version}`);
  }
}

function daysBetween(from, to) {
  if (to === "now") return Number.POSITIVE_INFINITY;
  return Math.ceil((new Date(`${to}T00:00:00Z`) - new Date(`${from}T00:00:00Z`)) / 86_400_000);
}

function validateRequest({ from, to, timeframe, format, allowLongTick }) {
  if (!SUPPORTED_TIMEFRAMES.has(timeframe)) {
    throw new Error(`Unsupported timeframe: ${timeframe}`);
  }
  if (!SUPPORTED_FORMATS.has(format)) {
    throw new Error(`Unsupported output format: ${format}`);
  }
  if (timeframe === "tick" && !allowLongTick && daysBetween(from, to) > 7) {
    throw new Error("Tick data can be very large. Use <= 7 days or pass --allow-long-tick.");
  }
}

function outputStem({ instrument, timeframe, priceType, from, to }) {
  return `${instrument.toUpperCase()}_${timeframe}_dukascopy_${priceType}_${from}_${to}`;
}

function rawOutputPath({ rawDir, instrument, stem }) {
  return path.join(rawDir, instrument.toUpperCase(), `${stem}_raw.json`);
}

function normalizedOutputPath({ outputDir, instrument, stem, format }) {
  return path.join(outputDir, instrument.toUpperCase(), `${stem}.${format}`);
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), "utf8");
}

function writeText(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, payload, "utf8");
}

function csvEscape(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function candleRowsToCsv(rows) {
  const header = ["timestamp", "open", "high", "low", "close", "volume"];
  const lines = [header.join(",")];
  for (const row of rows) {
    lines.push(
      [
        new Date(row.timestamp).toISOString(),
        row.open,
        row.high,
        row.low,
        row.close,
        row.volume ?? 0,
      ].map(csvEscape).join(",")
    );
  }
  return `${lines.join("\n")}\n`;
}

function tickRowsToCsv(rows) {
  const header = ["timestamp", "askPrice", "bidPrice", "askVolume", "bidVolume"];
  const lines = [header.join(",")];
  for (const row of rows) {
    lines.push(
      [
        new Date(row.timestamp).toISOString(),
        row.askPrice,
        row.bidPrice,
        row.askVolume,
        row.bidVolume,
      ].map(csvEscape).join(",")
    );
  }
  return `${lines.join("\n")}\n`;
}

function normalizeRows(data) {
  if (typeof data === "string") {
    throw new Error("Internal downloader expected JSON rows, got string");
  }
  if (!Array.isArray(data)) {
    throw new Error("dukascopy-node returned a non-array response");
  }
  return data;
}

async function fetchInstrument({ getHistoricalRates, instrument, request }) {
  const config = {
    instrument,
    dates: {
      from: new Date(`${request.from}T00:00:00Z`),
      to: request.to === "now" ? new Date() : new Date(`${request.to}T00:00:00Z`),
    },
    timeframe: request.timeframe,
    format: "json",
    priceType: request.priceType,
    volumes: request.timeframe !== "tick",
    useCache: request.useCache,
    cacheFolderPath: request.cachePath,
    batchSize: request.batchSize,
    pauseBetweenBatchesMs: request.batchPause,
    retryCount: request.retries,
    retryOnEmpty: true,
    failAfterRetryCount: true,
    pauseBetweenRetriesMs: request.retryPause,
  };
  return normalizeRows(await getHistoricalRates(config));
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    printHelp();
    return;
  }

  ensureNodeVersion();

  const instruments = resolveInstruments(args);
  const timeframe = String(args.timeframe || "h1").toLowerCase();
  const priceType = String(args["price-type"] || "bid").toLowerCase();
  const format = String(args.format || "csv").toLowerCase();
  const from = normalizeDate(args.from, "2024-01-01");
  const to = normalizeDate(args.to, "now");
  const tickMode = timeframe === "tick";
  const request = {
    from,
    to,
    timeframe,
    priceType,
    format,
    useCache: !toBool(args["no-cache"], false),
    cachePath: args["cache-path"] || path.join("datasets", ".dukascopy-cache"),
    batchSize: toNumber(args["batch-size"], tickMode ? 1 : 5),
    batchPause: toNumber(args["batch-pause"], tickMode ? 3000 : 2000),
    retries: toNumber(args.retries, tickMode ? 15 : 10),
    retryPause: toNumber(args["retry-pause"], 750),
  };
  validateRequest({
    from,
    to,
    timeframe,
    format,
    allowLongTick: toBool(args["allow-long-tick"], false),
  });

  const installIfMissing = !toBool(args["no-install"], false);
  const { getHistoricalRates } = resolveDukascopyNode({ installIfMissing });
  const outputDir = args["output-dir"] || "datasets";
  const rawDir = args["raw-dir"] || path.join("datasets", "_raw_dukascopy");
  const manifestPath = args.manifest || path.join("datasets", "dukascopy_manifest.json");
  const manifest = {
    collector: "dukascopy-node",
    generatedAt: new Date().toISOString(),
    request,
    instruments,
    outputs: {},
    metadata: {
      timestamp_note: "Dukascopy timestamps are treated as UTC. Candle CSV timestamps are ISO UTC.",
      tick_warning: "Tick data is raw bid/ask data and can be very large.",
      source_note: "Dukascopy data availability depends on instrument, date range, market sessions, and server responses.",
    },
  };

  for (const instrument of instruments) {
    const stem = outputStem({ instrument, timeframe, priceType, from, to });
    const rawPath = rawOutputPath({ rawDir, instrument, stem });
    const normalizedPath = normalizedOutputPath({ outputDir, instrument, stem, format });
    console.log(`Fetching ${instrument} ${timeframe} ${from} -> ${to}`);
    try {
      const rows = await fetchInstrument({ getHistoricalRates, instrument, request });
      if (rows.length === 0) {
        throw new Error("Dukascopy returned zero rows");
      }
      writeJson(rawPath, rows);
      if (format === "json") {
        writeJson(normalizedPath, rows);
      } else if (timeframe === "tick") {
        writeText(normalizedPath, tickRowsToCsv(rows));
      } else {
        writeText(normalizedPath, candleRowsToCsv(rows));
      }
      manifest.outputs[instrument.toUpperCase()] = {
        status: "ok",
        rows: rows.length,
        normalizedPath,
        rawPath,
        source: "dukascopy-node:getHistoricalRates",
      };
      console.log(`Wrote ${normalizedPath} (${rows.length} rows)`);
    } catch (error) {
      manifest.outputs[instrument.toUpperCase()] = {
        status: "error",
        rows: 0,
        normalizedPath,
        rawPath,
        error: error.message || String(error),
        source: "missing",
      };
      console.error(`Failed ${instrument}: ${error.message || error}`);
    }
    writeJson(manifestPath, manifest);
  }

  const okCount = Object.values(manifest.outputs).filter((item) => item.status === "ok").length;
  console.log(`Completed ${okCount}/${instruments.length} instruments`);
  console.log(`Manifest: ${manifestPath}`);
  if (okCount !== instruments.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error("error", error.message || error);
  process.exit(1);
});
