#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { getRealTimeRates } = require("dukascopy-node");

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
  if (!args[key]) throw new Error(`Missing required argument --${key}`);
  return args[key];
}

async function main() {
  const args = parseArgs(process.argv);

  const config = {
    instrument: requireArg(args, "instrument").toLowerCase(),
    timeframe: args.timeframe || "tick",
    format: args.format || "json",
  };

  if (args["price-type"]) config.priceType = args["price-type"];
  if (args.volumes !== undefined) config.volumes = toBool(args.volumes);

  if (args.from) {
    config.dates = {
      from: args.from,
      to: args.to || undefined,
    };
  } else {
    config.last = toNumber(args.last, 10);
  }

  const data = await getRealTimeRates(config);

  if (args.output) {
    fs.mkdirSync(path.dirname(args.output), { recursive: true });
    const payload = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    fs.writeFileSync(args.output, payload, "utf8");
    console.log(`Wrote ${args.output}`);
    return;
  }

  if (typeof data === "string") console.log(data);
  else console.log(JSON.stringify(data, null, 2));
}

main().catch((error) => {
  console.error("error", error.message || error);
  process.exit(1);
});
