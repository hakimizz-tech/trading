# Trading Bot Framework

This project is a research-to-execution framework for systematic trading strategies.

The goal is to design strategies in a way that can be researched on Linux, tested with historical data, visualized with consistent reports, journaled for review, and later executed through MetaTrader 5/aiomql in a Windows environment when the strategy is ready.

The project currently supports two strategy styles:

- **BollingerBand**: a signal-driven strategy with explicit entries, exits, stops, take-profit logic, and aiomql execution gates.
- **RisingAssest**: a long-only multi-asset rotation strategy that ranks assets by momentum, allocates to the strongest assets, and exits positions through monthly rebalancing.

Market data comes from multiple sources depending on the asset class. Stock and ETF research can use Yahoo Finance data. Forex, metals, and other instruments can use local CSVs, MetaTrader exports, or Dukascopy data. All data is normalized into a common OHLCV shape before strategies consume it.

The framework separates concerns deliberately:

- Strategy logic decides what should happen.
- Backtesting evaluates whether the idea is worth continuing.
- Reporting and visualization explain how the strategy behaved.
- Journaling records strategy decisions and order lifecycle events.
- Accounting records confirmed economic activity only.
- Execution gates protect live trading with spread, position, loss, and sizing checks.

Live trading is not the default mode. The intended workflow is research first, then backtest, then report, then paper/demo trading, then carefully gated live execution only after the strategy has earned that promotion.

This is not a prediction engine or a promise of returns. It is an engineering workspace for making trading ideas testable, auditable, and easier to improve over time.
