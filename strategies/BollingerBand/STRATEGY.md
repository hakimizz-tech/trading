# Strategy: Adaptive Bollinger Bands v1.0

## Overview

- **Asset class**: Liquid OHLCV-traded instruments supported by the data source and, for execution, MetaTrader 5 symbols available through aiomql.
- **Timeframe**: Primary M15 by default; configurable through `timeframe` and `interval`.
- **Style**: Hybrid mean reversion and breakout.
- **Lifecycle status**: Research and dry-run only. Not approved for live trading until the performance criteria and paper-trade gates below are met.
- **Edge hypothesis**: Prices alternate between ranging regimes, where Bollinger Band extremes can mean-revert, and volatility-compression regimes, where a Bollinger squeeze can precede directional expansion. RSI confirms exhaustion in mean-reversion regimes, while MACD confirms momentum in breakout regimes.

## Entry Rules

All entries use completed OHLCV bars. The canonical implementation lives in `strategies.BollingerBand.core.generate_adaptive_bollinger_signals`.
The adaptive engine supports three machine-testable modes:

- `adaptive`: hybrid mean-reversion plus breakout.
- `adaptive_mean_reversion`: mean-reversion entries/exits only.
- `adaptive_breakout`: squeeze-breakout entries/exits only.

### Shared Indicators

- Bollinger middle band: SMA(close, 20)
- Bollinger upper band: middle + 2.0 * population standard deviation(close, 20)
- Bollinger lower band: middle - 2.0 * population standard deviation(close, 20)
- Bandwidth: (upper - lower) / middle
- RSI: Wilder RSI(14)
- MACD: EMA(12) - EMA(26), signal line EMA(9)
- ATR: Wilder-style ATR(14) for stop and target distances

### Regime A: Mean Reversion

- Market condition: bandwidth is at or above the rolling `wide_quantile` threshold.
- Long entry:
  - Previous close < previous lower Bollinger Band.
  - Current close > current lower Bollinger Band.
  - RSI(14) < 30.
- Short entry:
  - Previous close > previous upper Bollinger Band.
  - Current close < current upper Bollinger Band.
  - RSI(14) > 70.

### Regime B: Squeeze Breakout

- Market condition: bandwidth recently touched or fell below the rolling `squeeze_quantile` threshold.
- Long entry:
  - Current close > upper Bollinger Band * (1 + breakout_buffer).
  - MACD crosses above MACD signal.
  - Optional volume confirmation passes when `require_volume_confirmation` is enabled.
- Short entry:
  - Current close < lower Bollinger Band * (1 - breakout_buffer).
  - MACD crosses below MACD signal.
  - Optional volume confirmation passes when `require_volume_confirmation` is enabled.

## Entry Execution

- Research execution: completed-bar signal, assumed filled at close in pandas backtests.
- vectorbt execution: `Portfolio.from_signals` with long and short entries/exits.
- aiomql execution: `strategies.BollingerBand.execution.aiomql_strategy.BollingerBandsAiomqlStrategy`.
- Live execution default: disabled with `live_trading = false`.
- Order type: aiomql `ScalpTrader.place_trade` using `OrderType.BUY` or `OrderType.SELL`.
- Audit rule: every executable signal is journaled before live order placement.

## Exit Rules

### Stop Loss

- Method: ATR-based.
- Parameters: default 2.0 * ATR(14) from entry.
- Long stop: entry - risk_per_unit.
- Short stop: entry + risk_per_unit.

### Take Profit

- Method: fixed risk multiple.
- Parameters: default 2.0R.
- Long target: entry + risk_per_unit * take_profit_rr.
- Short target: entry - risk_per_unit * take_profit_rr.

### Trailing Stop

- Method: ATR trailing stop.
- Parameters: default 2.5 * ATR(14).
- Activation: after price reaches at least 1.0R favorable movement.

### Time Stop

- Trigger: exit losing or flat trades after `max_hold_bars`, default 50 bars.
- Rationale: capital should not stay trapped in trades that do not revert or follow through.

### Signal Exit

- Mean-reversion long exit: close crosses back through the Bollinger middle band.
- Mean-reversion short exit: close crosses back through the Bollinger middle band.
- Breakout long exit: MACD crosses below signal.
- Breakout short exit: MACD crosses above signal.

### Exit Priority

1. Hard/ATR stop.
2. Take profit.
3. Signal exit.
4. Time stop.

## Position Sizing

