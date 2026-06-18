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
