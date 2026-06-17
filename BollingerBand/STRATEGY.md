# Strategy: Adaptive Bollinger Bands v1.0

## Overview

- **Asset class**: Liquid OHLCV-traded instruments supported by the data source and, for execution, MetaTrader 5 symbols available through aiomql.
- **Timeframe**: Primary M15 by default; configurable through `timeframe` and `interval`.
- **Style**: Hybrid mean reversion and breakout.
- **Lifecycle status**: Research and dry-run only. Not approved for live trading until the performance criteria and paper-trade gates below are met.
- **Edge hypothesis**: Prices alternate between ranging regimes, where Bollinger Band extremes can mean-revert, and volatility-compression regimes, where a Bollinger squeeze can precede directional expansion. RSI confirms exhaustion in mean-reversion regimes, while MACD confirms momentum in breakout regimes.

## Entry Rules

All entries use completed OHLCV bars. The canonical implementation lives in `BollingerBand.core.generate_adaptive_bollinger_signals`.

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
- aiomql execution: `BollingerBand.execution.aiomql_strategy.BollingerBandsAiomqlStrategy`.
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
- aiomql default: fixed volume `0.01` with `risk_per_trade = 0.01`.
- Required before live scaling: replace fixed volume with broker-aware sizing from account equity, stop distance, pip value, and `risk_per_trade`.
- Max position: one open position per strategy-symbol by default.

## Risk Parameters

- Risk per trade: default 1%, allowed range `(0, 5%]` in execution gate.
- Max open positions: default 1 per configured strategy-symbol.
- Stop-loss required: execution gate requires positive `stop_loss_pips`.
- Take-profit/risk multiple required: execution gate requires positive `take_profit_rr`.
- Live mode: opt-in only through config.
- Journal rule: live orders are blocked if journaling fails.
- Accounting rule: only confirmed fills and exits should be posted to the double-entry ledger.
- Current gap before production: max daily loss, spread measurement, and broker open-position inspection must be connected to live account state.

## Filters

### Market Filters

- Regime filter: adaptive bandwidth classifies mean-reversion, squeeze, breakout, or neutral conditions.
- Volatility filter: mean reversion only fires in wide-bandwidth regimes; breakout only fires after squeeze conditions.
- Momentum filter: breakout requires MACD confirmation.
- Volume filter: optional breakout volume confirmation using volume above rolling baseline.

### Instrument Filters

- Required OHLCV columns: open, high, low, close, volume.
- Execution symbols must be available in MetaTrader 5 through the configured broker.
- No liquidity, spread, or session filter is fully enforced in Linux research mode.

### Time Filters

- aiomql supports session injection via `sessions`.
- Default config does not restrict trading hours.
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

- Status: not yet populated with a committed dataset.
- Requirement before live: store dataset name, period, parameters, total return, Sharpe, max drawdown, win rate, profit factor, trade count, and average trade duration.

### Out-of-Sample

- Status: not yet populated with a committed dataset.
- Requirement before live: use walk-forward or train/test split and compare degradation from in-sample results.

### Paper Trade Results

- Status: not started.
- Requirement before live: run at least 2 weeks or 30 trades, whichever is longer.

## Dependencies

- Data: standard OHLCV DataFrame for research; aiomql `ForexSymbol.copy_rates_from_pos` for MT5 execution.
- Indicators: pandas/numpy by default; optional TA-Lib acceleration for RSI and MACD.
- Backtesting: pandas research backtest and optional vectorbt adapter.
- Execution: aiomql on Windows with MetaTrader 5.
- Persistence: SQLite trade journal and double-entry accounting ledger.
- Visualization: shared `visualization` package.

## Notes

- This document defines the adaptive strategy as a single hybrid strategy with two explicit sub-regimes.
- The simpler `mean_reversion`, `bbma`, and `bb_rsi` modes are research variants and should receive their own strategy definition document if promoted to production.
- Parameter optimization is research-only. Use walk-forward validation before adopting optimized parameters.

## Change Log

- **v1.0** 2026-06-17: Initial framework definition for the adaptive Bollinger Bands strategy.
