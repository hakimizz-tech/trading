#!/usr/bin/env python3
"""Read-only MetaTrader 5 terminal and symbol health check."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any


def main() -> int:
    args = _parse_args()
    mt5 = _import_mt5()
    symbols = list(args.symbols)
    if args.settings is not None:
        symbols.extend(_symbols_from_settings(args.settings))
    symbols = sorted(set(symbols))

    initialize_kwargs = {"path": str(args.terminal_path)} if args.terminal_path else {}
    if not mt5.initialize(**initialize_kwargs):
        print(f"initialize: FAIL {mt5.last_error()}")
        return 1

    try:
        print(f"initialize: OK")
        print(f"version: {_format_value(mt5.version())}")
        print(f"terminal_info: {_format_value(mt5.terminal_info())}")
        print(f"account_info: {_format_value(mt5.account_info())}")
        print(f"last_error: {_format_value(mt5.last_error())}")

        for symbol in symbols:
            _print_symbol_status(mt5, symbol)
        return 0
    finally:
        mt5.shutdown()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only MT5 terminal/account/symbol diagnostics.")
    parser.add_argument("--terminal-path", type=Path, default=None, help="Optional terminal64.exe path")
    parser.add_argument("--settings", type=Path, default=None, help="Optional bot settings JSON to read symbols from")
    parser.add_argument("--symbols", nargs="*", default=(), help="Broker symbols, e.g. EURUSD EURUSDm XAUUSD.pro")
    return parser.parse_args()


def _import_mt5() -> Any:
    try:
        return importlib.import_module("MetaTrader5")
    except ImportError as exc:  # pragma: no cover - depends on Windows MT5 environment.
        raise RuntimeError(
            "MetaTrader5 is not installed. Run this on Windows with MetaTrader 5 "
            "and install the official MetaTrader5 Python package."
        ) from exc


def _symbols_from_settings(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Bot settings must be a JSON object")

    symbols = [str(item).strip() for item in raw.get("symbols", []) if str(item).strip()]
    for spec in raw.get("strategies", []):
        if isinstance(spec, dict):
            symbols.extend(str(item).strip() for item in spec.get("symbols", []) if str(item).strip())
    return symbols


def _print_symbol_status(mt5: Any, symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"symbol {symbol}: NOT FOUND last_error={_format_value(mt5.last_error())}")
        return

    selected = bool(getattr(info, "visible", False)) or bool(mt5.symbol_select(symbol, True))
    tick = mt5.symbol_info_tick(symbol) if selected else None
    print(f"symbol {symbol}: {'OK' if selected else 'NOT SELECTABLE'}")
    print(f"  info: {_format_value(info)}")
    print(f"  tick: {_format_value(tick)}")
    if not selected:
        print(f"  last_error: {_format_value(mt5.last_error())}")


def _format_value(value: Any) -> Any:
    if hasattr(value, "_asdict"):
        return value._asdict()
    return value


if __name__ == "__main__":
    raise SystemExit(main())