- Research backtest: position is represented as full long, flat, or full short exposure in `position`.
- vectorbt default: `size = 0.95`, `size_type = "percent"`, configurable through `VectorBTBacktestConfig`.
- aiomql default: fixed volume `0.01` with optional broker-aware `use_risk_sizing`.
- Risk sizing: `execution.sizing.calculate_risk_position_size` sizes volume from account equity, stop distance, pip value, lot limits, volume step, and `risk_per_trade`.
- Required before live scaling: validate broker pip value, lot constraints, and free-margin behavior on Windows/demo MT5.
- Max position: one open position per strategy-symbol by default.

## Risk Parameters

- Risk per trade: default 1%, allowed range `(0, 5%]` in execution gate.
- Max open positions: default 1 per configured strategy-symbol.
- Stop-loss required: execution gate requires positive `stop_loss_pips`.
- Take-profit/risk multiple required: execution gate requires positive `take_profit_rr`.
- Live mode: opt-in only through config.
- Journal rule: live orders are blocked if journaling fails.
- Accounting rule: only confirmed fills and exits should be posted to the double-entry ledger.
- Live execution gate: broker snapshot now feeds spread checks, max open positions, max daily loss, and optional risk-based position sizing.
- Confirmed-fill accounting: broker close events with realized P&L are posted to the double-entry ledger through `record_broker_fill`.
- Live execution blocker: broker snapshot extraction, risk sizing, and confirmed-fill accounting are implemented but must pass Windows/demo MT5 validation before `live_trading` can be enabled.
- Pure-Python foundation:
  - `execution.state` defines normalized account, contract, spread, and open-position snapshots.
  - `execution.sizing` defines fixed-fractional broker-aware lot sizing.
  - `accounting.TradeLedger.record_position_close` posts confirmed MT5/CFD realized P&L, commission, and swap with idempotency by broker external id.
  - Journal statuses are standardized as `signal`, `blocked`, `submitted`, `filled`, `partially_filled`, `closed`, `rejected`, and `error`.

## Filters

### Market Filters

- Regime filter: adaptive bandwidth classifies mean-reversion, squeeze, breakout, or neutral conditions.
- Volatility filter: mean reversion only fires in wide-bandwidth regimes; breakout only fires after squeeze conditions.
- Momentum filter: breakout requires MACD confirmation.
- Volume filter: optional breakout volume confirmation using volume above rolling baseline.
- Spread filter: optional `max_spread` blocks entries when a `spread` column is present and exceeds the configured threshold.
- Session filter: optional `session_start` and `session_end` block entries outside the configured time window.

### Instrument Filters

- Required OHLCV columns: open, high, low, close, volume.
- Execution symbols must be available in MetaTrader 5 through the configured broker.
- Spread filtering requires a `spread` column in research data; the current local CSV datasets do not include spread.
- aiomql candle normalization preserves broker `spread` when returned by MT5 rates.

### Time Filters

- aiomql supports session injection via `sessions`.
- Default research config does not restrict trading hours.
- Session-filtered research runs can set `session_start` and `session_end`.
- Recommended before production: configure active sessions and block major illiquidity windows.

## Performance Criteria

### Continue Research

- Minimum backtest trade count: 100 trades for mean reversion and breakout evaluation.
- Out-of-sample Sharpe: > 1.0.
- Profit factor: > 1.5.
- Max drawdown: < 15% for mean reversion, < 20% for breakout.
- Mean-reversion win rate: > 55%.
- Breakout win rate: > 35% with average win / average loss > 2.0.

### Review Required

- Any core metric degrades more than 25% from baseline.
- Three consecutive losing weeks in paper trading.
- Live or paper results differ from out-of-sample results by more than 25%.
- Regime classification produces mostly neutral/no-trade output for the target market.

### Retire Strategy

- Rolling 30-day Sharpe < 0 for two consecutive weeks.
- Three consecutive losing months.
- Max drawdown halt is triggered twice in 30 days.
- Market regime shifts so Bollinger squeeze/bounce behavior no longer appears in out-of-sample data.

## Backtest Results

### In-Sample

- Status: baseline populated from local daily datasets on 2026-06-17.
- Command:
  - `./.venv/bin/python scripts/run_bollinger_research.py --tail 2500 --train-size 1000 --test-size 500 --step-size 500 --purge-size 5 --embargo-size 5`
- Assumptions:
  - vectorbt backend.
  - Initial cash: 10,000.
  - Fees: 0.02% per side.
  - Slippage: 0.01% per side.
  - Position size: 95% of equity.
  - Adaptive Bollinger default configuration with ATR exit plan defaults.
