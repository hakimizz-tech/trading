#!/usr/bin/env python3
"""Export aiomql account history for broker-side reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


async def export_history(args: argparse.Namespace) -> int:
    aiomql = _import_aiomql()
    _configure_aiomql(aiomql, args.config)

    date_to = _parse_datetime(args.to) if args.to else datetime.now(tz=timezone.utc)
    date_from = _parse_datetime(args.from_) if args.from_ else date_to - timedelta(days=args.days)
    history_kwargs = {"date_from": date_from, "date_to": date_to}
    if args.group:
        history_kwargs["group"] = args.group

    history = aiomql.History(**history_kwargs)
    await history.initialize()

    deals = [_to_mapping(item) for item in getattr(history, "deals", [])]
    orders = [_to_mapping(item) for item in getattr(history, "orders", [])]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.format == "json":
        _write_json(args.output_dir / "aiomql_history_deals.json", deals)
        _write_json(args.output_dir / "aiomql_history_orders.json", orders)
    else:
        _write_csv(args.output_dir / "aiomql_history_deals.csv", deals)
        _write_csv(args.output_dir / "aiomql_history_orders.csv", orders)

    print(f"Exported {len(deals)} deals and {len(orders)} orders to {args.output_dir}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export aiomql History deals/orders for reconciliation.")
    parser.add_argument("--days", type=int, default=7, help="Lookback days when --from is omitted")
    parser.add_argument("--from", dest="from_", default=None, help="UTC ISO datetime, e.g. 2026-06-01T00:00:00Z")
    parser.add_argument("--to", default=None, help="UTC ISO datetime; defaults to now")
    parser.add_argument("--group", default=None, help="Optional MT5 history group filter, e.g. *USD*")
    parser.add_argument("--config", type=Path, default=None, help="Optional JSON passed to aiomql.Config")
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/history"))
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    return parser.parse_args()


def _import_aiomql() -> Any:
    try:
        return importlib.import_module("aiomql")
    except ImportError as exc:  # pragma: no cover - depends on Windows MT5 environment.
        raise RuntimeError("aiomql is not installed. Run this on the Windows/MT5 execution environment.") from exc


def _configure_aiomql(aiomql: Any, config_path: Path | None) -> None:
    if config_path is None:
        return
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Config JSON must be an object")
    aiomql.Config(**config)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if isinstance(value, dict):
        return dict(value)
    return dict(getattr(value, "__dict__", {"value": str(value)}))


def _write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as file:
        if not fieldnames:
            file.write("")
            return
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    return asyncio.run(export_history(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
