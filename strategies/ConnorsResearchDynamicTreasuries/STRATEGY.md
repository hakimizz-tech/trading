# Connors Research Dynamic Treasuries

## Identity

Name: Connors Research Dynamic Treasuries v1.0  
Asset class: US Treasury ETFs  
Timeframe: Daily data, weekly rebalance  
Style: Long-only trend following / dynamic duration

## Edge Hypothesis

US Treasuries often receive safe-haven flows during equity-market stress. A portfolio that is always long Treasuries but dynamically extends duration when longer maturities show positive momentum can preserve capital in rising-rate environments while still participating in flight-to-quality rallies.

## Universe

Anchor:

- `IEI`: 3-7 year US Treasuries

Duration assets:

- `IEF`: 7-10 year US Treasuries
- `TLH`: 10-20 year US Treasuries
- `TLT`: 20+ year US Treasuries

## Entry And Allocation Rules

Rules are evaluated at the end of each business week:

1. Calculate trailing total returns for `IEF`, `TLH`, and `TLT` over 21, 42, 63, 84, and 105 trading days.
2. For each duration ETF, allocate 5% for every positive lookback.
3. Each duration ETF can therefore receive 0%, 5%, 10%, 15%, 20%, or 25%.
4. Allocate all residual capital to `IEI`.
5. The strategy is always 100% allocated to Treasury ETFs.

## Exit Rules

The strategy exits or reduces an ETF only through the weekly rebalance process. There is no stop-loss, take-profit, short selling, or cash state in the published rules.

## Risk Parameters

- Long-only Treasury ETF exposure.
- Maximum 25% allocation to each longer-duration ETF.
- Minimum 25% allocation to `IEI` when all duration assets have positive momentum.
- Maximum 100% allocation to `IEI` when no duration asset has positive momentum.
- Execution is delayed one bar in the backtest to avoid lookahead bias.

## Implementation

- Core implementation: `strategies.ConnorsResearchDynamicTreasuries.core`.
- Vectorbt research adapter: `strategies.ConnorsResearchDynamicTreasuries.backtesting.vectorbt_engine`.
- Walk-forward validation: `strategies.ConnorsResearchDynamicTreasuries.research.walk_forward`.
- Report wrapper: `strategies.ConnorsResearchDynamicTreasuries.reporting`.
- Research runner: `scripts/run_dynamic_treasuries_research.py`.
- Yahoo Finance dataset collector: `scripts/download_yfinance_history.py`.

## Backtest Results

### In-Sample

- Status: local baseline populated from yfinance Treasury ETF datasets on 2026-06-19.
- Data command:
  - `./.venv/bin/python scripts/download_yfinance_history.py --tickers IEI IEF TLH TLT --period 10y --interval 1d --repair --manifest datasets/yfinance_dynamic_treasuries_manifest.json`
- Research command:
  - `./.venv/bin/python scripts/run_dynamic_treasuries_research.py --name dynamic_treasuries_local_dev --skip-report-charts --walk-forward --wf-train-size 756 --wf-test-size 126 --wf-step-size 126 --wf-embargo-size 5`
- Assumptions:
  - Pure pandas research backend by default.
  - Initial cash: 10,000.
  - Fees: 0.05% per rebalance event in the research runner.
  - Long-only.
  - Weekly rebalance.
  - One-bar delayed execution.
- Results:

| Dataset | Period | Rows | Total Return | Annualized Return | Sharpe | Max Drawdown | Rebalances | Avg Duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dynamic Treasuries local dev | 2016-06-20 to 2026-06-18 | 2,514 | 3.32% | 0.33% | 0.050 | -19.67% | 327 | 7.26 |

Latest target allocation:

| Symbol | Target Weight |
| --- | ---: |
| IEI | 60.00% |
| IEF | 5.00% |
| TLH | 15.00% |
| TLT | 20.00% |

Per-asset contribution summary:

