# Strategies

This directory is the central home for strategy implementations.

Each strategy package should keep the same shape:

```text
strategies/
  strategy_name/
    __init__.py
    STRATEGY.md
    core.py
    backtesting/
      __init__.py
      signals.py
    reporting.py
    tests/ or ../../tests
```

Shared framework code stays outside strategy packages:

- `backtesting/`: common signal contracts.
- `execution/`: aiomql base, broker snapshots, sizing, and live gates.
- `journal/`: shared trade journal.
- `accounting/`: shared ledger.
- `reporting/`: generic report exports.
- `visualization/`: reusable charts.
- `strategy_registry.py`: maps bot config strategy types to executable aiomql classes.

Strategy packages should import shared framework code, not other strategy packages.

## Required Strategy Report Sections

Every `STRATEGY.md` must include a `Backtest Results` section with the same structure:

- `In-Sample`: status, command, assumptions, result table, stored outputs, and interpretation.
- `Out-of-Sample`: walk-forward method, fold settings, result table, fold outputs, and interpretation. If not run yet, mark it as `not populated` and name the command/module needed.
- `Paper Trade Results`: status, minimum paper-trade gate, and stored outputs when available.
- `Standard Reporting`: report module, standard report function, export root, report artifacts, and research runner hook.

Strategy-level tables should include, where applicable:

- period and row count
- total return
- annualized return
- Sharpe ratio
- maximum drawdown
- win rate or rebalance/trade count
- profit factor when trade-level P&L is available
- per-asset contribution or latest allocation for portfolio strategies
- walk-forward folds, mean OOS return, mean OOS Sharpe, worst OOS drawdown, OOS trade count, and profitable folds

The documentation should distinguish research baselines from deployment gates. A strategy with too few OOS trades, weak OOS Sharpe, missing broker mapping, or no paper-trade record remains research/dry-run only.