- Results:

| Dataset | Period | Rows | Total Return | Sharpe | Max Drawdown | Win Rate | Profit Factor | Trades |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GBPUSD D1 | 2013-10-14 to 2023-06-08 | 2,500 | 11.33% | 0.484 | -5.22% | 54.84% | 1.593 | 31 |
| EURUSD D1 | 2015-07-27 to 2025-02-21 | 2,500 | 14.37% | 0.674 | -6.03% | 59.38% | 2.095 | 32 |
| XAUUSD D1 | 2016-04-15 to 2026-01-30 | 2,500 | -4.91% | -0.044 | -18.93% | 52.50% | 0.904 | 40 |
- Stored outputs:
  - `trade_results/research/bollinger_research_summary.csv`
  - `trade_results/research/bollinger_research_summary.md`

### Out-of-Sample

- Status: baseline walk-forward populated from the same local daily datasets on 2026-06-17.
- Method:
  - Rolling windows.
  - Train size: 1,000 bars.
  - Purge: 5 bars.
  - Embargo: 5 bars.
  - Test size: 500 bars.
  - Step size: 500 bars.
  - Per-fold optimization grid: `bb_window` in `[20, 30]`, `bb_num_std = 2.0`, `wide_quantile` in `[0.55, 0.60]`, `squeeze_quantile = 0.20`.
- Results:

| Dataset | Folds | Mean OOS Return | Mean OOS Sharpe | Worst OOS Drawdown | OOS Trades | Profitable Folds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GBPUSD D1 | 2 | 0.34% | 0.200 | -3.42% | 13 | 1 |
| EURUSD D1 | 2 | 1.16% | 0.209 | -3.20% | 14 | 1 |
| XAUUSD D1 | 2 | 2.28% | 0.322 | -5.04% | 10 | 1 |
- Fold outputs:
  - `trade_results/research/GBPUSD_D1_walk_forward.csv`
  - `trade_results/research/EURUSD_1d_walk_forward.csv`
  - `trade_results/research/XAUUSD_1D_walk_forward.csv`
- Interpretation:
  - These are initial baselines only. OOS trade counts are below the 100-trade research threshold, so the strategy remains research/dry-run only.
  - The daily datasets do not validate the M15 default execution timeframe. M15/H1 walk-forward runs are still required before paper trading.

### Intraday Validation

- Status: initial M15/H1 validation populated from local datasets on 2026-06-17.
- Command:
  - `./.venv/bin/python scripts/run_bollinger_research.py datasets/GBPUSD/GBPUSD_PERIOD_M15.csv datasets/xauusd/XAU_1h_data.csv --summary-name bollinger_intraday_research_summary --tail 20000 --train-size 10000 --test-size 2500 --step-size 2500 --purge-size 96 --embargo-size 96 --freq auto`
- Method:
  - Recent 20,000 bars per dataset.
  - Rolling train windows of 10,000 bars.
  - Purge: 96 bars.
  - Embargo: 96 bars.
  - Test windows of 2,500 bars.
  - Per-fold optimization grid: `bb_window` in `[20, 30]`, `bb_num_std = 2.0`, `wide_quantile` in `[0.55, 0.60]`, `squeeze_quantile = 0.20`.
- Results:

| Dataset | Period | Rows | Single Return | Single Sharpe | Single Drawdown | Single Trades | Folds | Mean OOS Return | Mean OOS Sharpe | Worst OOS Drawdown | OOS Trades | Profitable Folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GBPUSD M15 | 2022-08-17 22:00 to 2023-06-08 10:00 | 20,000 | -12.02% | -4.707 | -12.08% | 207 | 3 | -2.14% | -9.169 | -3.37% | 71 | 0 |
| XAUUSD H1 | 2022-08-02 15:00 to 2026-01-30 23:00 | 20,000 | -8.91% | -0.101 | -20.48% | 283 | 3 | -5.67% | -0.567 | -11.14% | 97 | 0 |
- Stored outputs:
  - `trade_results/research/bollinger_intraday_research_summary.csv`
  - `trade_results/research/bollinger_intraday_research_summary.md`
  - `trade_results/research/GBPUSD_M15_walk_forward.csv`
  - `trade_results/research/XAUUSD_1H_walk_forward.csv`
- Interpretation:
  - The current adaptive parameter family fails the default M15-style validation.
  - Do not move to paper trading with this configuration.
  - Required next research step: isolate mean-reversion and breakout sub-regimes, add spread/session filters, and re-run walk-forward validation before checklisting for paper deployment.

