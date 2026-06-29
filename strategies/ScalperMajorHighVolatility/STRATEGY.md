# Scalper Major High Volatility

## Identity

- Source: `A Computational Solution for Automated Trading in High Volatility Environments.md`
- Asset class: Forex first, compatible with any canonical OHLCV market data
- Timeframes: M1, M5, M15, M30, H1, H4, D1
- Style: short-term RSI/SMA exhaustion with Marubozu confirmation
- Status: research only

## Research Hypothesis

High-volatility forex environments create repeated overextension events. When price
is far from SMA-20, RSI is extreme, and the candle forms a Marubozu exhaustion
pattern, the next move has enough mean-reversion tendency to support a scalping
strategy if risk and drawdown are tightly controlled.

## Implemented Rules

Long setup:

- RSI below 30.
- Close below SMA-20 by at least a configurable ATR-normalized distance.
- Bearish Marubozu candle confirms capitulation/exhaustion.

Short setup:

- RSI above 70.
- Close above SMA-20 by at least a configurable ATR-normalized distance.
- Bullish Marubozu candle confirms exhaustion.

Exits:

- RSI reverts through the configured midline.
- Opposite signal appears.
- ATR stop-loss.
- ATR take-profit.
- Time stop after a configurable number of bars.

Risk and sizing:

- Position size is capped by ATR stop distance and `risk_fraction`.
- Global drawdown can block new entries.
- The paper's paired recovery lot sequence is implemented as a helper:
  `0.01, 0.01, 0.02, 0.02, 0.04, 0.04...`.
- The paper's progressive lot-sizing equation is implemented as
  `progressive_lot_size(...)`.

## Important Approximation

The original paper uses an MT5 Expert Advisor with broker execution, margin,
free-margin checks, grid recovery, and paired martingale behavior. This module does
not enable live grid/martingale execution. It exposes those mechanics as research
helpers only. Live execution requires broker-aware margin gates, confirmed-fill
accounting, max-loss controls, and paper trading validation.

## Implementation Audit

Status after rereading the paper:

| Paper Component | Implementation Status | Notes |
| --- | --- | --- |
| H1/new-candle signal processing | Partially implemented | Code supports any OHLCV timeframe. Research report below is D1 because current local datasets are D1 only. |
| RSI threshold heuristic | Implemented | Buy when RSI < 30, sell/short when RSI > 70. |
| SMA-20 distance heuristic | Implemented | Uses ATR-normalized distance from SMA-20 instead of an undefined absolute "significant distance". |
| Marubozu confirmation | Implemented | Uses TA-Lib `CDLMARUBOZU` when available and also applies explicit body/wick rules matching the paper's description. |
| TA-Lib indicator backend | Implemented | Uses TA-Lib RSI, SMA, ATR, and Marubozu detection when `talib` is installed; falls back to pandas otherwise. |
| Risk Manager drawdown gate | Partially implemented | Global drawdown blocks new entries. Per-symbol floating drawdown is documented but not fully meaningful in the single-symbol research backtest. |
| Capital Manager progressive lot sizing | Implemented as helper | `progressive_lot_size(...)` implements the paper's equations. |
| Grid recovery with paired martingale | Research simulator implemented | `recovery_lot_sequence(...)` implements `0.01, 0.01, 0.02, 0.02...`; `backtest_scalper_major_recovery(...)` simulates basket recovery. Live/grid execution is still disabled. |
| Max 14 positions per asset/direction | Research simulator implemented | `RecoveryConfig.max_positions_per_direction` defaults to 14 and can be reduced for safer stress tests. |
| Winning basket profit target 3x losing basket loss | Research simulator implemented | `RecoveryConfig.profit_to_loss_ratio` defaults to 3.0. Requires further broker-aware validation before paper/live use. |
| MT5 execution delay, commission per lot, margin/free-margin model | Not fully implemented | Research backtest uses proportional fees/slippage. Live replication requires MT5/aiomql broker simulation. |

Conclusion: the current module is a practical, testable research translation of the signal logic and metrics, not a full reproduction of the paper's MT5 Expert Advisor.

## Evaluation Metrics

The module reports the paper's core evaluation family:

- cumulative/total return
- annualized return
- maximum drawdown
- Sharpe ratio
- profit factor
- expected payoff
- recovery factor
- win rate
- trade count

## Standard Reporting

