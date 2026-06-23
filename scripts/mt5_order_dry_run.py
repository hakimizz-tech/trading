#!/usr/bin/env python3
"""Build an MT5 market-order request and validate it with order_check only."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any


def main() -> int:
    args = _parse_args()
    mt5 = _import_mt5()
    initialize_kwargs = {"path": str(args.terminal_path)} if args.terminal_path else {}
    if not mt5.initialize(**initialize_kwargs):
        print(f"initialize: FAIL {mt5.last_error()}")
        return 1

    try:
        info = _ensure_symbol(mt5, args.symbol)
        tick = mt5.symbol_info_tick(args.symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick failed for {args.symbol}: {mt5.last_error()}")

        request = _build_request(mt5, info, tick, args)
        print("request:")
        print(_format_value(request))

        margin = mt5.order_calc_margin(request["type"], args.symbol, args.volume, request["price"])
        print(f"order_calc_margin: {_format_value(margin)} last_error={_format_value(mt5.last_error())}")

        check = mt5.order_check(request)
        if check is None:
            raise RuntimeError(f"order_check failed: {mt5.last_error()}")

        print("order_check:")
        print(_format_value(check))
        retcode = getattr(check, "retcode", None)
        print(f"order_check_retcode: {retcode}")
        return 0
    finally:
        mt5.shutdown()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an MT5 market-order request with order_check only.")
    parser.add_argument("--symbol", required=True, help="Broker symbol, e.g. EURUSDm or XAUUSD.pro")
    parser.add_argument("--side", choices=("buy", "sell"), required=True)
    parser.add_argument("--volume", type=float, required=True, help="Lot size to validate")
    parser.add_argument("--sl-points", type=float, default=0.0, help="Stop-loss distance in points; 0 disables SL")
    parser.add_argument("--tp-points", type=float, default=0.0, help="Take-profit distance in points; 0 disables TP")
    parser.add_argument("--deviation", type=int, default=20)
    parser.add_argument("--magic", type=int, default=260617)
    parser.add_argument("--comment", default="mt5-order-dry-run")
    parser.add_argument("--terminal-path", type=Path, default=None, help="Optional terminal64.exe path")
    return parser.parse_args()


def _import_mt5() -> Any:
    try:
        return importlib.import_module("MetaTrader5")
    except ImportError as exc:  # pragma: no cover - depends on Windows MT5 environment.
        raise RuntimeError(
            "MetaTrader5 is not installed. Run this on Windows with MetaTrader 5 "
            "and install the official MetaTrader5 Python package."
        ) from exc


def _ensure_symbol(mt5: Any, symbol: str) -> Any:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol not found: {symbol}. Broker symbols may use suffixes like EURUSDm or XAUUSD.pro.")
    if not bool(getattr(info, "visible", False)) and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol {symbol}: {mt5.last_error()}")
    return info


def _build_request(mt5: Any, info: Any, tick: Any, args: argparse.Namespace) -> dict[str, Any]:
    is_buy = args.side == "buy"
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    price = float(tick.ask if is_buy else tick.bid)
    point = float(getattr(info, "point", 0.0) or 0.0)
    sl = 0.0
    tp = 0.0
    if point > 0 and args.sl_points > 0:
        sl = price - args.sl_points * point if is_buy else price + args.sl_points * point
    if point > 0 and args.tp_points > 0:
        tp = price + args.tp_points * point if is_buy else price - args.tp_points * point

    filling_mode = getattr(info, "filling_mode", None) or getattr(mt5, "ORDER_FILLING_FOK", 0)
    return {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": args.symbol,
        "volume": args.volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": args.deviation,
        "magic": args.magic,
        "comment": args.comment,
        "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
        "type_filling": filling_mode,
    }


def _format_value(value: Any) -> Any:
    if hasattr(value, "_asdict"):
        return value._asdict()
    return value


if __name__ == "__main__":
    raise SystemExit(main())
