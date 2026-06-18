# MetaTrader5 Python API Quick Reference

## Install and import

```bash
pip install MetaTrader5
pip install --upgrade MetaTrader5
```

```python
import MetaTrader5 as mt5
```

## Function map

### Connection and diagnostics

- `initialize()` connects Python to the MetaTrader 5 terminal.
- `login()` connects to a trading account using supplied credentials.
- `shutdown()` closes the connection.
- `version()` returns terminal version details.
- `last_error()` returns the latest integration error.
- `terminal_info()` returns connected terminal status and parameters.
- `account_info()` returns current trading account details.

### Symbols and market state

- `symbols_total()` returns the number of symbols.
- `symbols_get()` returns all symbols.
- `symbol_info(symbol)` returns instrument metadata.
- `symbol_info_tick(symbol)` returns the latest tick.
- `symbol_select(symbol, True)` adds a symbol to MarketWatch.
- `market_book_add`, `market_book_get`, and `market_book_release` manage market depth subscriptions.

### Historical data

- `copy_rates_from(symbol, timeframe, date_from, count)` returns bars starting from a date.
- `copy_rates_from_pos(symbol, timeframe, start_pos, count)` returns bars from a zero-based index.
- `copy_rates_range(symbol, timeframe, date_from, date_to)` returns bars in a date range.
- `copy_ticks_from(symbol, date_from, count, flags)` returns ticks starting from a date.
- `copy_ticks_range(symbol, date_from, date_to, flags)` returns ticks in a date range.

### Orders, positions, history

- `orders_total()` and `orders_get()` inspect active orders.
- `positions_total()` and `positions_get()` inspect open positions.
- `history_orders_total()` and `history_orders_get()` inspect historical orders.
- `history_deals_total()` and `history_deals_get()` inspect historical deals.

### Trading calculations and execution

- `order_calc_margin()` estimates required margin.
- `order_calc_profit()` estimates profit or loss.
- `order_check(request)` validates a trade request before sending.
- `order_send(request)` sends a trade request to the terminal and broker trade server.

## Core coding rules

1. Use UTC-aware datetimes for historical data calls.
2. Always check for `None` returns and print `mt5.last_error()`.
3. Use `symbol_select(symbol, True)` before data retrieval if the symbol is not visible.
4. Use `try` and `finally` so `mt5.shutdown()` always runs.
5. Keep live trading disabled by default.
