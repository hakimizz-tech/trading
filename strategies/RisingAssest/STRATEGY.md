# Strategy: Rising Assets v1.0

Source specification: `strategies/RisingAssest/rising-assets-strategy.md`.

## Identity

- Asset class: Global ETF universe across equities, real estate, credit, gold, and US treasuries.
- Timeframe: Daily data, monthly rebalance on the last available trading day of each month.
- Style: Long-only cross-asset trend following / momentum rotation.
- Objective: Long risk assets when they are rising; rotate toward bonds, gold, and other defensive assets when risk assets are not leading.

## Universe

Risk assets:

- `SPY`, `IWM`, `QQQ`, `EFA`, `EEM`, `VNQ`, `LQD`

Risk-off assets:

- `GLD`, `SHY`, `IEF`, `TLT`, `AGG`

## Rules

1. At each monthly rebalance, calculate each asset's momentum score.
2. Momentum score is the average of trailing 1-month, 3-month, 6-month, and 12-month total returns.
3. Select the top 5 assets by momentum score.
4. Weight selected assets by inverse 63-trading-day volatility.
5. Sell assets that leave the top 5 at the next rebalance.
6. The strategy is long-only and fully allocated when enough data exists.

## Risk

- No short selling.
- Portfolio concentration is limited by selecting 5 assets and inverse-volatility weighting them.
- Execution should be delayed one bar after a rebalance signal in backtests to avoid lookahead bias.
- Live deployment requires broker-symbol mapping and portfolio-level order reconciliation.

## Implementation

- Core implementation: `strategies.RisingAssest.core`.
- Backtesting signal adapter: `strategies.RisingAssest.backtesting.signals`.
- Vectorbt research adapter: `strategies.RisingAssest.backtesting.vectorbt_engine`.
- Report wrapper: `strategies.RisingAssest.reporting`.
- Research runner: `scripts/run_rising_assets_research.py`.
- Yahoo Finance dataset collector: `scripts/download_yfinance_history.py`.

## Backtest Results

### In-Sample

- Status: local baseline populated from yfinance ETF datasets on 2026-06-18.
- Data command:
  - `./.venv/bin/python scripts/download_yfinance_history.py --rising-assets-universe --period 10y --interval 1d --repair --manifest datasets/yfinance_rising_assets_manifest.json`
- Research command:
  - `./.venv/bin/python scripts/run_rising_assets_research.py --dataset SPY datasets/SPY/SPY_1d_yfinance.csv --dataset IWM datasets/IWM/IWM_1d_yfinance.csv --dataset QQQ datasets/QQQ/QQQ_1d_yfinance.csv --dataset EFA datasets/EFA/EFA_1d_yfinance.csv --dataset EEM datasets/EEM/EEM_1d_yfinance.csv --dataset VNQ datasets/VNQ/VNQ_1d_yfinance.csv --dataset LQD datasets/LQD/LQD_1d_yfinance.csv --dataset GLD datasets/GLD/GLD_1d_yfinance.csv --dataset SHY datasets/SHY/SHY_1d_yfinance.csv --dataset IEF datasets/IEF/IEF_1d_yfinance.csv --dataset TLT datasets/TLT/TLT_1d_yfinance.csv --dataset AGG datasets/AGG/AGG_1d_yfinance.csv --report-name rising_assets_yfinance_12etf --skip-report-charts`
- Assumptions:
  - vectorbt target-percent portfolio adapter.
  - Initial cash: 10,000.
  - Long-only.
  - Monthly rebalance on last available trading day of each month.
  - Select top 5 assets by average 1/3/6/12-month momentum.
  - Weight selected assets by inverse 63-day volatility.
  - One-bar delayed execution to avoid lookahead.
- Results:

| Dataset | Period | Rows | Assets | Total Return | Annualized Return | Annualized Volatility | Sharpe | Max Drawdown | Rebalances |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rising Assets 12 ETF | 2016-06-20 to 2026-06-17 | 2,513 | 12 | 98.70% | 7.13% | 9.92% | 0.719 | -16.24% | 109 |

Latest target allocation:

| Symbol | Target Weight |
| --- | ---: |
| SPY | 28.02% |
| IWM | 19.88% |
| QQQ | 18.64% |
| EFA | 20.24% |
| EEM | 13.22% |
| VNQ | 0.00% |
| LQD | 0.00% |
| GLD | 0.00% |
| SHY | 0.00% |
| IEF | 0.00% |
| TLT | 0.00% |
| AGG | 0.00% |

