# Connors Research Weekly Mean Reversion

## Identity

Name: Connors Research Weekly Mean Reversion v1.0  
Asset class: Liquid US equities with SPY regime filter and SHY idle allocation  
Timeframe: Daily data, weekly decisions, daily stop checks  
Style: Long-only mean reversion

## Edge Hypothesis

Liquid US stocks that become sharply oversold during a rising broad market tend to mean revert. The strategy buys short-term pullbacks only when SPY's six-month trend is positive, then favors lower-volatility candidates to reduce portfolio turbulence.

## Entry Rules

Rules are evaluated on the last available trading day of each week:

1. SPY trailing 126-trading-day total return is positive.
2. The stock is in the liquid universe, ranked by 200-day average dollar volume.
3. Weekly RSI(2) is below 20.
4. Qualified stocks are ranked by trailing 100-day historical volatility.
5. Buy, on the next bar in the research-safe backtest, the lowest-volatility candidates until the portfolio reaches 10 stock slots.

Each stock slot receives `1 / max_positions` target weight. With the default 10 slots, each stock receives 10%.

## Exit Rules

Weekly exit: sell on the weekly close signal when weekly RSI(2) is above 80.  
Daily stop: sell if the close is more than 10% below the recorded entry price.  
Idle capital: allocate unused capital to SHY when SHY data is available.

## Risk Parameters

The strategy is long-only and does not short stocks. The default portfolio cap is 10 equal-weight stock positions. Entry orders are delayed one bar in the backtest to avoid lookahead bias. Trading costs are configurable through `trading_cost` and vectorbt `fees`/`slippage`.

## Implementation

Core pandas implementation:

- `core.py`: indicators, target weights, trade table, metrics, live-readiness checks.
- `backtesting/vectorbt_engine.py`: vectorbt target-percent portfolio adapter.
- `research/walk_forward.py`: rolling/expanding walk-forward validation with train warmup, embargo, and out-of-sample fold metrics.
- `reporting.py`: shared strategy report exports and charts.

The implementation supports a full 500-stock liquid universe when those datasets are available. Local tests use the stock and ETF files under `datasets/`, so those results are development checks rather than a faithful recreation of the published 2003-2018 study.

## Backtest Results

### In-Sample

- Status: local development baseline populated from yfinance stock/ETF datasets on 2026-06-18.
- Command:
  - `./.venv/bin/python scripts/run_connors_research.py --no-use-vectorbt --name connors_local_dev --skip-report-charts --walk-forward --wf-train-size 756 --wf-test-size 126 --wf-step-size 126 --wf-embargo-size 5`
- Dataset:
  - `AAPL`, `MSFT`, `NVDA`, `QQQ`, `SPY`, and `SHY`.
- Assumptions:
  - Pure pandas research backend.
  - Initial cash: 10,000.
  - Fees: 0.05% per rebalance/order event in the research runner.
  - Long-only.
  - Maximum stock slots: 10.
  - Idle capital allocated to `SHY`.
  - Entry and exit weights are delayed one bar in the backtest to avoid lookahead.
- Results:

| Dataset | Period | Rows | Total Return | Annualized Return | Sharpe | Max Drawdown | Trades |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Connors local dev | 2016-06-20 to 2026-06-17 | 2,514 | 34.66% | 3.03% | 0.551 | -11.58% | 186 |

Per-asset contribution summary:

| Symbol | Exposure | Contribution Return | Contribution Sharpe | Contribution Max Drawdown | Entries | Exits | Stop Exits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SHY | 99.96% | 12.96% | 0.899 | -5.18% | 0 | 0 | 0 |
| NVDA | 24.54% | 7.09% | 0.280 | -6.12% | 55 | 54 | 14 |
| QQQ | 23.87% | 6.09% | 0.504 | -2.58% | 40 | 40 | 4 |
| AAPL | 27.76% | 6.00% | 0.357 | -3.26% | 49 | 48 | 8 |
| MSFT | 25.66% | 2.67% | 0.187 | -3.87% | 42 | 41 | 5 |
| SPY | 0.00% | 0.00% | n/a | 0.00% | 0 | 0 | 0 |

