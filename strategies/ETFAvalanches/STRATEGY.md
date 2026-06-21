# ETF Avalanches

## Identity

Name: ETF Avalanches v1.0  
Asset class: Global, regional, sector, and broad equity ETFs  
Timeframe: Daily data  
Style: Short-only mean reversion inside bearish regimes

## Edge Hypothesis

Equity ETFs in established downtrends often experience sharp short-term bear-market rallies. These rallies can become attractive short entries when the longer-term and intermediate-term trends remain negative. The strategy attempts to profit when those rallies fade and the existing downtrend resumes.

## Universe

Local development universe:

- `SPY`: S&P 500 ETF
- `IWM`: Russell 2000 ETF
- `EFA`: developed international equity ETF
- `EEM`: emerging markets equity ETF
- `VNQ`: US real estate ETF
- `SHY`: 1-3 year Treasury ETF used as the idle-capital sleeve

Research universe scaffold:

- Core broad ETFs: `SPY`, `IWM`, `EFA`, `EEM`, `VNQ`
- Sector ETFs: `XLB`, `XLE`, `XLF`, `XLI`, `XLK`, `XLP`, `XLU`, `XLV`, `XLY`
- Country/regional ETFs: `EWA`, `EWC`, `EWG`, `EWH`, `EWJ`, `EWS`, `EWT`, `EWU`, `EWY`, `EWZ`

The local baseline only uses ETFs already available in `datasets/`; it is not the full book-style universe.

## Entry Rules

Rules are evaluated for every shortable ETF except `SHY`.

1. Long-term bear regime: trailing 252-trading-day return is negative.
2. Intermediate bear confirmation: trailing 21-trading-day return is negative.
3. Short-term strength: RSI(2) is above 70.
4. Limit entry: place a next-day sell-short limit order 3% above the signal close.
5. Fill model: the sell-short order fills if next-day high is greater than or equal to the limit price.
6. Candidate ranking: if too many ETFs qualify, rank by highest 100-day historical volatility.
7. Maximum positions: hold up to 5 short positions.

## Exit Rules

There are two buy-to-cover exits:

1. RSI cover: exit a short when RSI(2) drops below 15.
2. Momentum cover: exit a short when trailing 21-trading-day return turns positive.

No long equity positions are opened. Idle capital is allocated to `SHY` when `SHY` data is available.

## Risk Parameters

- Short-only equity ETF exposure.
- Maximum 5 simultaneous shorts.
- Equal short slot size: 20% notional per short.
- Maximum gross short exposure: 100%.
- Idle capital sleeve: `SHY`.
- Entry orders use a daily OHLC limit-fill model.
- Execution weights are delayed one bar in portfolio return simulation to avoid lookahead bias.
- Live execution requires broker confirmation that each ETF is shortable.

## Implementation

- Core implementation: `strategies.ETFAvalanches.core`.
- Vectorbt research adapter: `strategies.ETFAvalanches.backtesting.vectorbt_engine`.
- Walk-forward validation: `strategies.ETFAvalanches.research.walk_forward`.
- Report wrapper: `strategies.ETFAvalanches.reporting`.
- Research runner: `scripts/run_etf_avalanches_research.py`.
- Yahoo Finance dataset collector: `scripts/download_yfinance_history.py`.

## Backtest Results

### In-Sample

- Status: local baseline populated from available yfinance ETF datasets on 2026-06-19.
- Research command:
  - `./.venv/bin/python scripts/run_etf_avalanches_research.py --skip-report-charts --walk-forward --wf-train-size 756 --wf-test-size 126 --wf-step-size 126 --wf-embargo-size 5`
- Assumptions:
  - Pure pandas research backend by default.
  - Initial cash: 10,000.
  - Fees: 0.05% on target-weight changes.
  - Short-only ETF positions.
  - Idle capital allocated to `SHY`.
  - Sell-short limit order fills when next-day high reaches the limit price.
  - One-bar delayed execution weights.
- Results:

| Dataset | Period | Rows | Total Return | Annualized Return | Sharpe | Max Drawdown | Win Rate | Profit Factor | Trades | Avg Short Exposure |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ETF Avalanches local dev | 2016-06-20 to 2026-06-18 | 2,514 | 16.38% | 1.53% | 0.474 | -8.39% | 65.22% | 1.479 | 23 | 0.53% |

Per-asset contribution summary:

| Symbol | Exposure | Avg Weight | Contribution Return | Contribution Sharpe | Contribution Max Drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| SHY | 99.84% | 99.47% | 15.50% | 0.987 | -5.48% |
| IWM | 0.72% | -0.14% | 0.90% | 0.108 | -1.86% |
| EEM | 0.60% | -0.12% | 0.61% | 0.113 | -0.94% |
| EFA | 0.56% | -0.11% | 0.53% | 0.106 | -0.89% |
| VNQ | 0.40% | -0.08% | -0.41% | -0.052 | -2.47% |
| SPY | 0.36% | -0.07% | -0.51% | -0.084 | -1.22% |

- Stored outputs:
  - `trade_results/research/etf_avalanches_local_dev_metrics.json`
  - `trade_results/research/etf_avalanches_local_dev_asset_performance.csv`
  - `trade_results/research/etf_avalanches_local_dev_closed_trades.csv`
  - `trade_results/research/etf_avalanches_local_dev_target_weights.csv`
  - `trade_results/research/etf_avalanches_local_dev_live_readiness.json`
  - `trade_results/reports/etf_avalanches_local_dev/`
- Interpretation:
  - The local baseline is positive and drawdown is controlled, but the result is dominated by `SHY` because the short strategy was active only rarely.
  - Trade count is only 23 over roughly 10 years, far below the 100-trade research threshold.
  - The tested universe is too small to validate the original strategy premise.
  - Current status remains research-only.

### Out-of-Sample

- Status: local walk-forward baseline populated on 2026-06-19.
- Method:
  - Rolling windows.
  - Train size: 756 trading days.
  - Test size: 126 trading days.
  - Step size: 126 trading days.
  - Embargo: 5 trading days.
  - No parameter optimization; train windows are used as historical warmup.
- Results:

| Dataset | Folds | Mean OOS Return | OOS Compounded Return | Mean OOS Sharpe | Worst OOS Drawdown | OOS Trades | Profitable Folds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ETF Avalanches local dev | 13 | 0.83% | 11.25% | 0.941 | -5.63% | 21 | 10 |

- Fold outputs:
  - `trade_results/research/etf_avalanches_local_dev_walk_forward.csv`
  - `trade_results/research/etf_avalanches_local_dev_walk_forward_asset_performance.csv`
  - `trade_results/research/etf_avalanches_local_dev_walk_forward_summary.json`
- Interpretation:
  - OOS results are directionally encouraging, with positive compounded OOS return, positive mean OOS Sharpe, and 10 profitable folds out of 13.
  - The OOS trade count is only 21, so the signal sample is too small for deployment confidence.
  - The local data period starts in 2016, so it misses the 2008 global financial crisis that is central to the original ETF Avalanches thesis.

### Final Assessment

Current status: research-only, blocked from paper trading and live trading.

The local implementation validates the mechanics of the strategy, but not the deployability of the edge. The baseline is positive mainly because idle capital sat in `SHY`, while the actual short module had very low exposure and too few trades.

Main shortcomings:

- The local universe is incomplete relative to the intended country, regional, and sector ETF universe.
- Trade count is far below the 100-trade research threshold.
- Average short exposure is only 0.53%, so the strategy has not been tested as a meaningful portfolio hedge.
- The local sample starts in 2016 and does not include 2008, the main stress regime this strategy was designed to exploit.
- Daily OHLC limit-fill modeling is an approximation; live short entries need broker-specific borrow, margin, and fill handling.
- Live execution cannot proceed until ETF shortability, borrow availability, hard-to-borrow costs, and broker symbol mappings are confirmed.

Current research judgment:

| Gate | Status | Reason |
| --- | --- | --- |
| Research readiness | Blocked | Needs full ETF universe and longer historical data. |
| Backtest validation | Incomplete | Positive baseline, but only 23 trades and very low short exposure. |
| Walk-forward validation | Incomplete | Positive OOS baseline, but only 21 OOS trades. |
| Risk validation | Blocked | Short borrow, margin, and hard-to-borrow costs are not modeled. |
| Reporting readiness | Ready for research | Standard report and short-specific artifacts are generated. |
| Paper trading gate | Blocked | Needs full-universe validation and broker shortability checks. |
| Live trading gate | Blocked | No broker-confirmed short execution path yet. |

Required next research:

1. Download the full ETF Avalanches universe with `--period max`.
2. Add static benchmark comparisons: `SH`, `SPY`, `SHY`, and a static short `SPY` proxy.
3. Add crisis-window analysis for 2008, Q4 2018, COVID 2020, 2022, and large `SPY`/`QQQ` drawdown windows.
4. Test entry limit levels from 1.5% to 3.5%.
5. Add borrow-cost and hard-to-borrow assumptions for live realism.
6. Validate with at least 100 closed short trades before paper trading.

### Paper Trade Results

- Status: not started.
- Requirement before live: run at least 2 weeks or 30 short-entry/order events, whichever is longer, after the full-universe backtest passes.

## Standard Reporting

- Strategy-level report module: `strategies.ETFAvalanches.reporting`.
- Standard report function: `generate_etf_avalanches_report`.
- Default export root: `trade_results/reports/`.
- Per-run artifacts:
  - `report_data.csv`: equity, drawdown, and short exposure timeline.
  - `trades.csv`: normalized short-entry and cover events.
  - `closed_trades.csv`: paired short trades with entry, exit, holding days, P&L, and return.
  - `trade_summary.csv`: closed-trade count, win/loss count, win rate, P&L, and return summary.
  - `metrics.json`: backtest metrics.
  - `report.md`: human-readable report with strategy-specific note.
  - `candidate_signals.csv`: candidate sell-limit fills ranked by volatility.
  - `target_weights.csv`: daily target allocation matrix.
  - `execution_weights.csv`: one-bar delayed execution weights.
  - `short_exposure.csv`: gross short exposure through time.
  - `asset_performance.csv`: per-ETF exposure, contribution, Sharpe, and drawdown.
  - `rsi.csv`, `long_returns.csv`, `intermediate_returns.csv`, `volatility.csv`: indicator diagnostics.
  - `equity_short_events.png`: strategy equity with short-entry and cover markers when charts are enabled.
  - `equity_drawdown.png`: equity curve and drawdown when charts are enabled.
  - `short_exposure.png`: short exposure and `SHY` allocation when charts are enabled.
  - `asset_contribution.png`: per-ETF contribution chart when charts are enabled.
  - `trade_counts.png`: closed short trades by ETF when charts are enabled.
  - `return_distribution.png`: return distribution when charts are enabled.
  - `asset_correlation.png`: ETF return correlation heatmap when charts are enabled.
- Research runner hook:
  - `scripts/run_etf_avalanches_research.py`.
  - Add `--walk-forward` for OOS validation.
  - Use `--skip-report-charts` for table-only report generation on machines without chart dependencies.

## Live Readiness

Current live status: blocked.

Latest local readiness output:

- Data coverage: complete for `SPY`, `IWM`, `EFA`, `EEM`, `VNQ`, and `SHY`.
- Rows: 2,514.
- Blockers:
  - missing broker symbol mapping for `EEM`, `EFA`, `IWM`, `SHY`, `SPY`, and `VNQ`
  - missing shortable confirmation for `EEM`, `EFA`, `IWM`, `SPY`, and `VNQ`

Live execution should be blocked until a broker adapter supplies:

- broker symbol mapping for all ETFs
- latest daily OHLCV data including high and close
- current positions/current weights
- shortability and borrow-cost checks for every short candidate
- margin and buying-power checks for short orders
- broker-specific limit order handling
- journal and ledger writes based only on confirmed fills