- Stored outputs:
  - `trade_results/research/rising_assets_yfinance_12etf_metrics.csv`
  - `trade_results/research/rising_assets_yfinance_12etf_latest_weights.csv`
  - `trade_results/research/rising_assets_yfinance_12etf_live_readiness.json`
  - `trade_results/reports/rising_assets_yfinance_12etf/`
- Interpretation:
  - This is a useful full-universe ETF baseline.
  - The strategy remains blocked for live deployment until broker symbol mapping and paper-trade validation exist.

Data-quality notes:

- yfinance successfully returned all 12 ETF datasets.
- Most assets have 2,513 aligned daily rows ending 2026-06-17.
- `SPY` and `QQQ` include one zero-volume/missing OHLC row each in the raw Yahoo response; normalized quality completeness is 99.96%.
- `VNQ` has one impossible candle flagged by structural OHLC validation.
- Yahoo Finance data can be delayed, revised, repaired, or incomplete, so serious research should preserve raw files and review quality reports before promotion.

Data-quality artifacts:

- `datasets/yfinance_rising_assets_manifest.json`
- `trade_results/data_quality/yfinance_rising_assets/ohlcv_dataset_quality.csv`

### Out-of-Sample

- Status: not populated yet.
- Required method:
  - Rolling or expanding walk-forward validation.
  - Train windows should cover at least one full market cycle when possible.
  - Test windows should be monthly or quarterly blocks.
  - Embargo should separate train/test by at least several trading days.
- Required outputs:
  - `trade_results/research/rising_assets_<run>_walk_forward.csv`
  - `trade_results/research/rising_assets_<run>_walk_forward_summary.json`
- Interpretation:
  - In-sample performance alone is not enough for paper trading.
  - Walk-forward validation should be added before live checklisting.

### Paper Trade Results

- Status: not started.
- Requirement before live: run at least 2 weeks or 30 trades, whichever is longer.

## Standard Reporting

- Strategy-level report module: `strategies.RisingAssest.reporting`.
- Standard report function: `generate_rising_assets_report`.
- Default export root: `trade_results/reports/`.
- Research runner hook:
  - `scripts/run_rising_assets_research.py`.
  - Use `--skip-report-charts` for table-only report generation on machines without chart dependencies.

Per-run report charts:

- `trade_results/reports/rising_assets_yfinance_12etf/equity_trades.png` — equity timeline with rebalance markers.
- `trade_results/reports/rising_assets_yfinance_12etf/equity_drawdown.png` — equity curve and underwater drawdown.
- `trade_results/reports/rising_assets_yfinance_12etf/target_allocations.png` — monthly target allocation stack.
- `trade_results/reports/rising_assets_yfinance_12etf/asset_growth.png` — strategy growth of $1 versus each ETF.
- `trade_results/reports/rising_assets_yfinance_12etf/return_distribution.png` — strategy return distribution with risk markers.
- `trade_results/reports/rising_assets_yfinance_12etf/asset_correlation.png` — ETF return correlation heatmap.

Per-run report tables:

- `trade_results/reports/rising_assets_yfinance_12etf/report_data.csv`
- `trade_results/reports/rising_assets_yfinance_12etf/trades.csv`
- `trade_results/reports/rising_assets_yfinance_12etf/trade_summary.csv`
- `trade_results/reports/rising_assets_yfinance_12etf/target_weights.csv`
- `trade_results/reports/rising_assets_yfinance_12etf/momentum_scores.csv`
- `trade_results/reports/rising_assets_yfinance_12etf/metrics.json`

## Live Readiness

The strategy now has broker-agnostic live preparation pieces:

- Price CSV/universe loading.
- yfinance stock/ETF data collection into `datasets/<TICKER>/<TICKER>_<interval>_yfinance.csv`.
- Monthly target-weight generation with explicit liquidation to zero for dropped assets.
- Vectorbt backtest adapter using target-percent rebalances.
- Broker-agnostic live rebalance order generation.
- Live-readiness validation for history, symbol coverage, and broker symbol mapping.

Current live status: blocked.

Blockers from the latest local run:

- Missing broker-symbol mapping for the full strategy universe.

Before live market execution, add broker symbol mapping, broker-specific order sizing rules, trading session checks, cash/reconciliation checks, and paper-trade validation.