| Symbol | Exposure | Avg Weight | Contribution Return | Contribution Sharpe | Contribution Max Drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| IEF | 75.58% | 13.00% | 3.81% | 0.373 | -1.83% |
| IEI | 99.96% | 63.07% | 3.35% | 0.117 | -13.14% |
| TLH | 73.35% | 12.10% | 2.50% | 0.143 | -3.44% |
| TLT | 71.80% | 11.80% | 0.39% | 0.017 | -7.18% |

- Stored outputs:
  - `trade_results/research/dynamic_treasuries_local_dev_metrics.json`
  - `trade_results/research/dynamic_treasuries_local_dev_asset_performance.csv`
  - `trade_results/research/dynamic_treasuries_local_dev_duration_exposure.csv`
  - `trade_results/research/dynamic_treasuries_local_dev_target_weights.csv`
  - `trade_results/research/dynamic_treasuries_local_dev_live_readiness.json`
  - `trade_results/reports/dynamic_treasuries_local_dev/`
- Interpretation:
  - The recent 2016-2026 sample is a difficult period for duration strategies because it includes the 2022 bond bear market/rate shock.
  - The strategy stayed fully invested in Treasuries but did not avoid enough drawdown from longer-duration exposure.
  - This local baseline is research-only; it does not satisfy a paper-trading or live deployment threshold.

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

| Dataset | Folds | Mean OOS Return | OOS Compounded Return | Mean OOS Sharpe | Worst OOS Drawdown | OOS Rebalances | Profitable Folds | Mean OOS Duration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dynamic Treasuries local dev | 13 | -0.01% | -1.62% | -0.202 | -10.21% | 229 | 6 | 7.18 |

- Fold outputs:
  - `trade_results/research/dynamic_treasuries_local_dev_walk_forward.csv`
  - `trade_results/research/dynamic_treasuries_local_dev_walk_forward_asset_performance.csv`
  - `trade_results/research/dynamic_treasuries_local_dev_walk_forward_summary.json`
- Interpretation:
  - OOS results are weak and slightly negative over the local 2019-2026 fold windows.
  - The strategy remains useful as a defensive module candidate, but it needs benchmark comparison against static `IEI`, `IEF`, `TLT`, and blended Treasury allocations before promotion.
  - Do not paper trade this configuration until benchmark and crisis-window analysis are added.

### Final Assessment

Current status: research-only, blocked from paper trading and live trading.

The local Dynamic Treasuries implementation follows the intended allocation logic, but the current configuration failed to prove a durable defensive edge in the 2016-2026 sample.

Main shortcomings:

- Very low realized return: 3.32% total return and 0.33% annualized return over roughly 10 years.
- No meaningful risk-adjusted edge: Sharpe is 0.050 in-sample and -0.202 across walk-forward OOS folds.
- Drawdown is too high for a defensive Treasury module: max drawdown reached -19.67%.
- Walk-forward validation is negative: OOS compounded return is -1.62%, with only 6 profitable folds out of 13.
- The ETF universe is highly correlated. `IEI`, `IEF`, `TLH`, and `TLT` are all Treasury-duration instruments, so the strategy is mostly timing interest-rate duration rather than diversifying across unrelated assets.
- The strategy is always fully invested in Treasuries. It can shorten duration into `IEI`, but it cannot move into a true cash/T-bill risk-off sleeve when the full Treasury curve is selling off.
- Momentum reacts late during sharp rate-regime changes. This was especially damaging during the 2022 bond bear market.
- `TLT` contributed very little but added meaningful risk: 0.39% contribution return versus -7.18% contribution max drawdown.
- Average duration of 7.26 remained too high for the rising-rate environment.

Current research judgment:

| Gate | Status | Reason |
| --- | --- | --- |
| Research readiness | Blocked | Needs benchmark, crisis-window, and longer-history validation. |
| Backtest validation | Failed | In-sample return is low and drawdown is too high. |
| Walk-forward validation | Failed | OOS compounded return and mean OOS Sharpe are negative. |
| Risk validation | Failed | No cash/T-bill escape mode and duration remains too high in rate shocks. |
| Reporting readiness | Improved | Rebalance-specific reporting is now available, but benchmark reports are still needed. |
| Paper trading gate | Blocked | Current configuration is not strong enough for paper trading. |
| Live trading gate | Blocked | No live broker path and no validated edge. |