- Strategy-level report module: `strategies.ScalperMajorHighVolatility.reporting`.
- Standard report function: `generate_scalper_major_report`.
- Default export root: `trade_results/reports/`.
- Report artifacts include:
  - `report_data.csv`: OHLCV, SMA, RSI, ATR, equity, drawdown, position timeline, and signal columns.
  - `trades.csv`: normalized entry/exit trade events.
  - `trade_summary.csv`: closed-trade summary.
  - `metrics.json`: strategy metrics.
  - `report.md`: report index.
  - `price_sma_trades.png`: price, SMA-20, and trade markers when chart rendering is enabled.
  - `equity_drawdown.png`: equity and drawdown when chart rendering is enabled.
- Research runner hook:
  - Add `--generate-reports` to `scripts/run_scalper_major_research.py`.
  - Use `--skip-report-charts` for table-only reports when chart dependencies or display permissions are unavailable.

## Recovery Research Mode

- Basket recovery module: `strategies.ScalperMajorHighVolatility.recovery`.
- Entry point: `backtest_scalper_major_recovery`.
- Configuration: `RecoveryConfig`.
- Research runner mode:
  - `--mode signal_only` uses the original one-position signal translation.
  - `--mode basket_recovery` uses the paper-style recovery simulator.
- Basket recovery walk-forward is intentionally not enabled yet; it needs recovery-aware folds so results are not confused with signal-only walk-forward.

## aiomql Execution Adapter

- Adapter module: `strategies.ScalperMajorHighVolatility.execution.aiomql_strategy`.
- Adapter class: `ScalperMajorAiomqlStrategy`.
- Default mode: dry-run. `live_trading` remains `False` unless explicitly enabled in bot configuration.
- Signal cadence: newly closed H1 candle by default.
- Signal source: shared Scalper Major RSI/SMA-20/Marubozu logic.
- Execution safety:
  - Uses `AiomqlStrategyBase`.
  - Reuses shared journal and ledger hooks.
  - Reuses broker snapshot gates.
  - Reuses spread, max-open-position, daily-loss, and risk-sizing gates.
  - Emits basket-recovery metadata but does not yet place live recovery grid orders.
- Live recovery trading remains blocked until:
  - broker position inspection is verified on Windows/demo MT5.
  - recovery basket state is rebuilt from confirmed broker positions.
  - recovery-aware journal and ledger reconciliation is tested.
  - max recovery depth is reduced and stress-tested before any 14-level configuration.

## Validation Plan

1. Load clean OHLCV datasets from M1 through D1.
2. Resample lower timeframe data with `resample_ohlcv_timeframes`.
3. Run single-period backtests per symbol/timeframe.
4. Run chronological walk-forward validation.
5. Compare results against the paper's reported metrics.
6. Keep the strategy research-only until out-of-sample metrics exceed project
   thresholds and live execution gates are implemented.

## Backtest Results

### D1 Baseline Across Local Datasets

- Status: baseline populated from local D1 datasets on 2026-06-23.
- Backend: TA-Lib was available in `.venv` and used for RSI, SMA, ATR, and Marubozu detection.
- Command shape:
  - load each dataset with `market_data.ohlcv.load_ohlcv_csv`
  - run `backtest_scalper_major(...)` with default research config
  - initial cash: 20,000
  - risk fraction: 1% per trade
  - stop: 1.5 ATR
  - take profit: 1.0 ATR
  - max holding bars: 12
  - fees/slippage: proportional research assumptions, not broker lot commission