### Split-Regime Intraday Validation

- Status: populated on 2026-06-17 after splitting the hybrid engine into mean-reversion-only and breakout-only modes.
- Session filter:
  - `session_start = 07:00`
  - `session_end = 17:00`
- Spread filter:
  - Implemented in code through `AdaptiveRegimeConfig.max_spread`.
  - Not applied to these research runs because the local GBPUSD/XAUUSD CSV files do not include a `spread` column.
- Mean-reversion command:
  - `./.venv/bin/python scripts/run_bollinger_research.py datasets/GBPUSD/GBPUSD_PERIOD_M15.csv datasets/xauusd/XAU_1h_data.csv --strategy adaptive_mean_reversion --summary-name bollinger_intraday_mean_reversion_session_summary --tail 20000 --train-size 10000 --test-size 2500 --step-size 2500 --purge-size 96 --embargo-size 96 --freq auto --session-start 07:00 --session-end 17:00`
- Breakout command:
  - `./.venv/bin/python scripts/run_bollinger_research.py datasets/GBPUSD/GBPUSD_PERIOD_M15.csv datasets/xauusd/XAU_1h_data.csv --strategy adaptive_breakout --summary-name bollinger_intraday_breakout_session_summary --tail 20000 --train-size 10000 --test-size 2500 --step-size 2500 --purge-size 96 --embargo-size 96 --freq auto --session-start 07:00 --session-end 17:00`
- Results:

| Strategy | Dataset | Single Return | Single Sharpe | Single Drawdown | Single Trades | Mean OOS Return | Mean OOS Sharpe | Worst OOS Drawdown | OOS Trades | Profitable Folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mean Reversion | GBPUSD M15 | -6.34% | -3.091 | -7.17% | 78 | -0.67% | -3.845 | -1.68% | 20 | 1/3 |
| Mean Reversion | XAUUSD H1 | -11.75% | -0.311 | -13.56% | 56 | -1.15% | -0.336 | -3.29% | 19 | 0/3 |
| Breakout | GBPUSD M15 | -2.86% | -2.169 | -3.46% | 58 | -0.48% | -3.932 | -1.09% | 18 | 0/3 |
| Breakout | XAUUSD H1 | 3.24% | 0.078 | -5.21% | 107 | 0.19% | -0.008 | -2.30% | 38 | 2/3 |
- Stored outputs:
  - `trade_results/research/bollinger_intraday_mean_reversion_session_summary.csv`
  - `trade_results/research/bollinger_intraday_breakout_session_summary.csv`
  - `trade_results/research/GBPUSD_M15_adaptive_mean_reversion_walk_forward.csv`
  - `trade_results/research/GBPUSD_M15_adaptive_breakout_walk_forward.csv`
  - `trade_results/research/XAUUSD_1H_adaptive_mean_reversion_walk_forward.csv`
  - `trade_results/research/XAUUSD_1H_adaptive_breakout_walk_forward.csv`
- Interpretation:
  - Mean reversion remains weak on both tested intraday datasets.
  - Breakout-only improves XAUUSD H1 and is the only tested split with positive single-period and mean OOS return, but OOS Sharpe is still approximately flat and trade count is below threshold.
  - GBPUSD M15 remains unsuitable under these rules.
  - Next research should focus on XAUUSD H1 breakout filters: volume confirmation, stronger breakout buffer, trend/session segmentation, and real spread-aware filtering.

### Paper Trade Results

- Status: not started.
- Requirement before live: run at least 2 weeks or 30 trades, whichever is longer.

## Standard Reporting

- Strategy-level report module: `strategies.BollingerBand.reporting`.
- Standard report function: `generate_bollinger_strategy_report`.
- Default export root: `trade_results/reports/`.
- Per-run artifacts:
  - `report_data.csv`: OHLCV, Bollinger bands, equity, drawdown, and position timeline.
  - `trades.csv`: normalized entry/exit trade table.
  - `trade_summary.csv`: closed-trade count, win/loss count, win rate, P&L, and return summary.
  - `metrics.json`: backtest engine metrics.
  - `report.md`: human-readable report index.
  - `price_bollinger_trades.png`: close price, Bollinger bands, entries, and exits when charts are enabled.
  - `equity_drawdown.png`: equity curve and drawdown when charts are enabled.
