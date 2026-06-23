# Directional Forex ML

## Hypothesis

Daily forex direction contains a small but tradable signal when the model is trained with strict time ordering, simple no-lookahead features, and realistic pair-specific transaction costs. The implementation follows the 2025 Springer Nature paper on directional forecasting across eight USD currency pairs.

## Paper Translation

- Universe: EUR/USD, CNY/USD, JPY/USD, AUD/USD, CHF/USD, MXN/USD, ZAR/USD, TRY/USD.
- Target: `Close[t + horizon] > Open[t]`.
- Baseline features: daily return, normalized high-low range, opening gap.
- Extended features: optional macro/yield columns when supplied.
- Models: Logistic Regression, Logistic Regression selected by MADL, Decision Tree, Random Forest, Gradient Boosting, AdaBoost, XGBoost, and MLP.
- Cost model: dynamic spread cost, `cost_pct = spread_pips * pip_value / current_price`, applied symmetrically.
- Selection principle: prefer interpretable, cost-aware models over high-accuracy models that overtrade.

Broker data often arrives as `USDJPY`, `USDMXN`, or `USDZAR`, while the paper expresses those series as `JPY/USD`, `MXN/USD`, and `ZAR/USD`. Use `invert_usd_base_quote(...)` when reproducing the paper convention from broker-style OHLCV.

## Implementation Map

- Strategy framework: this `STRATEGY.md` states the hypothesis, universe, model rules, validation gates, reporting status, and live-trading block.
- OHLCV processing: all public entry points call `market_data.ohlcv.validate_ohlcv(...)`; broker-style USD-base pairs can be converted with `features.invert_usd_base_quote(...)`.
- Feature engineering: `features.py` builds no-lookahead lagged returns, opening gap, volatility, rolling momentum, skew, kurtosis, and optional macro features.
- Signal classification and scikit-learn: `models.py` trains Logistic Regression, Logistic MADL, Decision Tree, Random Forest, Gradient Boosting, AdaBoost, and MLP classifiers with probability outputs.
- XGBoost: `models.py` supports `model_name="xgboost"` when the optional `xgboost` package is installed.
- Walk-forward validation: `research/walk_forward.py` provides rolling or expanding train/test splits with purge and embargo.
- Paper-period validation: `research/paper_validation.py` evaluates pre-COVID, COVID-era, post-COVID, full-period, future-validation, and cost-sensitivity runs.
- Slippage and costs: `costs.py` models paper-style dynamic forex spread costs plus optional commission and slippage buffers.
- Macro feature path: `macro.py` loads 5-year and 13-week Treasury rates into the paper macro schema.
- Statistical validation: `statistics.py` provides paired t-test, Wilcoxon, bootstrap confidence intervals, and an approximate Hansen-style SPA bootstrap screen.
- VaR backtesting: `risk.py` provides Historical, Parametric, and EWMA VaR models with Kupiec POF and Christoffersen independence diagnostics.
- Vectorized backtesting: `backtesting/vectorbt_engine.py` adapts prepared ML signals into the shared vectorbt engine when vectorbt is installed.
- Portfolio analytics: `analytics.py` reports total return, Sharpe, Sortino, Calmar, Omega, VaR, CVaR, max drawdown, time underwater, win rate, profit factor, and expectancy.
- Trading visualization: `reporting.py` wraps the shared `visualization`/reporting layer to export price, ML probability overlays, entries, exits, equity, drawdown, trade tables, metrics, and model-comparison charts.

## Reusable Signal Gate

Other strategies can use the classifier before entry:

```python
gate = apply_ml_probability_gate(
    base_long_entries=signals["long_entry"],
    base_short_entries=signals["short_entry"],
    probabilities=ml_probabilities,
    expected_move=expected_move,
    cost_hurdle=cost_hurdle,
    threshold=0.54,
)
```

For a full base signal table:

```python
gate = build_ml_gate_for_signals(
    ohlcv=data,
    base_signals=scalper_signals,
    artifact=trained_ml_artifact,
    threshold=0.54,
)
```

Accept a base signal only when:

- ML probability agrees with trade direction.
- Estimated move exceeds spread + commission + slippage buffer.

This is intended to filter weak RSI/SMA/Marubozu signals in strategies such as Scalper Major.

## Status

- Research implementation: started and initial daily smoke baseline completed.
- Live execution: blocked until model persistence, broker spread snapshots, and paper-trading validation are added.
- Reporting: standard strategy report wrapper is available.
- Paper reproduction status: implementation support is now in place for the missing paper components, but the full eight-pair 2018-2023 paper run still needs to be executed and documented after all datasets and optional XGBoost dependency are available.

## Paper-Reproduction Commands

Run the exact paper-style technical feature baseline across all available local datasets:

```bash
python scripts/run_directional_forex_ml_research.py \
  --paper-models \
  --feature-set paper_technical \
  --invert-usd-base-to-paper \
  --regime-validation \
  --future-validation \
  --cost-sensitivity \
  --var-backtest \
  --generate-comparison-charts \
  --name directional_forex_ml_paper_reproduction
```

