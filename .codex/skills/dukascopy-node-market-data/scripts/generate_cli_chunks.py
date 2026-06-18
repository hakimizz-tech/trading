#!/usr/bin/env python3
"""Generate day/week chunked dukascopy-node CLI commands."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate chunked dukascopy-node CLI commands.")
    parser.add_argument("--instrument", required=True, help="Dukascopy instrument id, e.g. eurusd")
    parser.add_argument("--from", dest="date_from", required=True, help="Start date yyyy-mm-dd")
    parser.add_argument("--to", dest="date_to", required=True, help="End date yyyy-mm-dd, exclusive-style for chunks")
    parser.add_argument("--timeframe", default="tick", help="tick, m1, h1, d1, etc.")
    parser.add_argument("--format", default="csv", choices=["csv", "json", "array"])
    parser.add_argument("--chunk-days", type=int, default=1, help="Days per command")
    parser.add_argument("--price-type", default=None, choices=["bid", "ask"])
    parser.add_argument("--directory", default="./download")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--batch-pause", type=int, default=None)
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--cache-path", default=None)
    parser.add_argument("--retries", type=int, default=None)
    parser.add_argument("--retry-on-empty", action="store_true")
    parser.add_argument("--no-fail-after-retries", action="store_true")
    parser.add_argument("--date-format", default=None)
    parser.add_argument("--time-zone", default=None)
    args = parser.parse_args()

    if args.chunk_days < 1:
        raise SystemExit("--chunk-days must be at least 1")

    current = parse_date(args.date_from)
    end = parse_date(args.date_to)
    instrument = args.instrument.lower()

    while current < end:
        nxt = min(current + timedelta(days=args.chunk_days), end)
        start_s = current.strftime("%Y-%m-%d")
        end_s = nxt.strftime("%Y-%m-%d")
        suffix = args.format
        file_name = f"dukascopy_{instrument}_{args.timeframe}_{start_s}_{end_s}.{suffix}"
        output_dir = Path(args.directory).as_posix()

        parts = [
            "npx dukascopy-node",
            f"-i {instrument}",
            f"-from {start_s}",
            f"-to {end_s}",
            f"-t {args.timeframe}",
            f"-f {args.format}",
            f"--directory {output_dir}",
            f"--file-name {file_name}",
        ]

        if args.price_type:
            parts.append(f"--price-type {args.price_type}")
        if args.batch_size is not None:
            parts.append(f"--batch-size {args.batch_size}")
        if args.batch_pause is not None:
            parts.append(f"--batch-pause {args.batch_pause}")
        if args.cache:
            parts.append("--cache")
        if args.cache_path:
            parts.append(f"--cache-path {args.cache_path}")
        if args.retries is not None:
            parts.append(f"--retries {args.retries}")
        if args.retry_on_empty:
            parts.append("--retry-on-empty")
        if args.no_fail_after_retries:
            parts.append("--no-fail-after-retries")
        if args.date_format:
            parts.append(f"--date-format '{args.date_format}'")
        if args.time_zone:
            parts.append(f"--time-zone {args.time_zone}")

        print(" ".join(parts))
        current = nxt


if __name__ == "__main__":
    main()
