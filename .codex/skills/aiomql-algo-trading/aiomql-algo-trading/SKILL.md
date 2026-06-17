---
name: aiomql-algo-trading
description: Guides development of algorithmic trading bots with the aiomql Python framework for MetaTrader 5. Use when the user asks to install aiomql, create async MT5 code, build Strategy subclasses, configure Bot orchestration, Sessions, RAM risk management, Trader or ScalpTrader execution, ForexSymbol market data, technical indicators, trade recording, position tracking, or debug aiomql projects. Do NOT use for unrelated Python finance questions or live trade recommendations.
license: MIT
compatibility: Agent Skills format. Intended for Codex or coding agents working on Python aiomql projects. Live MT5 execution needs Python 3.13 or newer, Windows, MetaTrader 5 terminal, and a trading account.
metadata:
  author: Hakeem Keem and ChatGPT
  version: 1.0.0
  category: algorithmic-trading
  library: aiomql
  source: github.com/Ichinga-Samuel/aiomql
---

# aiomql Algorithmic Trading Skill

## Purpose

Use this skill to help build, review, debug, and scaffold Python projects that use `aiomql`, an async-first algorithmic trading framework on top of MetaTrader 5. The skill should turn vague requests such as “build me an aiomql bot” into safe, structured code with configuration, strategy, bot wiring, sessions, risk controls, logging, and tests.

## Critical operating rules

1. Treat trading automation as high-risk software. Do not promise profits, win rates, guaranteed signals, or financial outcomes.
2. Default to demo, dry-run, backtest, or signal-only code. Do not generate live-order code unless the user explicitly asks for live execution and confirms they understand the risk.
3. Never hardcode real credentials. Use `aiomql.json.example`, environment variables, or a local ignored `aiomql.json` file. Redact secrets in explanations and diagnostics.
4. Before suggesting live execution, verify the environment constraints: Python 3.13 or newer, Windows, installed MetaTrader 5 terminal, broker account, and symbol availability.
5. Ask for missing trading requirements when they affect code correctness: symbols, timeframe, broker symbol suffix, session hours, risk per trade, stop-loss logic, take-profit logic, spread filter, maximum open positions, and demo or live mode.
6. Prefer simple, auditable strategies over complex black-box logic. Add logging and comments only where they clarify trading flow.
7. Use aiomql abstractions rather than raw MetaTrader 5 calls unless the user specifically asks for low-level access.
8. For every strategy that can place trades, include a risk gate, a session gate, and an execution gate.

## When the user asks for aiomql code

Follow this sequence:

1. Inspect the project if files exist.
   - Look for `pyproject.toml`, `requirements.txt`, `uv.lock`, `aiomql.json`, `strategies/`, `tests/`, and existing bot entry points.
   - If the installed API differs from these notes, inspect the local package or the upstream repository before editing.

2. Choose the correct entry point.
   - Use async `MetaTrader`, async `Strategy`, and `await bot.start()` when the surrounding app already has an event loop.
   - Use `bot.execute()` for normal script entry points.
   - Use synchronous mirrors only for notebooks, quick scripts, or user requests for sync code.

3. Create or update configuration safely.
   - Generate `aiomql.json.example`, not a real credentials file.
   - Add `.gitignore` entries for `aiomql.json`, SQLite databases, logs, and result files if missing.
   - Explain that the user should fill credentials locally.

4. Design the strategy.
   - Subclass `Strategy`.
   - Put tunable values in the `parameters` dictionary.
   - Let declared parameters become instance attributes.
   - Implement `trade()` as the framework execution loop.
   - Keep signal generation separate from order execution, usually with a `find_entry()` or `generate_signal()` method.

5. Wire execution through aiomql components.
   - Use `ForexSymbol` for forex instruments when pip and volume handling matter.
   - Use `Trader`, `SimpleTrader`, or `ScalpTrader` for order placement instead of hand-building raw requests unless needed.
   - Use `Sessions` and `Session` to restrict active trading windows.
   - Use `Tracker` for signal persistence, snooze intervals, and delayed re-entry.
   - Use `OpenPositionsTracker` or custom tracking for trailing stops, take-profit extension, or position management.

6. Add risk controls.
   - Use `RAM` or a clear custom risk layer for lot sizing and money management.
   - Include maximum spread checks, maximum concurrent positions, maximum daily loss, minimum stop distance, and explicit volume constraints where relevant.
   - Validate stop-loss and take-profit values before sending an order.

7. Add observability and persistence.
   - Configure `logging` at the entry point.
   - Record results to CSV, JSON, or SQLite when the user asks for auditability.
   - Keep trade records and diagnostics outside source code directories.

8. Test before live execution.
   - Run syntax checks and unit tests where possible.
   - Use `scripts/check_aiomql_env.py` from this skill to inspect Python, OS, package import, and local config without connecting to a broker.
   - For strategy logic, isolate signal functions so they can be tested without MetaTrader 5.

