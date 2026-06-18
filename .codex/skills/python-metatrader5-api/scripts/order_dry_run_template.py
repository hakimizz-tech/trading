#!/usr/bin/env python3
"""Build and validate an MT5 order request. Live send requires --send."""

from __future__ import annotations

import argparse

import MetaTrader5 as mt5


def ensure_symbol(symbol: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol not found: {symbol}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol {symbol}: {mt5.last_error()}")
    return mt5.symbol_info(symbol)


def normalize_volume(volume: float, info) -> float:
    min_vol = getattr(info, "volume_min", volume)
    max_vol = getattr(info, "volume_max", volume)
    step = getattr(info, "volume_step", 0.01) or 0.01
    volume = max(min_vol, min(max_vol, volume))
    steps = round((volume - min_vol) / step)
    return round(min_vol + steps * step, 8)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run an MT5 market order request.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", required=True, choices=["buy", "sell"])
    parser.add_argument("--volume", required=True, type=float)
    parser.add_argument("--sl-points", type=int, default=100)
    parser.add_argument("--tp-points", type=int, default=200)
    parser.add_argument("--deviation", type=int, default=20)
    parser.add_argument("--magic", type=int, default=234000)
    parser.add_argument("--send", action="store_true", help="Actually call order_send after order_check")
    args = parser.parse_args()

    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    try:
        info = ensure_symbol(args.symbol)
        tick = mt5.symbol_info_tick(args.symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {args.symbol}: {mt5.last_error()}")

        point = info.point
        volume = normalize_volume(args.volume, info)
        is_buy = args.side == "buy"
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        price = tick.ask if is_buy else tick.bid
        sl = price - args.sl_points * point if is_buy else price + args.sl_points * point
        tp = price + args.tp_points * point if is_buy else price - args.tp_points * point

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": args.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": args.deviation,
            "magic": args.magic,
            "comment": "python mt5 dry run",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        print("Request:")
        for key, value in request.items():
            print(f"  {key}: {value}")

        check = mt5.order_check(request)
        if check is None:
            raise RuntimeError(f"order_check failed: {mt5.last_error()}")
        print("\nOrder check:")
        print(check)
        if hasattr(check, "_asdict"):
            print(check._asdict())

        if not args.send:
            print("\nDry run only. Re-run with --send only after confirming account, symbol, volume, SL and TP.")
            return 0

        result = mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"order_send failed: {mt5.last_error()}")
        print("\nOrder send result:")
        print(result)
        if hasattr(result, "_asdict"):
            print(result._asdict())
        return 0 if result.retcode == mt5.TRADE_RETCODE_DONE else 2
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