Run the technical + macro path when a Treasury macro CSV is available:

```bash
python scripts/run_directional_forex_ml_research.py \
  --paper-models \
  --feature-set paper_technical \
  --macro-csv datasets/macro/treasury_rates.csv \
  --use-macro-features \
  --invert-usd-base-to-paper \
  --regime-validation \
  --future-validation \
  --cost-sensitivity \
  --var-backtest \
  --generate-comparison-charts \
  --name directional_forex_ml_paper_macro
```

## Backtest Results

### Daily Smoke Baseline

- Status: initial leakage-safe smoke run populated from local Dukascopy daily datasets.
- Command:
  - `python scripts/run_directional_forex_ml_research.py datasets/EURUSD/EURUSD_d1_dukascopy_bid_2020-01-01_2024-01-01.csv datasets/AUDUSD/AUDUSD_d1_dukascopy_bid_2020-01-01_2024-01-01.csv datasets/USDJPY/USDJPY_d1_dukascopy_bid_2020-01-01_2024-01-01.csv datasets/USDCHF/USDCHF_d1_dukascopy_bid_2020-01-01_2024-01-01.csv --models logistic_madl logistic --name directional_forex_ml_daily_smoke --output-dir trade_results/research --walk-forward --train-size 600 --test-size 150 --step-size 150 --purge-size 1 --embargo-size 1 --invert-usd-base-to-paper`
- Assumptions:
  - Daily OHLCV only.
  - Data period: 2020-01-01 to 2023-12-29.
  - Initial cash: 10,000.
  - Technical feature set only.
  - Completed-bar features are shifted by one bar to avoid lookahead.
  - Current opening gap is allowed because it is known at decision time.
  - Broker-style `USDJPY` was inverted to paper-style `JPYUSD`.
  - Dynamic paper spread costs were applied.
- Single split results:

| Symbol | Research Symbol | Model | Return | Sharpe | Max Drawdown | Trades | Win Rate | Profit Factor |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | EURUSD | logistic_madl | -5.51% | -1.346 | -5.71% | 43 | 34.88% | 0.539 |
| EURUSD | EURUSD | logistic | -7.61% | -1.765 | -7.81% | 52 | 34.62% | 0.463 |
| AUDUSD | AUDUSD | logistic_madl | -0.37% | -0.090 | -3.73% | 24 | 50.00% | 0.953 |
| AUDUSD | AUDUSD | logistic | -3.63% | -0.453 | -10.10% | 72 | 45.83% | 0.860 |
| USDJPY | JPYUSD | logistic_madl | 0.00% | NA | 0.00% | 0 | NA | NA |
| USDJPY | JPYUSD | logistic | 0.00% | NA | 0.00% | 0 | NA | NA |
| USDCHF | USDCHF | logistic_madl | -0.05% | 0.023 | -6.22% | 87 | 51.72% | 1.007 |
| USDCHF | USDCHF | logistic | -0.05% | 0.023 | -6.22% | 87 | 51.72% | 1.007 |

### Walk-Forward Smoke Baseline

| Symbol | Research Symbol | Model | Folds | Mean OOS Return | Mean OOS Sharpe | Worst OOS Drawdown | OOS Trades | Profitable Folds |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | EURUSD | logistic_madl | 4 | -3.49% | -0.691 | -13.48% | 351 | 1 |
| EURUSD | EURUSD | logistic | 4 | -4.09% | -0.788 | -14.24% | 366 | 1 |
| AUDUSD | AUDUSD | logistic_madl | 4 | -3.60% | -0.248 | -22.81% | 192 | 2 |
| AUDUSD | AUDUSD | logistic | 4 | -5.14% | -0.587 | -26.28% | 230 | 1 |
| USDJPY | JPYUSD | logistic_madl | 4 | -0.08% | -0.149 | -2.02% | 3 | 0 |
| USDJPY | JPYUSD | logistic | 4 | -2.36% | -1.491 | -9.12% | 13 | 0 |
| USDCHF | USDCHF | logistic_madl | 4 | -6.88% | -0.830 | -24.56% | 272 | 1 |
| USDCHF | USDCHF | logistic | 4 | -9.29% | -1.343 | -25.54% | 313 | 1 |

- Stored outputs:
  - `trade_results/research/directional_forex_ml_daily_smoke_summary.csv`
  - `trade_results/research/directional_forex_ml_daily_smoke_summary.md`
  - `trade_results/research/directional_forex_ml_daily_smoke_*_walk_forward.csv`
- Interpretation:
  - The leakage-safe baseline does not validate the standalone strategy yet.
  - Logistic MADL improves some cases versus standard logistic regression, especially AUDUSD and EURUSD, but the OOS fold results remain weak.
  - These results are still useful as a strategy gate: the classifier can reject low-quality entries from rule-based systems, but should not be traded standalone until it passes broader pair/timeframe/future-period validation.
  - Earlier unrealistically high smoke results were discarded after identifying same-day close/high/low lookahead. Completed-bar features are now shifted.
