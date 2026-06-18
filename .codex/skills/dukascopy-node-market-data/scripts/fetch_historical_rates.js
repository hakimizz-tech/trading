#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { getHistoricalRates } = require("dukascopy-node");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function toBool(value) {
  if (value === true) return true;
  if (value === undefined || value === false) return false;
  return ["1", "true", "yes", "y"].includes(String(value).toLowerCase());
}

function toNumber(value, fallback) {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function requireArg(args, key) {
  if (!args[key]) {
    throw new Error(`Missing required argument --${key}`);
  }
  return args[key];
}

function normalizeFormat(format) {
  const value = format || "json";
  if (!["csv", "json", "array"].includes(value)) {
    throw new Error("--format must be one of: csv, json, array");
  }
  return value;
}

async function main() {
  const args = parseArgs(process.argv);

  const instrument = requireArg(args, "instrument").toLowerCase();
  const from = requireArg(args, "from");
  const to = requireArg(args, "to");
  const timeframe = args.timeframe || "d1";
  const format = normalizeFormat(args.format);
  const output = args.output;

  const config = {
    instrument,
    dates: {
      from: new Date(from),
      to: to === "now" ? new Date() : new Date(to),
    },
    timeframe,
    format,
  };

  if (args["price-type"]) config.priceType = args["price-type"];
  if (args.volumes !== undefined) config.volumes = toBool(args.volumes);
  if (args.cache !== undefined) config.useCache = toBool(args.cache);
  if (args["cache-path"]) config.cacheFolderPath = args["cache-path"];
  if (args["batch-size"]) config.batchSize = toNumber(args["batch-size"], 10);
  if (args["batch-pause"]) config.pauseBetweenBatchesMs = toNumber(args["batch-pause"], 1000);
  if (args.retries) config.retryCount = toNumber(args.retries, 0);
  if (args["retry-on-empty"] !== undefined) config.retryOnEmpty = toBool(args["retry-on-empty"]);
  if (args["no-fail-after-retries"] !== undefined) config.failAfterRetryCount = false;
  if (args["retry-pause"]) config.pauseBetweenRetriesMs = toNumber(args["retry-pause"], 500);
  if (args.debug !== undefined) config.debug = toBool(args.debug);
  if (args["date-format"]) config.dateFormat = args["date-format"];
  if (args["time-zone"]) config.timeZone = args["time-zone"];

  if (timeframe === "tick") {
    console.warn("WARNING: tick data is raw bid/ask data and can be very large for long ranges.");
  }

  const data = await getHistoricalRates(config);

  if (output) {
    fs.mkdirSync(path.dirname(output), { recursive: true });
    const payload = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    fs.writeFileSync(output, payload, "utf8");
    console.log(`Wrote ${output}`);
    return;
  }

  if (typeof data === "string") {
    console.log(data);
  } else {
    console.log(JSON.stringify(data, null, 2));
  }
}

main().catch((error) => {
  console.error("error", error.message || error);
  process.exit(1);
});
