# aiomql API Map

This reference summarizes the aiomql concepts a coding agent should prefer when helping with projects that use `aiomql`.

## Environment and installation

- Package: `aiomql`
- Install: `python -m pip install aiomql`
- Optional extras:
  - `python -m pip install "aiomql[talib]"`
  - `python -m pip install "aiomql[optional]"`
  - `python -m pip install "aiomql[all]"`
- Live MetaTrader 5 execution requires Windows, MetaTrader 5 terminal, a broker account, and Python 3.13 or newer.

## Configuration

Use one of these approaches:

```python
from aiomql import Config

config = Config(login=12345678, password="local_secret", server="Broker-Demo")
```

or a project-local `aiomql.json` file:

```json
{
  "login": 12345678,
  "password": "your_password",
  "server": "YourBroker-Demo"
}
```

For generated projects, create `aiomql.json.example` and add `aiomql.json` to `.gitignore`.

## Low-level interface

Use `MetaTrader` for direct async access to MT5 functions:

```python
import asyncio
from aiomql import MetaTrader

async def main():
    async with MetaTrader() as mt5:
        account = await mt5.account_info()
        symbols = await mt5.symbols_get()
        print(account, len(symbols))

asyncio.run(main())
```

Use this path when the user asks for account info, symbol lists, terminal info, direct market data, or direct order experimentation.

## Core abstractions

- `Bot`: orchestrates strategies and coroutines.
- `Strategy`: base class for trading logic. Implement `trade()`.
- `ForexSymbol`: specialized symbol wrapper for forex pip and volume calculations.
- `TimeFrame`: timeframe enum such as M1, M5, M15, H1.
- `OrderType`: order direction enum such as BUY or SELL.
- `Trader`, `SimpleTrader`, `ScalpTrader`: higher-level order execution helpers.
- `Tracker`: remembers a current signal and snooze interval.
- `Session`, `Sessions`: restrict trading to defined time windows.
- `OpenPositionsTracker`: tracks and manages open positions.
- `RAM`: risk assessment and money-management component.
- Trade result components: CSV, JSON, SQLite, or trade records depending on project needs.

## Suggested import style

Prefer public imports from `aiomql` first:

```python
from aiomql import Bot, ForexSymbol, OrderType, ScalpTrader, Sessions, Strategy, TimeFrame, Tracker
```

If a name is not exposed in the installed version, inspect `src/aiomql/`, the package docs, or use the deeper module path from the project.

## Project package map

Expected upstream layout:

- `core/`: MT5 wrappers, config, constants, models, errors, exceptions, state, SQLite, sync wrappers.
- `lib/`: bot, executor, strategy, symbol, order, trader, account, candles, ticks, positions, history, RAM, sessions, terminal, result storage, sync mirrors.
- `contrib/`: strategies, symbols, trackers, traders, utilities.
- `ta_libs/`: pandas-ta and TA-Lib integration.
- `utils/`: decorators, price helpers, process pool.

## Decision guide

Use `MetaTrader` directly when:

- The user wants account info, symbols, raw ticks, raw rates, or terminal checks.
- You are debugging connectivity.
- You need a minimal script.

Use `Strategy` plus `Bot` when:

- The user wants an actual bot.
- Multiple symbols or strategies are involved.
- Sessions, tracking, and repeated execution loops are required.

Use `Bot.process_pool()` when:

- Independent bots must run in separate processes.
- Separate markets, accounts, or strategy families should not share runtime state.

Use sync APIs when:

- The user is in a notebook.
- The user wants a short script and no concurrent strategy loop.
- The environment cannot easily handle an existing async loop.
