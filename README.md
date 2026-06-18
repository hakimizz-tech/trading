# Trading Bot Framework

This project separates strategy research from MetaTrader 5 execution:

- `strategies/BollingerBand/` is the canonical strategy package for Bollinger Band research, backtesting, execution adapters, and strategy-specific tests.
- `strategies/` is the central namespace for new strategy implementations.
- `bot.py` loads one or many strategy specs from JSON and runs them through an aiomql `Bot`.
- `bot_config.py` validates bot settings without requiring aiomql.

Live execution is disabled by default. Use demo/dry-run first.

## Linux Research

```bash
.venv/bin/python -m unittest discover -s strategies/BollingerBand/tests
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m strategies.BollingerBand.core path/to/ohlcv.csv --date-col time
```

## Strategy Packages

New strategies should live under `strategies/` so more strategies can be added
without spreading core logic, adapters, and tests across unrelated top-level folders.

```text
strategies/
  strategy_name/
    __init__.py
    core.py              # pure pandas/numpy indicators, signals, research backtest
    backtesting/
      __init__.py
      signals.py         # converts strategy output into long/short entries and exits
      vectorbt_engine.py # vectorbt adapter for this strategy
    execution/
      __init__.py
      aiomql_strategy.py # aiomql Strategy wrapper for Windows/MT5
    tests/
      __init__.py
      test_core.py
      test_backtesting.py
```

The current Bollinger implementation follows this layout:

- `strategies/BollingerBand/STRATEGY.md` is the versioned strategy definition, including hypothesis, entry rules, exits, risk parameters, filters, and performance gates.
- `strategies/BollingerBand/core.py` contains pandas/numpy indicator, signal, exit, and research backtest logic that runs on Linux.
- `strategies/BollingerBand/backtesting/signals.py` normalizes Bollinger outputs into long/short entries, exits, and optional stop/take-profit arrays.
- `strategies/BollingerBand/backtesting/vectorbt_engine.py` runs prepared signals through vectorbt.
- `strategies/BollingerBand/execution/aiomql_strategy.py` wraps the tested signal logic as an aiomql `Strategy` for Windows/MT5.
- `strategies/BollingerBand/tests/` covers the strategy package contract.

The Rising Assets implementation follows the new central strategy namespace:

- `strategies/RisingAssest/STRATEGY.md` is the machine-readable strategy summary based on `strategies/RisingAssest/rising-assets-strategy.md`.
- `strategies/RisingAssest/core.py` implements monthly momentum scoring, top-asset selection, inverse-volatility weighting, and portfolio backtesting.
- `strategies/RisingAssest/backtesting/signals.py` prepares portfolio-level target and execution weights.
- `strategies/RisingAssest/reporting.py` exports standard reports plus target weights and momentum scores.

Rising Assets is a multi-asset portfolio rotation strategy, not a single-symbol aiomql execution strategy yet. Before adding it to `strategy_registry.py`, define broker symbol mapping, rebalance order generation, portfolio reconciliation, and MT5-supported instruments.

Global folders should stay small:

- `accounting/` holds the shared double-entry ledger used after confirmed fills.
- `backtesting/` holds shared signal contracts consumed by backtesting engines.
- `bot.py` and `bot_config.py` orchestrate runtime settings and bot startup.
- `execution/` holds shared aiomql execution base classes, broker snapshots, live gates, and sizing.
- `journal/` holds the shared SQLite trade journal used by all strategies.
- `reporting/` holds shared strategy report exports; each strategy only supplies overlays or data enrichment.
- `scripts/` holds environment and operational checks.
- `strategy_registry.py` maps JSON strategy types to executable strategy classes.
- `visualization/` holds shared charts for all strategies and trade logs.
- `tests/` holds cross-strategy or application-level tests only.

Install the optional vectorbt backend:

```bash
.venv/bin/python -m pip install -r requirements-backtest.txt
```

Install the optional visualization backend:

```bash
.venv/bin/python -m pip install -r requirements-visualization.txt
```

Programmatic use:

