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

    deals, orders = await _collect_history(
        aiomql,
        history_kwargs,
        date_from=date_from,
        date_to=date_to,
        use_account_context=not args.no_account_context,
    )
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
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional aiomql config filename loaded with Config(filename=..., reload=True).",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/history"))
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    parser.add_argument(
        "--no-account-context",
        action="store_true",
        help="Do not wrap the History request in `async with aiomql.Account()`.",
    )
    return parser.parse_args()


def _import_aiomql() -> Any:
    try:
        return importlib.import_module("aiomql")
    except ImportError as exc:  # pragma: no cover - depends on Windows MT5 environment.
        raise RuntimeError("aiomql is not installed. Run this on the Windows/MT5 execution environment.") from exc


def _configure_aiomql(aiomql: Any, config_path: Path | None) -> None:
    if config_path is None:
        return
    aiomql.Config(filename=str(config_path), reload=True)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _collect_history(
    aiomql: Any,
    history_kwargs: dict[str, Any],
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    use_account_context: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect aiomql History rows using the creator's Account/History pattern."""
    if use_account_context and hasattr(aiomql, "Account"):
        async with aiomql.Account():
            return await _history_rows(aiomql.History(**history_kwargs), date_from=date_from, date_to=date_to)
    return await _history_rows(aiomql.History(**history_kwargs), date_from=date_from, date_to=date_to)


async def _history_rows(
    history: Any,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return deals/orders from aiomql History across documented API variants."""
    if hasattr(history, "init") and date_from is not None and date_to is not None:
        await _maybe_await(history.init(date_from, date_to))
    elif hasattr(history, "initialize"):
        await _maybe_await(history.initialize())
    else:
        if hasattr(history, "deals_total"):
            await _maybe_await(history.deals_total())
        if hasattr(history, "orders_total"):
            await _maybe_await(history.orders_total())
    deals = [_to_mapping(item) for item in getattr(history, "deals", [])]
    orders = [_to_mapping(item) for item in getattr(history, "orders", [])]
    return deals, orders


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


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
