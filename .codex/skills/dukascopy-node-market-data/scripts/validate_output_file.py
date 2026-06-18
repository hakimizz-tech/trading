#!/usr/bin/env python3
"""Basic validation for Dukascopy CSV or JSON outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

OHLC_COLUMNS = {"timestamp", "open", "high", "low", "close"}
TICK_COLUMNS = {"timestamp", "askPrice", "bidPrice"}


def load_columns(path: Path) -> tuple[set[str], int]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            rows = sum(1 for _ in reader)
            return columns, rows

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return set(data[0].keys()), len(data)
        if isinstance(data, list):
            return {"array_format"}, len(data)
        raise ValueError("JSON output is not a list")

    raise ValueError("Only .csv and .json files are supported by this validator")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Dukascopy output file shape.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--kind", choices=["ohlc", "tick", "auto"], default="auto")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"ERROR: file does not exist: {path}")
    if path.stat().st_size == 0:
        raise SystemExit(f"ERROR: file is empty: {path}")

    columns, rows = load_columns(path)
    if rows == 0:
        raise SystemExit("ERROR: file has zero data rows")

    if args.kind == "ohlc":
        missing = OHLC_COLUMNS - columns
        if missing:
            raise SystemExit(f"ERROR: missing OHLC columns: {sorted(missing)}")
    elif args.kind == "tick":
        missing = TICK_COLUMNS - columns
        if missing:
            raise SystemExit(f"ERROR: missing tick columns: {sorted(missing)}")
    elif "array_format" not in columns:
        if OHLC_COLUMNS <= columns:
            print("Detected OHLC output.")
        elif TICK_COLUMNS <= columns:
            print("Detected tick output.")
        else:
            raise SystemExit(f"ERROR: unrecognized columns: {sorted(columns)}")

    print(f"OK: {path} contains {rows} rows with columns: {', '.join(sorted(columns))}")


if __name__ == "__main__":
    main()
