# Safe Order Workflows

## Default stance

Generate dry-run and validation scripts unless the user explicitly asks for live execution. A dry-run script builds a request and calls `order_check()` but does not call `order_send()`.

## Basic market buy request

```python
symbol = "EURUSD"
lot = 0.10
info = mt5.symbol_info(symbol)
tick = mt5.symbol_info_tick(symbol)

point = info.point
price = tick.ask
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": lot,
    "type": mt5.ORDER_TYPE_BUY,
    "price": price,
    "sl": price - 100 * point,
    "tp": price + 200 * point,
    "deviation": 20,
    "magic": 234000,
    "comment": "python mt5 dry run",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_RETURN,
}
```

## Pre-trade checks

Before `order_check()`:

- `symbol_info` is not `None`.
- Symbol is visible or selected into MarketWatch.
- Tick is not `None`.
- Lot size respects broker min, max, and volume step.
- Stop loss and take profit respect broker stop levels.
- Account trade mode permits trading.
- Market is open.

## Validate request

```python
check = mt5.order_check(request)
if check is None:
    raise RuntimeError(f"order_check failed: {mt5.last_error()}")
print(check)
```

## Live execution gate

Only after explicit user confirmation:

```python
result = mt5.order_send(request)
if result is None:
    raise RuntimeError(f"order_send failed: {mt5.last_error()}")
print(result)
if result.retcode != mt5.TRADE_RETCODE_DONE:
    print("Trade not completed. retcode:", result.retcode)
    print(result._asdict())
```

## Closing a position

To close a position, use the opposite order type and include the `position` ticket. For a long position, send a sell request. For a short position, send a buy request.

## Risk notes

- Never calculate lot size from account balance without a defined risk percentage and stop-loss distance.
- Never omit stop loss in production examples unless the user is intentionally testing a broker-specific order type.
- Demonstrate on demo accounts first.