- Stored outputs:
  - `trade_results/research/connors_local_dev_metrics.json`
  - `trade_results/research/connors_local_dev_asset_performance.csv`
  - `trade_results/research/connors_local_dev_equity.csv`
  - `trade_results/research/connors_local_dev_drawdown.csv`
  - `trade_results/research/connors_local_dev_trades.csv`
  - `trade_results/research/connors_local_dev_target_weights.csv`
- Interpretation:
  - This is a local development baseline only.
  - The test universe is too small to replicate the published 500-liquid-stock universe.
  - `SHY` contributes materially because the strategy spends most of its time in idle allocation with this small candidate universe.

### Out-of-Sample

- Status: local walk-forward baseline populated on 2026-06-18.
- Method:
  - Rolling windows.
  - Train size: 756 trading days.
  - Test size: 126 trading days.
  - Step size: 126 trading days.
  - Embargo: 5 trading days.
  - No parameter optimization yet; train windows are used as historical warmup and regime context.
- Results:

| Dataset | Folds | Mean OOS Return | OOS Compounded Return | Mean OOS Sharpe | Worst OOS Drawdown | OOS Trades | Profitable Folds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Connors local dev | 13 | 1.82% | 25.27% | 0.787 | -8.23% | 132 | 9 |

- Fold outputs:
  - `trade_results/research/connors_local_dev_walk_forward.csv`
  - `trade_results/research/connors_local_dev_walk_forward_asset_performance.csv`
  - `trade_results/research/connors_local_dev_walk_forward_summary.json`
- Interpretation:
  - OOS fold count is useful, but the candidate universe is still only four tradable stock/ETF candidates plus SPY/SHY.
  - OOS trade count exceeds 100, but this does not satisfy the strategy-framework live threshold because the universe is not representative of the intended 500-liquid-stock universe.
  - Required next research step: expand the yfinance universe, rerun walk-forward, and compare per-asset contribution stability.

### Paper Trade Results

- Status: not started.
- Requirement before live: run at least 2 weeks or 30 trades, whichever is longer.
- Additional requirement: broker symbol mapping and confirmed-fill journal/accounting must be connected before live execution.

## Standard Reporting

- Strategy-level report module: `strategies.ConnorsResearchWeeklyMeanReversion.reporting`.
- Standard report function: `generate_connors_report`.
- Default export root: `trade_results/reports/`.
- Per-run artifacts:
  - `report_data.csv`: equity, drawdown, and position timeline.
  - `trades.csv`: normalized entry/exit trade table.
  - `trade_summary.csv`: trade count and return summary.
  - `metrics.json`: backtest metrics.
  - `report.md`: human-readable report index.
  - `asset_performance.csv`: per-symbol exposure, contribution, Sharpe, drawdown, entries, exits, and stop exits.
  - `target_weights.csv`: daily target allocation matrix.
  - `weekly_rsi.csv`: weekly RSI values forward-filled to daily rows.
  - `regime.csv`: SPY regime filter state.
  - `equity_drawdown.png`: equity curve and drawdown when charts are enabled.
  - `asset_contribution.png`: per-symbol contribution chart when charts are enabled.
  - `stock_allocations.png`: allocation stack when charts are enabled.
  - `symbol_trades/<SYMBOL>_trades.png`: per-symbol entry and exit markers when charts are enabled.
- Research runner hook:
  - `scripts/run_connors_research.py`.
  - Add `--walk-forward` for OOS validation.
  - Use `--skip-report-charts` for table-only report generation on machines without chart dependencies.

## Live Readiness

Live execution should be blocked until a broker adapter supplies:

- confirmed stock/ETF tradability and symbol mapping
- latest daily OHLCV and volume data
- portfolio holdings/current weights
- order sizing compatible with the broker's share or fractional-share rules
- journal and ledger writes based only on confirmed fills