- Research runner hook:
  - Add `--generate-reports` to `scripts/run_bollinger_research.py` to create per-dataset reports.
  - Use `--skip-report-charts` for table-only report generation on machines without chart dependencies.

## Actionable Checklist

### Research Readiness

- [x] Strategy rules documented with explicit mean-reversion and breakout sub-regimes.
- [x] Indicators, entries, exits, spread filters, and session filters are implemented in pure Python.
- [x] Local datasets are normalized through `strategies.BollingerBand.research.datasets`.
- [x] Standard strategy report export exists under `trade_results/reports/`.
- [ ] Add spread-bearing MT5/demo datasets for realistic spread-filter research.

### Backtest Validation

- [x] vectorbt adapter supports long/short entries, exits, stops, fees, slippage, and metrics.
- [x] Walk-forward validation runs with train/test splits, purge, embargo, and parameter selection.
- [x] Daily and intraday baseline metrics are recorded in this document.
- [ ] Re-run XAUUSD H1 breakout research with volume confirmation, breakout buffer grid, and session segmentation.
- [ ] Promote only configurations that meet minimum trade count, OOS Sharpe, drawdown, and profit-factor gates.

### Risk Validation

- [x] Broker/account snapshot model is independent of aiomql and unit-testable on Linux.
- [x] Broker-aware position sizing uses equity, risk per trade, stop distance, pip value, and lot constraints.
- [x] Live execution gate checks max spread, max open positions, max daily loss, and final volume.
- [ ] Validate pip value, point size, lot step, and free-margin behavior against Windows/demo MT5 broker data.
- [ ] Add scenario tests for max daily loss using confirmed broker P&L from demo fills.

### Execution Readiness

- [x] aiomql adapter remains import-guarded for Linux research and Windows execution.
- [x] Live trading is opt-in only through `live_trading`.
- [x] Order attempts are journaled before live placement.
- [ ] Confirm broker open-position inspection against real aiomql/MT5 position objects.
- [ ] Run paper execution on Windows/demo MT5 before enabling live trading.

### Journal/Accounting Readiness

- [x] Journal statuses are standardized: `signal`, `blocked`, `submitted`, `filled`, `partially_filled`, `closed`, `rejected`, `error`.
- [x] Ledger posts MT5/CFD-style realized P&L, commission, and swap for confirmed broker closes.
- [x] Ledger posting is idempotent by broker external id.
- [x] Reconciliation script exists for journal, ledger, and broker records.
- [ ] Reconcile demo broker deal history against journal and ledger after paper trading starts.

### Paper Trading Gate

- [ ] Use only a configuration that passes walk-forward validation thresholds.
- [ ] Run at least 2 weeks or 30 trades, whichever is longer.
- [ ] Confirm fills, exits, journal records, ledger records, and reconciliation match broker history.
- [ ] Paper drawdown and slippage must stay within 25% of validated out-of-sample assumptions.

### Live Trading Gate

- [ ] Paper trading gate complete.
- [ ] Windows/demo MT5 validation complete for broker snapshot, sizing, spread, open positions, and confirmed-fill accounting.
- [ ] `live_trading` remains disabled until journal, ledger, and max-loss controls are verified in the deployment environment.
- [ ] Start with minimum broker volume and hard daily loss limits.

## Dependencies

- Data: standard OHLCV DataFrame for research; aiomql `ForexSymbol.copy_rates_from_pos` for MT5 execution.
- Indicators: pandas/numpy by default; optional TA-Lib acceleration for RSI and MACD.
- Backtesting: pandas research backtest and optional vectorbt adapter.
- Execution: aiomql on Windows with MetaTrader 5.
- Persistence: SQLAlchemy-backed trade journal and double-entry accounting ledger, defaulting to local SQLite paths.
- Visualization: shared `visualization` package.

## Notes

- This document defines the adaptive strategy as a single hybrid strategy with two explicit sub-regimes.
- The simpler `mean_reversion`, `bbma`, and `bb_rsi` modes are research variants and should receive their own strategy definition document if promoted to production.
- Parameter optimization is research-only. Use walk-forward validation before adopting optimized parameters.

## Change Log

- **v1.2** 2026-06-17: Added standard strategy reporting exports and converted readiness notes into actionable research, validation, execution, journal/accounting, paper, and live gates.
- **v1.1** 2026-06-17: Added split adaptive sub-regimes plus spread/session entry filters; populated session-filtered intraday split-regime validation.
- **v1.0** 2026-06-17: Initial framework definition for the adaptive Bollinger Bands strategy.