| Dataset | Asset Class | TF | Period | Rows | Total Return | Ann. Return | Sharpe | Max DD | Profit Factor | Win Rate | Trades |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | Forex | D1 | 2020-01-01 to 2023-12-29 | 1,250 | 2.66% | 0.53% | 0.328 | -2.04% | 1.464 | 64.71% | 17 |
| GBPUSD | Forex | D1 | 2020-01-01 to 2023-12-29 | 1,249 | -4.94% | -1.02% | -0.418 | -6.82% | 0.603 | 56.25% | 16 |
| USDCAD | Forex | D1 | 2020-01-01 to 2023-12-29 | 1,250 | 0.48% | 0.10% | 0.065 | -4.05% | 1.115 | 62.50% | 16 |
| USDCHF | Forex | D1 | 2020-01-01 to 2023-12-29 | 1,250 | -9.24% | -1.94% | -0.988 | -9.24% | 0.274 | 33.33% | 15 |
| AUDUSD | Forex | D1 | 2020-01-01 to 2023-12-29 | 1,250 | 7.97% | 1.56% | 0.748 | -2.04% | 3.174 | 81.25% | 16 |
| USDJPY | Forex | D1 | 2020-01-01 to 2023-12-29 | 1,250 | 0.04% | 0.01% | 0.014 | -5.54% | 1.004 | 52.63% | 19 |
| SPY | Stock/ETF | D1 | 2016-06-20 to 2026-06-18 | 2,514 | 0.64% | 0.06% | 0.040 | -6.85% | 1.035 | 54.29% | 35 |
| QQQ | Stock/ETF | D1 | 2016-06-20 to 2026-06-18 | 2,514 | -6.80% | -0.70% | -0.274 | -10.62% | 0.693 | 44.12% | 34 |
| AAPL | Stock | D1 | 2016-06-20 to 2026-06-18 | 2,514 | -25.13% | -2.86% | -1.017 | -25.17% | 0.314 | 34.04% | 47 |
| MSFT | Stock | D1 | 2016-06-20 to 2026-06-18 | 2,514 | 2.19% | 0.22% | 0.111 | -7.87% | 1.134 | 54.55% | 33 |
| NVDA | Stock | D1 | 2016-06-20 to 2026-06-18 | 2,514 | 7.44% | 0.72% | 0.336 | -6.93% | 1.473 | 64.86% | 37 |

### Interpretation

- The D1 research translation does not reproduce the paper's reported EA performance.
- AUDUSD D1 is the strongest local baseline in this first pass, with 7.97% total return, 0.748 Sharpe, -2.04% max drawdown, and 3.174 profit factor.
- EURUSD and USDCAD are mildly positive but low Sharpe.
- GBPUSD, USDCHF, QQQ, and AAPL are weak under this D1 configuration.
- Stock/ETF results are mixed, which is expected because the paper is forex-first and scalping-oriented.
- Trade counts are far below the paper's 11,571 trades because current local validation is D1 only and the full grid/recovery engine is intentionally not enabled.

### Intraday Validation

- Status: populated from local Dukascopy forex datasets on 2026-06-23.
- Backend: TA-Lib was used for RSI, SMA, ATR, and Marubozu detection.
- Commands:
  - `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python scripts/run_scalper_major_research.py --symbols EURUSD GBPUSD USDCAD USDCHF --timeframes h1 --name scalper_major_h1_research --output-dir trade_results/research`
  - `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python scripts/run_scalper_major_research.py --symbols EURUSD GBPUSD USDCAD USDCHF --timeframes m30 --name scalper_major_m30_research --output-dir trade_results/research`
  - `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python scripts/run_scalper_major_research.py --symbols EURUSD GBPUSD USDCAD USDCHF --timeframes m15 --name scalper_major_m15_research --output-dir trade_results/research`
  - `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python scripts/run_scalper_major_research.py --symbols EURUSD GBPUSD --timeframes m5 --name scalper_major_m5_research --output-dir trade_results/research`
  - `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python scripts/run_scalper_major_research.py --symbols EURUSD GBPUSD USDCAD USDCHF --timeframes d1 --name scalper_major_d1_research --output-dir trade_results/research`
- Assumptions:
  - Initial cash: 20,000.
  - Risk fraction: 1% per trade.
  - Stop: 1.5 ATR.
  - Take profit: 1.0 ATR.
  - Max holding bars: 12.
  - Costs: proportional research fees/slippage, not broker lot commission.
  - Grid/martingale recovery remains disabled.

#### H1 Results

| Symbol | Period | Rows | Return | Sharpe | Max DD | Profit Factor | Win Rate | Trades | OOS Return | OOS Sharpe | OOS Trades | Profitable Folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 2020-01-01 to 2023-12-29 | 24,954 | -4.90% | -0.101 | -5.48% | 0.862 | 51.83% | 301 | -2.70% | -0.046 | 261 | 23/45 |
| GBPUSD | 2020-01-01 to 2023-12-29 | 24,952 | 9.87% | 0.174 | -4.57% | 1.257 | 57.86% | 318 | 7.22% | 0.060 | 276 | 26/45 |
| USDCAD | 2020-01-01 to 2023-12-29 | 24,953 | -5.96% | -0.147 | -9.43% | 0.824 | 50.99% | 304 | -7.74% | -0.156 | 275 | 20/45 |
| USDCHF | 2020-01-01 to 2023-12-29 | 24,947 | -2.67% | -0.058 | -4.40% | 0.919 | 55.44% | 285 | -0.99% | 0.037 | 251 | 25/45 |