```python
from strategies.BollingerBand.backtesting.vectorbt_engine import VectorBTBacktestConfig, run_bollinger_vectorbt
from strategies.BollingerBand.core import ExitPlan

result = run_bollinger_vectorbt(
    data,
    exit_plan=ExitPlan(),
    config=VectorBTBacktestConfig(init_cash=10_000, fees=0.003, slippage=0.001, freq="1h"),
)

print(result.metrics)
print(result.stats)
```

Shared visualization works with any strategy that produces OHLCV data, equity,
positions, and a trade log:

```python
from visualization import plot_backtest_report, save_figure

fig = plot_backtest_report(result, title="Bollinger Adaptive")
save_figure(fig, "reports/bollinger_adaptive.png")
```

The Bollinger strategy separates entries from exits and supports an adaptive mode:

- Entries: mean reversion, BBMA, BB + RSI, or adaptive BB + RSI + MACD.
- Adaptive Regime A: wide-band ranging market, BB bounce entries confirmed by RSI.
- Adaptive Regime B: recent Bollinger squeeze, breakout entries confirmed by MACD crossover.
- Stop loss: ATR-based stop, default `2.0 × ATR(14)`.
- Take profit: fixed R-multiple target, default `2R`.
- Trailing stop: ATR trailing after the trade reaches the activation R multiple.
- Time stop: exits dead trades after `max_hold_bars` when not profitable.
- Signal exit: mean-reversion exits at the middle band; breakout exits on reverse MACD cross.

The module uses pandas/numpy indicators by default and will use TA-Lib for RSI/MACD if `talib` is installed.

Example:

```bash
.venv/bin/python -m strategies.BollingerBand.core data.csv \
  --date-col time \
  --strategy adaptive \
  --atr-stop-mult 2.0 \
  --take-profit-rr 2.0 \
  --trailing-atr-mult 2.5 \
  --max-hold-bars 50 \
  --squeeze-quantile 0.2 \
  --wide-quantile 0.6
```

## Windows aiomql Setup

Use Windows with Python 3.13+, MetaTrader 5, aiomql, and a broker demo account.
The `MetaTrader5` dependency behind aiomql is not installable for this Linux
research environment, so install the aiomql runtime only after migrating to
Windows.

```bash
python -m pip install -r requirements-aiomql.txt
copy aiomql.json.example aiomql.json
python scripts/check_aiomql_env.py --project .
```

Fill `aiomql.json` locally. Do not commit it.

Then edit `bot_settings.example.json` or create your own settings file:

```bash
python bot.py --settings bot_settings.example.json
```

Executable strategy signals are journaled to SQLite by default:

```json
{
  "journal_enabled": true,
  "journal_db_path": "trade_results/trade_journal.sqlite",
  "accounting_enabled": true,
  "accounting_db_path": "trade_results/trade_accounting.sqlite"
}
```

Dry-run signals, blocked signals, live order attempts, submitted orders, and
order errors are recorded. In live mode, journaling failure blocks the order
attempt so production trades remain auditable.

Live execution gates use a normalized broker snapshot for spread checks, open
position limits, daily-loss limits, and optional risk-based lot sizing. Keep
`live_trading` false until these gates have been validated against a Windows
demo MT5 account for the target broker symbols.

Accounting is separate from journaling. The journal records strategy decisions
and order lifecycle events; the double-entry ledger records confirmed economic
activity such as fills, realized exits, fees, funding, and withdrawals. Do not
post accounting entries for dry-run signals or unfilled submitted orders.
Confirmed broker closes with realized P&L are posted idempotently by broker
deal/order id.

## Adding Strategies

1. Create a strategy package under `strategies/`.
2. Put pure signal logic in `StrategyName/core.py`; it should accept an OHLCV DataFrame and avoid aiomql imports.
3. Return the shared `backtesting.PreparedSignals` contract from `StrategyName/backtesting/signals.py`.
4. Put vectorbt/backtrader adapters in `StrategyName/backtesting/`.
5. Put the aiomql wrapper in `StrategyName/execution/aiomql_strategy.py`, inheriting from `execution.StrategyAiomqlBase`.
6. Use `reporting.generate_strategy_report` for generic reports; supply only strategy-specific overlays or frame enrichment.
7. Register the wrapper in `strategy_registry.py`.
8. Add a strategy spec to the JSON settings file.
9. Keep `live_trading` false until the strategy has been backtested and demo tested.
