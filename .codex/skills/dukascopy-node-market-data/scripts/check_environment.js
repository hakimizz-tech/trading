#!/usr/bin/env node
"use strict";

function versionTuple(version) {
  return version.replace(/^v/, "").split(".").map((part) => Number(part));
}

function isNodeSupported(version) {
  const [major] = versionTuple(version);
  return Number.isFinite(major) && major >= 12;
}

const nodeVersion = process.version;
console.log(`Node.js: ${nodeVersion}`);

if (!isNodeSupported(nodeVersion)) {
  console.error("ERROR: dukascopy-node requires Node.js 12 or newer.");
  process.exitCode = 1;
} else {
  console.log("Node.js version is supported.");
}

try {
  const resolved = require.resolve("dukascopy-node");
  console.log(`dukascopy-node module found: ${resolved}`);
} catch (error) {
  console.warn("dukascopy-node module not found in this project.");
  console.warn("Install with: npm install dukascopy-node --save");
  console.warn("For one-off CLI usage, try: npx dukascopy-node -i eurusd -from 2024-02-13 -to 2024-02-15 -t m1 -f csv");
}