## Standard project structure to create

Use this structure for new aiomql projects unless the user has an existing convention:

```text
project-root/
  aiomql.json.example
  .gitignore
  bot.py
  strategies/
    __init__.py
    ema_crossover.py
  tests/
    test_strategy_config.py
  logs/
  trade_results/
```

Do not create a real `aiomql.json` containing credentials. Create only `aiomql.json.example`.

## Starter strategy pattern

When generating a strategy, prefer this shape:

```python
import logging

from aiomql import ForexSymbol, OrderType, ScalpTrader, Sessions, Strategy, TimeFrame, Tracker, Trader

logger = logging.getLogger(__name__)


class MyStrategy(Strategy):
    parameters = {
        "timeframe": TimeFrame.M15,
        "count": 300,
        "interval": TimeFrame.M15,
        "timeout": 60 * 60,
        "live_trading": False,
    }

    def __init__(self, *, symbol: ForexSymbol, params: dict | None = None, trader: Trader | None = None, sessions: Sessions | None = None, name: str = "MyStrategy"):
        super().__init__(symbol=symbol, params=params, sessions=sessions, name=name)
        self.tracker = Tracker(snooze=self.interval.seconds)
        self.trader = trader or ScalpTrader(symbol=self.symbol)

    async def find_entry(self) -> None:
        candles = await self.symbol.copy_rates_from_pos(timeframe=self.timeframe, count=self.count)
        # Add indicators and update self.tracker here.
        self.tracker.update(order_type=None, snooze=self.interval.seconds)

    async def trade(self) -> None:
        await self.find_entry()

        if self.tracker.order_type is None:
            await self.sleep(secs=self.tracker.snooze)
            return

        if not self.live_trading:
            logger.info("Dry-run signal for %s: %s", self.symbol.name, self.tracker.order_type)
            await self.delay(secs=self.tracker.snooze)
            return

        await self.trader.place_trade(order_type=self.tracker.order_type, parameters=self.parameters)
        await self.delay(secs=self.tracker.snooze)
```

Adapt imports to the installed aiomql version if names move between releases.

## Bot wiring pattern

Use this for normal script execution:

```python
import logging

from aiomql import Bot, ForexSymbol, OpenPositionsTracker
from strategies.ema_crossover import EMAXOver

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    symbols = [ForexSymbol(name=name) for name in ["EURUSD", "GBPUSD", "USDJPY"]]
    strategies = [EMAXOver(symbol=symbol) for symbol in symbols]

    bot = Bot()
    bot.add_strategies(strategies)
    bot.add_coroutine(coroutine=OpenPositionsTracker(autocommit=True).track, on_separate_thread=True)
    bot.execute()


if __name__ == "__main__":
    main()
```

If the user is already inside async code, use `await bot.start()` rather than `bot.execute()`.

## Reference files

Consult these bundled files when more detail is needed:

- `references/aiomql-api-map.md` for package concepts and import choices.
- `references/strategy-patterns.md` for strategy templates, sessions, bot orchestration, and technical analysis patterns.
- `references/risk-and-live-trading-safety.md` for live trading gates, secrets handling, and risk controls.
- `references/testing-and-debugging.md` for trigger tests, environment checks, and troubleshooting.

Useful scripts:

- `scripts/check_aiomql_env.py` checks Python version, OS, aiomql import, project files, and redacted config state.
- `scripts/scaffold_aiomql_project.py` creates a safe dry-run starter project.
- `scripts/validate_skill.py` validates this skill folder structure and frontmatter.

## Troubleshooting guidance

### aiomql import fails

Check Python version, virtual environment activation, and package installation:

```bash
python --version
python -m pip install aiomql
python scripts/check_aiomql_env.py --project .
```

### MetaTrader connection fails

Verify Windows, MetaTrader 5 terminal installation, broker server name, account credentials, and terminal login. Do not expose credentials in chat, logs, or commits.

### Strategy runs but no trades occur

Check sessions, symbol visibility, spread filters, tracker state, dry-run mode, risk gates, and whether `live_trading` is still false.

### Trades open too frequently

Add a tracker snooze, signal confirmation, max-position check, cooldown per symbol, and session constraints.

### Technical indicators missing

Install the relevant extras or dependencies. Use `aiomql[talib]` for TA-Lib support where the local system can build or install TA-Lib.

## Output quality checklist

Before finalizing aiomql code, verify:

- The code is compatible with Python 3.13 or newer.
- Live execution is disabled by default.
- Credentials are not hardcoded.
- Strategy parameters are configurable.
- Entry signal logic is separated from execution.
- Sessions and risk controls are present where trades can be placed.
- Logging is configured.
- The bot entry point is correct for sync or async context.
- Tests or at least syntax checks are provided.
- The user receives exact commands to run the code.
