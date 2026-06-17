# Trading Bot Framework

This project separates strategy research from MetaTrader 5 execution:

- `bollinger_bands_strategy.py` contains pandas/numpy indicator, signal, and backtest logic that runs on Linux.
- `strategies/bollinger_aiomql.py` wraps the tested signal logic as an aiomql `Strategy` for Windows/MT5.
- `bot.py` loads one or many strategy specs from JSON and runs them through an aiomql `Bot`.
- `bot_config.py` validates bot settings without requiring aiomql.

Live execution is disabled by default. Use demo/dry-run first.

## Linux Research

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python bollinger_bands_strategy.py path/to/ohlcv.csv --date-col time
```

The Bollinger strategy separates entries from exits and supports an adaptive mode:

- Entries: mean reversion, BBMA, BB + RSI, or adaptive BB + RSI + MACD.
- Adaptive Regime A: wide-band ranging market, BB bounce entries confirmed by RSI.
- Adaptive Regime B: recent Bollinger squeeze, breakout entries confirmed by MACD crossover.
- Stop loss: ATR-based stop, default `2.0 × ATR(14)`.
- Take profit: fixed R-multiple target, default `2R`.
- Trailing stop: ATR trailing after the trade reaches the activation R multiple.
- Time stop: exits dead trades after `max_hold_bars` when not profitable.
- Signal exit: mean-reversion exits at the middle band; breakout exits on reverse MACD cross.

The module uses pandas/numpy indicators by default and will use TA-Lib for RSI/MACD if `talib` is installed.

Example:

```bash
.venv/bin/python bollinger_bands_strategy.py data.csv \
  --date-col time \
  --strategy adaptive \
  --atr-stop-mult 2.0 \
  --take-profit-rr 2.0 \
  --trailing-atr-mult 2.5 \
  --max-hold-bars 50 \
  --squeeze-quantile 0.2 \
  --wide-quantile 0.6
```

## Windows aiomql Setup

Use Windows with Python 3.13+, MetaTrader 5, aiomql, and a broker demo account.
The `MetaTrader5` dependency behind aiomql is not installable for this Linux
research environment, so install the aiomql runtime only after migrating to
Windows.

```bash
python -m pip install -r requirements-aiomql.txt
copy aiomql.json.example aiomql.json
python scripts/check_aiomql_env.py --project .
```

Fill `aiomql.json` locally. Do not commit it.

Then edit `bot_settings.example.json` or create your own settings file:

```bash
python bot.py --settings bot_settings.example.json
```

## Adding Strategies

1. Put pure signal logic in a testable module that accepts an OHLCV DataFrame.
2. Add an aiomql wrapper in `strategies/`.
3. Register the wrapper in `bot.py`.
4. Add a strategy spec to the JSON settings file.
5. Keep `live_trading` false until the strategy has been backtested and demo tested.