Required next research:

1. Add a true defensive sleeve using `BIL`, `SHY`, `SGOV`, or a cash proxy.
2. Allow the portfolio to reduce exposure below `IEI` when Treasury momentum is broadly negative.
3. Test `TLT` caps at 25%, 20%, 15%, 10%, and 0%.
4. Add rate-shock filters such as 6-month/12-month positive momentum, 200-day moving average confirmation, or Treasury volatility thresholds.
5. Compare against simple benchmarks: 100% `IEI`, 100% `IEF`, 100% `TLH`, 100% `TLT`, equal-weight Treasuries, 60/20/10/10 duration blend, and 100% `BIL`/`SHY`/`SGOV`.
6. Add crisis-window analysis for Q4 2018, COVID 2020, the 2022 rate shock, the 2023 banking crisis, and major `SPY`/`QQQ` drawdown windows.
7. Re-run the research with `--period max` data where available, because the current 10-year sample misses 2008 and 2011.

### Paper Trade Results

- Status: not started.
- Requirement before live: run at least 2 weeks or 30 rebalance/order events, whichever is longer.

## Standard Reporting

- Strategy-level report module: `strategies.ConnorsResearchDynamicTreasuries.reporting`.
- Standard report function: `generate_dynamic_treasuries_report`.
- Default export root: `trade_results/reports/`.
- Per-run artifacts:
  - `report_data.csv`: equity, drawdown, and position timeline.
  - `trades.csv`: generic compatibility file; not the primary evaluation table for this strategy.
  - `trade_summary.csv`: generic compatibility summary; do not use win rate or closed-trade count to judge this rebalance strategy.
  - `rebalance_events.csv`: rebalance date, turnover, estimated fee, duration before/after, next-bar return, and allocation increases/decreases.
  - `rebalance_summary.csv`: rebalance count, average turnover, max turnover, estimated fees, average duration before/after, and average next-bar return.
  - `metrics.json`: backtest metrics.
  - `report.md`: human-readable report with metrics, rebalance summary, and strategy-specific reporting note.
  - `asset_performance.csv`: per-ETF exposure, contribution, Sharpe, and drawdown.
  - `target_weights.csv`: weekly target allocation matrix forward-filled to daily rows.
  - `execution_weights.csv`: one-bar delayed execution weights.
  - `duration_exposure.csv`: effective portfolio duration.
  - `momentum_returns.csv`: lookback return signals.
  - `positive_signal_counts.csv`: positive momentum vote counts.
  - `target_allocations.png`: allocation stack when charts are enabled.
  - `duration_exposure.png`: effective duration timeline when charts are enabled.
  - `asset_growth.png`: strategy growth versus ETFs when charts are enabled.
  - `asset_contribution.png`: per-ETF contribution chart when charts are enabled.
  - `asset_correlation.png`: ETF return correlation heatmap when charts are enabled.
- Research runner hook:
  - `scripts/run_dynamic_treasuries_research.py`.
  - Add `--walk-forward` for OOS validation.
  - Use `--skip-report-charts` for table-only report generation on machines without chart dependencies.

## Live Readiness

Current live status: blocked.

Latest local readiness output:

- Data coverage: complete for `IEI`, `IEF`, `TLH`, and `TLT`.
- Rows: 2,514.
- Blocker: missing broker symbol mapping for all four ETFs.

Live execution should be blocked until a broker adapter supplies:

- broker symbol mapping for `IEI`, `IEF`, `TLH`, and `TLT`
- latest daily OHLCV data
- portfolio holdings/current weights
- broker-specific ETF order sizing and cash/reconciliation checks
- journal and ledger writes based only on confirmed fills
