---
name: python-metatrader5-api
description: Expert workflow for using the official MetaTrader5 Python package to connect to MT5, fetch bars and ticks, inspect account/symbol data, calculate margin/profit, check orders, and build safe trading scripts. Use when the user mentions MetaTrader5, MT5 Python, MQL5 Python integration, copy_rates, copy_ticks, symbol_info, order_send, order_check, trading bot, forex data, or broker terminal automation.
license: MIT
compatibility: Requires Python, the MetaTrader 5 terminal, and the MetaTrader5 package. Live trading requires a logged-in MT5 account and explicit user approval.
metadata:
  author: Hakeem Keem
  version: 1.0.0
  category: trading-automation
  tags:
    - metatrader5
    - mt5
    - python
    - forex
    - algorithmic-trading
---

# Python MetaTrader5 API Skill

## Purpose

Use this skill to help users write, debug, and structure Python scripts that integrate with the official `MetaTrader5` package. The skill should produce robust code for connection management, market data retrieval, symbol/account inspection, order checking, and order request construction.

## Critical safety rules

1. Default to read-only workflows: account inspection, symbol lookup, historical bars, ticks, positions, orders, and dry-run request validation.
2. Do not send a live order unless the user explicitly asks to execute a trade and provides or confirms symbol, side, lot size, stop loss, take profit, account/server context, and that the target account may trade live.
3. For any trade workflow, call or generate code that calls `order_check()` before `order_send()`.
4. Always include failure handling using `mt5.last_error()` and inspect returned `retcode` values after trade requests.
5. Always close the terminal connection with `mt5.shutdown()` in a `finally` block or context manager pattern.
6. Never place credentials directly into published code. Use environment variables, an `.env` file excluded from git, or terminal-saved credentials.
7. Make users aware that broker symbols may differ, for example `EURUSD`, `EURUSDm`, `XAUUSD`, or `XAUUSD.pro`.

## Standard workflow

### Step 1: Identify the user's task type

Classify the request into one of these workflows:

- Environment setup: installation, terminal connection, Windows path, package import problems.
- Account and terminal diagnostics: `initialize`, `login`, `version`, `terminal_info`, `account_info`, `last_error`.
- Symbol discovery and market data: `symbols_get`, `symbol_info`, `symbol_info_tick`, `symbol_select`, market book functions.
- Historical data extraction: `copy_rates_from`, `copy_rates_from_pos`, `copy_rates_range`, `copy_ticks_from`, `copy_ticks_range`.
- Order and position inspection: `orders_total`, `orders_get`, `positions_total`, `positions_get`, history orders/deals.
- Trade planning and validation: `order_calc_margin`, `order_calc_profit`, `order_check`.
- Trade execution: `order_send`, only after explicit user confirmation.

### Step 2: Load focused references only when needed

Use these bundled references for deeper detail:

- `references/api-quick-reference.md` for function categories and common patterns.
- `references/connection-patterns.md` for initialization, login, shutdown, and diagnostics.
- `references/data-retrieval-patterns.md` for bars, ticks, pandas conversion, and UTC handling.
- `references/order-workflows.md` for safe order request design, dry runs, and `order_check` before `order_send`.
- `references/troubleshooting.md` for common MT5 Python errors and fixes.

### Step 3: Generate code with safe defaults

When producing Python code:

- Use `import MetaTrader5 as mt5`.
- Use `from datetime import datetime, timezone` for date ranges.
- Use UTC-aware datetimes for functions that request time ranges.
- Convert arrays to pandas DataFrames when the user wants analysis, CSV export, charts, or ML-ready data.
- Check for `None` and empty returns separately.
- Print `mt5.last_error()` when a call fails.
- Select symbols into MarketWatch with `mt5.symbol_select(symbol, True)` when needed.
- Never assume filling mode. Prefer using symbol info to determine valid filling type or instruct the user to test with their broker.

### Step 4: Validate outputs

Before finalizing scripts, check that the code:

- Initializes MT5 and shuts it down reliably.
- Handles missing symbols and invisible symbols.
- Handles no data returned due to terminal chart history limits.
- Uses UTC time for bars and ticks.
- Does not expose account password or server secrets.
- Uses dry-run mode unless user explicitly requested live execution.

## Example prompts this skill should handle

### Example 1: Fetch historical rates

User says: `write python code to get XAUUSD H1 candles from MT5 and save to CSV`

Actions:

1. Create a UTC date range.
2. Initialize MT5.
3. Select the symbol.
4. Call `copy_rates_range(symbol, mt5.TIMEFRAME_H1, utc_from, utc_to)`.
5. Convert to DataFrame.
6. Convert `time` from seconds to datetime.
7. Save to CSV.
8. Shutdown in `finally`.

### Example 2: Debug MT5 connection

User says: `mt5.initialize failed`

Actions:

1. Ask only for the missing detail if necessary: OS, terminal path, whether MT5 is installed and logged in.
2. Provide a health-check script using `mt5.initialize()`, `mt5.last_error()`, `mt5.terminal_info()`, and `mt5.version()`.
3. Suggest checking terminal path, account login, broker server name, and package installation.

### Example 3: Prepare an order request safely

User says: `create a buy order script for EURUSD`

Actions:

1. Create a dry-run script first.
2. Fetch `symbol_info` and latest tick.
3. Calculate price, SL, TP using `point`.
4. Build a request dictionary.
5. Run `order_check(request)`.
6. Print all result fields.
7. Keep `order_send()` disabled unless the user explicitly confirms live execution.

## Useful scripts bundled with this skill

- `scripts/mt5_health_check.py`: diagnoses connection, terminal, account, and symbol visibility.
- `scripts/fetch_rates_to_csv.py`: exports bars to CSV using UTC date ranges.
- `scripts/order_dry_run_template.py`: builds a request and runs `order_check`; live sending requires `--send`.

## Response style

- Be direct and practical.
- Give runnable code first when the user asks for code.
- Explain broker-dependent values, especially symbol names, filling modes, stop levels, and account permissions.
- For risky trading actions, slow down and require explicit confirmation.