#### M30 Results

| Symbol | Period | Rows | Return | Sharpe | Max DD | Profit Factor | Win Rate | Trades | OOS Return | OOS Sharpe | OOS Trades | Profitable Folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 2020-01-01 to 2023-12-29 | 49,910 | -1.36% | -0.019 | -4.97% | 0.970 | 58.55% | 579 | 0.68% | 0.054 | 538 | 31/62 |
| GBPUSD | 2020-01-01 to 2023-12-29 | 37,424 | -5.53% | -0.102 | -6.86% | 0.867 | 55.63% | 462 | -3.25% | -0.031 | 411 | 18/45 |
| USDCAD | 2020-01-01 to 2022-12-30 | 37,458 | -6.13% | -0.121 | -8.54% | 0.844 | 55.12% | 488 | -4.69% | -0.081 | 452 | 18/45 |
| USDCHF | 2020-01-01 to 2022-12-30 | 37,450 | 7.37% | 0.144 | -2.12% | 1.232 | 63.15% | 445 | 6.92% | 0.209 | 406 | 27/45 |

#### M15 Results

| Symbol | Period | Rows | Return | Sharpe | Max DD | Profit Factor | Win Rate | Trades | OOS Return | OOS Sharpe | OOS Trades | Profitable Folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 2020-01-01 to 2023-12-29 | 99,817 | -9.20% | -0.104 | -11.75% | 0.860 | 59.53% | 1,139 | -8.57% | -0.070 | 1,077 | 38/95 |
| GBPUSD | 2020-01-01 to 2023-12-29 | 99,805 | -4.19% | -0.030 | -7.76% | 0.946 | 59.66% | 1,113 | -4.21% | 0.013 | 1,057 | 48/95 |
| USDCAD | 2020-01-01 to 2023-12-29 | 74,846 | -9.46% | -0.146 | -9.75% | 0.814 | 55.29% | 926 | -8.99% | -0.148 | 869 | 28/70 |
| USDCHF | 2020-01-01 to 2023-12-29 | 99,745 | -0.13% | -0.000 | -4.93% | 0.998 | 59.46% | 1,189 | -0.22% | 0.057 | 1,134 | 51/95 |

#### M5 Results

| Symbol | Period | Rows | Return | Sharpe | Max DD | Profit Factor | Win Rate | Trades | OOS Return | OOS Sharpe | OOS Trades | Profitable Folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 2023-01-01 to 2023-09-29 | 56,127 | -3.86% | -0.136 | -5.35% | 0.813 | 60.00% | 685 | -3.74% | -0.125 | 609 | 8/24 |
| GBPUSD | 2023-01-01 to 2023-12-29 | 55,933 | -5.28% | -0.170 | -6.06% | 0.765 | 59.28% | 614 | -3.73% | -0.150 | 525 | 9/23 |

#### D1 Forex Re-Run

| Symbol | Period | Rows | Return | Sharpe | Max DD | Profit Factor | Win Rate | Trades | OOS Return | OOS Sharpe | OOS Trades | Profitable Folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 2020-01-01 to 2023-12-29 | 1,250 | 2.66% | 0.328 | -2.04% | 1.464 | 64.71% | 17 | -1.09% | -0.588 | 6 | 1/2 |
| GBPUSD | 2020-01-01 to 2023-12-29 | 1,249 | -4.94% | -0.418 | -6.82% | 0.603 | 56.25% | 16 | -0.96% | -0.298 | 2 | 0/1 |
| USDCAD | 2020-01-01 to 2023-12-29 | 1,250 | 0.48% | 0.065 | -4.05% | 1.115 | 62.50% | 16 | 0.02% | 0.058 | 5 | 1/2 |
| USDCHF | 2020-01-01 to 2023-12-29 | 1,250 | -9.24% | -0.988 | -9.24% | 0.274 | 33.33% | 15 | -3.35% | -0.053 | 6 | 1/2 |

Stored outputs:

- `trade_results/research/scalper_major_h1_research_summary.csv`
- `trade_results/research/scalper_major_h1_research_summary.md`
- `trade_results/research/scalper_major_m30_research_summary.csv`
- `trade_results/research/scalper_major_m30_research_summary.md`
- `trade_results/research/scalper_major_m15_research_summary.csv`
- `trade_results/research/scalper_major_m15_research_summary.md`
- `trade_results/research/scalper_major_m5_research_summary.csv`
- `trade_results/research/scalper_major_m5_research_summary.md`
- `trade_results/research/scalper_major_d1_research_summary.csv`
- `trade_results/research/scalper_major_d1_research_summary.md`

### Intraday Interpretation

- This research translation still does not reproduce the paper's reported MT5 Expert Advisor performance.
- GBPUSD H1 is the strongest H1 candidate, with 9.87% single-period return and 7.22% compounded OOS return, but Sharpe remains low at 0.174 single-period and 0.060 OOS.
- USDCHF M30 is the strongest split, with 7.37% single-period return, 6.92% compounded OOS return, 1.232 profit factor, and shallow -2.12% max drawdown.
- M15 and M5 are not acceptable under the current rules. They generate many trades but negative return and weak OOS performance.
- Win rates near 55-63% are not enough to overcome costs and average loss size on most symbols/timeframes.
- M1 validation is still absent because no M1 CSV outputs were included in this completed run.
- The strategy remains research-only. Before any paper/live path, the next research pass should test session filters, spread filters, broker lot commission modeling, and a controlled basket/grid simulator if we decide to approximate the paper's recovery engine.

### Paper Replication Gap

The current implementation is not a full reproduction of the paper's MT5 Expert
Advisor. It is a safer research translation of the entry signal with conventional
ATR/RSI/time exits.

Key differences from the paper:

| Component | Current Status | Replication Gap |
| --- | --- | --- |
| H1 signal processor | Partially implemented | Code supports H1, but also evaluates other timeframes. A paper-exact run should use only newly closed H1 candles. |
| Risk manager | Partially implemented | Global drawdown blocks entries, but broker margin/free-margin and per-asset floating drawdown are not fully simulated. |
| Capital manager | Helper only | Progressive lot sizing exists, but the default backtest uses fixed fractional risk sizing. |
| Grid recovery | Research simulator implemented | Paired martingale sequence exists and can now be exercised through `backtest_scalper_major_recovery(...)`. |
| Basket logic | Research simulator implemented | The simulator supports up to 14 positions per direction by default through `RecoveryConfig.max_positions_per_direction`. |
| 3x winning-basket target | Research simulator implemented | The simulator closes baskets when winning-side profit reaches `RecoveryConfig.profit_to_loss_ratio` times losing-side loss. |
| Broker execution model | Not fully implemented | Current research uses proportional fees/slippage, not MT5 lot commission, spread, swap, margin, free margin, or execution delay. |

Interpretation:

- The raw RSI/SMA/Marubozu signal is not strong enough by itself across the tested data.
- The paper's reported performance likely depends heavily on the recovery and money-management layer.
- That layer may smooth backtests, but it also adds hidden tail risk, margin pressure, and possible account failure during persistent one-way trends.

### Next Research Gates

Before this strategy can move beyond research-only status:

1. Reproduce the paper-exact setup:
   - H1 only.
   - EURUSD, GBPUSD, USDCAD, and USDCHF.
   - 2016-01-01 to 2023-12-31.
   - MT5-quality bid/ask or tick/spread data.
   - $7 commission per lot.
   - 50 ms execution delay assumption.
   - swap assumptions documented explicitly.
2. Separate signal edge from recovery edge:
   - Run signal-only fixed-risk tests.
   - Run signal plus progressive lot sizing.
   - Run signal plus full grid/martingale basket recovery.
3. Add a broker-aware simulator:
   - margin and free margin.
   - leverage and contract size.
   - pip value and lot sizing.
   - spread, slippage, swap, and commission per lot.
   - partial fills or failed-order assumptions where relevant.
4. Stress test the recovery engine:
   - Brexit-style moves.
   - COVID shock.
   - Ukraine-war volatility.
   - CPI/FOMC spikes.
   - flash candles and spread widening.
   - long one-way trends.
5. Add robustness testing:
   - walk-forward validation after any recovery logic is added.
   - Monte Carlo trade reshuffling.
   - parameter stability maps.
   - worst 5% path drawdown analysis.
