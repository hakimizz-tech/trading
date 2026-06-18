#!/usr/bin/env python3
"""MetaTrader5 connection and symbol health check."""

from __future__ import annotations

import argparse
import os
from typing import Any

import MetaTrader5 as mt5


def dump_namedtuple(label: str, obj: Any) -> None:
    print(f"\n## {label}")
    if obj is None:
        print("None")
        return
    if hasattr(obj, "_asdict"):
        for key, value in obj._asdict().items():
            print(f"{key}: {value}")
    else:
        print(obj)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check MT5 Python connection and symbol visibility.")
    parser.add_argument("--path", default=os.getenv("MT5_PATH"), help="Path to terminal64.exe")
    parser.add_argument("--login", type=int, default=int(os.getenv("MT5_LOGIN", "0")) or None)
    parser.add_argument("--password", default=os.getenv("MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("MT5_SERVER"))
    parser.add_argument("--symbol", default="EURUSD", help="Symbol to inspect")
    args = parser.parse_args()

    kwargs = {k: v for k, v in {
        "path": args.path,
        "login": args.login,
        "password": args.password,
        "server": args.server,
    }.items() if v is not None}

    print("MetaTrader5 package author:", getattr(mt5, "__author__", "unknown"))
    print("MetaTrader5 package version:", getattr(mt5, "__version__", "unknown"))

    if not mt5.initialize(**kwargs):
        print("initialize failed:", mt5.last_error())
        return 1

    try:
        dump_namedtuple("Terminal info", mt5.terminal_info())
        print("\n## Version")
        print(mt5.version())
        dump_namedtuple("Account info", mt5.account_info())

        symbol = args.symbol
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"\nSymbol not found: {symbol}")
            print("Similar symbols:")
            base = ''.join(ch for ch in symbol if ch.isalpha())[:3]
            for candidate in mt5.symbols_get(f"*{base}*") or []:
                print("-", candidate.name)
            return 2

        if not info.visible:
            print(f"\nSymbol {symbol} is not visible. Trying symbol_select...")
            if not mt5.symbol_select(symbol, True):
                print("symbol_select failed:", mt5.last_error())
                return 3

        dump_namedtuple(f"Symbol info: {symbol}", mt5.symbol_info(symbol))
        dump_namedtuple(f"Latest tick: {symbol}", mt5.symbol_info_tick(symbol))
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
