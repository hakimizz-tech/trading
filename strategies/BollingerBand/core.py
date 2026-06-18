"""Bollinger Bands strategy research module.

This file is intentionally independent of MetaTrader 5/aiomql so it can be
developed on Linux and later wrapped in an aiomql Strategy on Windows.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    talib: Any = import_module("talib")
except ImportError:  # pragma: no cover - optional production acceleration
    talib = None


BUY = 1
SELL = -1
FLAT = 0


@dataclass(frozen=True)
class BacktestResult:
    data: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float | int]


@dataclass(frozen=True)
class ExitPlan:
    """Rule-based exit plan for completed-bar backtests.

    Priority: hard stop > ATR stop/trail > take profit > signal exit > time stop.
    """

    atr_length: int = 14
    atr_stop_multiplier: float = 2.0
    take_profit_rr: float = 2.0
    trailing_atr_multiplier: float = 2.5
    trail_activation_rr: float = 1.0
    max_hold_bars: int = 50
    use_signal_exit: bool = True


@dataclass(frozen=True)
class AdaptiveRegimeConfig:
    """Configuration for adaptive Bollinger regime detection."""

    regime_mode: str = "hybrid"
    bb_window: int = 20
    bb_num_std: float = 2.0
    rsi_window: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bandwidth_lookback: int = 120
    squeeze_quantile: float = 0.20
    wide_quantile: float = 0.60
    squeeze_release_bars: int = 5
    breakout_buffer: float = 0.0
    require_volume_confirmation: bool = False
    volume_window: int = 20
    volume_multiplier: float = 1.2
    max_spread: float | None = None
    spread_col: str = "spread"
    session_start: str | None = None
    session_end: str | None = None


def _require_columns(data: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def calculate_bollinger_bands(
    data: pd.DataFrame,
    window: int = 20,
    num_std: float = 2.0,
    price_col: str = "close",
) -> pd.DataFrame:
    """Add Bollinger Bands using SMA and population standard deviation.

    Formulas:
    - middle = N-period SMA(close)
    - upper = middle + K * population_std(close, N)
    - lower = middle - K * population_std(close, N)
    """
    _require_columns(data, (price_col,))
    if window <= 1:
        raise ValueError("window must be greater than 1")
    if num_std <= 0:
        raise ValueError("num_std must be positive")

    result = data.copy()
    price = result[price_col].astype(float)
    middle = price.rolling(window=window, min_periods=window).mean()
    population_std = price.rolling(window=window, min_periods=window).std(ddof=0)

    result["bb_middle"] = middle
    result["bb_upper"] = middle + num_std * population_std
    result["bb_lower"] = middle - num_std * population_std
    result["bb_width"] = result["bb_upper"] - result["bb_lower"]
    result["bb_bandwidth"] = result["bb_width"] / result["bb_middle"].replace(0.0, np.nan)
    return result


def add_atr(data: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Add Average True Range using Wilder-style exponential smoothing."""
    _require_columns(data, ("high", "low", "close"))
    if window <= 1:
        raise ValueError("window must be greater than 1")

    result = data.copy()
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    close = result["close"].astype(float)
    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result[f"atr_{window}"] = true_range.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    return result


def generate_mean_reversion_signals(
    data: pd.DataFrame,
    price_col: str = "close",
) -> pd.DataFrame:
    """Generate Bollinger mean-reversion buy/sell signals.

    Buy:  price(t-1) < lower(t-1) and price(t) > lower(t)
    Sell: price(t-1) > upper(t-1) and price(t) < upper(t)
    """
    _require_columns(data, (price_col, "bb_upper", "bb_lower"))
    result = data.copy()
    price = result[price_col].astype(float)

    buy = (price.shift(1) < result["bb_lower"].shift(1)) & (price > result["bb_lower"])
    sell = (price.shift(1) > result["bb_upper"].shift(1)) & (price < result["bb_upper"])

    long_exit = (price.shift(1) <= result["bb_middle"].shift(1)) & (price > result["bb_middle"])
    short_exit = (price.shift(1) >= result["bb_middle"].shift(1)) & (price < result["bb_middle"])

    result["buy_signal"] = buy.fillna(False)
    result["sell_signal"] = sell.fillna(False)
    result["long_entry"] = result["buy_signal"]
    result["short_entry"] = result["sell_signal"]
    result["long_exit"] = long_exit.fillna(False) | result["sell_signal"]
    result["short_exit"] = short_exit.fillna(False) | result["buy_signal"]
    result["signal"] = np.select([result["buy_signal"], result["sell_signal"]], [BUY, SELL], default=FLAT)
    return result


def add_ema(data: pd.DataFrame, span: int = 50, price_col: str = "close") -> pd.DataFrame:
    """Add an EMA column using pandas' standard recursive EMA."""
    _require_columns(data, (price_col,))
    if span <= 1:
        raise ValueError("span must be greater than 1")

    result = data.copy()
    result[f"ema_{span}"] = result[price_col].astype(float).ewm(span=span, adjust=False).mean()
    return result


def generate_bbma_signals(
    data: pd.DataFrame,
    ema_span: int = 50,
    price_col: str = "close",
) -> pd.DataFrame:
    """Generate BB + EMA signals.

    Buy:  EMA crosses above the Bollinger middle band.
    Sell: EMA crosses below the Bollinger middle band.
    """
    result = add_ema(data, span=ema_span, price_col=price_col)
    ema_col = f"ema_{ema_span}"
    _require_columns(result, (ema_col, "bb_middle"))

    ema = result[ema_col]
    middle = result["bb_middle"]
    buy = (ema.shift(1) <= middle.shift(1)) & (ema > middle)
    sell = (ema.shift(1) >= middle.shift(1)) & (ema < middle)

    result["bbma_buy_signal"] = buy.fillna(False)
    result["bbma_sell_signal"] = sell.fillna(False)
    result["long_entry"] = result["bbma_buy_signal"]
    result["short_entry"] = result["bbma_sell_signal"]
    result["long_exit"] = result["bbma_sell_signal"]
    result["short_exit"] = result["bbma_buy_signal"]
    result["signal"] = np.select(
        [result["bbma_buy_signal"], result["bbma_sell_signal"]],
        [BUY, SELL],
        default=FLAT,
    )
    return result


def add_rsi(data: pd.DataFrame, window: int = 14, price_col: str = "close") -> pd.DataFrame:
    """Add Wilder RSI."""
    _require_columns(data, (price_col,))
    if window <= 1:
        raise ValueError("window must be greater than 1")

    result = data.copy()
    if talib is not None:
        close_values = result[price_col].astype(float).to_numpy(dtype=np.float64)
        result[f"rsi_{window}"] = talib.RSI(close_values, timeperiod=window)
        return result

    delta = result[price_col].astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)

    result[f"rsi_{window}"] = 100.0 - (100.0 / (1.0 + rs))
    result.loc[avg_loss == 0.0, f"rsi_{window}"] = 100.0
    result.loc[(avg_gain == 0.0) & (avg_loss == 0.0), f"rsi_{window}"] = 50.0
    return result


def add_macd(
    data: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    price_col: str = "close",
) -> pd.DataFrame:
    """Add MACD line, signal line, and histogram."""
    _require_columns(data, (price_col,))
    if min(fast, slow, signal) <= 1:
        raise ValueError("MACD periods must be greater than 1")
    if fast >= slow:
        raise ValueError("MACD fast period must be less than slow period")

    result = data.copy()
    macd_col = f"macd_{fast}_{slow}_{signal}"
    signal_col = f"macd_signal_{fast}_{slow}_{signal}"
    hist_col = f"macd_hist_{fast}_{slow}_{signal}"

    close = result[price_col].astype(float)
    if talib is not None:
        macd, macd_signal, macd_hist = talib.MACD(
            close.to_numpy(dtype=np.float64),
            fastperiod=fast,
            slowperiod=slow,
            signalperiod=signal,
        )
        result[macd_col] = macd
        result[signal_col] = macd_signal
        result[hist_col] = macd_hist
        return result

    fast_ema = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    macd_signal = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()

    result[macd_col] = macd_line
    result[signal_col] = macd_signal
    result[hist_col] = macd_line - macd_signal
    return result


def add_volume_confirmation(
    data: pd.DataFrame,
    window: int = 20,
    multiplier: float = 1.2,
) -> pd.DataFrame:
    """Add a boolean volume confirmation column for breakout filtering."""
    _require_columns(data, ("volume",))
    if window <= 1:
        raise ValueError("window must be greater than 1")
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")

    result = data.copy()
    baseline = result["volume"].astype(float).rolling(window=window, min_periods=window).mean()
    result["volume_sma"] = baseline
    result["volume_confirmed"] = result["volume"].astype(float) > baseline * multiplier
    return result


def add_entry_filters(data: pd.DataFrame, config: AdaptiveRegimeConfig) -> pd.DataFrame:
    """Add spread/session filter columns used to gate strategy entries."""
    result = data.copy()
    spread_filter = _spread_filter(result, config)
    session_filter = _session_filter(result, config)
    result["spread_filter_pass"] = spread_filter
    result["session_filter_pass"] = session_filter
    result["entry_filter_pass"] = spread_filter & session_filter
    return result


def generate_bb_rsi_signals(
    data: pd.DataFrame,
    rsi_window: int = 14,
    oversold: float = 30.0,
    price_col: str = "close",
) -> pd.DataFrame:
    """Generate BB + RSI signals.

    The requested rule combines an oversold RSI, a lower-band excursion, and a
    middle-band cross. Since price cannot be both below the lower band and above
    the middle band on the same completed bar, this implementation requires the
    prior bar to be outside the lower band and the current bar to cross above the
    middle band while RSI is still oversold.
    """
    result = add_rsi(data, window=rsi_window, price_col=price_col)
    rsi_col = f"rsi_{rsi_window}"
    _require_columns(result, (price_col, "bb_lower", "bb_middle", rsi_col))

    price = result[price_col].astype(float)
    prior_outside_lower = price.shift(1) < result["bb_lower"].shift(1)
    crosses_middle_up = (price.shift(1) <= result["bb_middle"].shift(1)) & (price > result["bb_middle"])
    buy = (result[rsi_col] < oversold) & prior_outside_lower & crosses_middle_up

    long_exit = (price.shift(1) <= result["bb_middle"].shift(1)) & (price > result["bb_middle"])

    result["bb_rsi_buy_signal"] = buy.fillna(False)
    result["long_entry"] = result["bb_rsi_buy_signal"]
    result["short_entry"] = False
    result["long_exit"] = long_exit.fillna(False)
    result["short_exit"] = False
    result["signal"] = np.where(result["bb_rsi_buy_signal"], BUY, FLAT)
    return result


def generate_adaptive_bollinger_signals(
    data: pd.DataFrame,
    config: AdaptiveRegimeConfig | None = None,
    price_col: str = "close",
) -> pd.DataFrame:
    """Generate adaptive BB signals across mean-reversion and breakout regimes.

    Regime A, mean reversion:
    - Wide bandwidth.
    - Long when close crosses back above lower band and RSI < oversold.
    - Short when close crosses back below upper band and RSI > overbought.
    - Signal exit at the middle band.

    Regime B, squeeze breakout:
    - Recent Bollinger squeeze.
    - Long when close breaks above upper band and MACD crosses bullish.
    - Short when close breaks below lower band and MACD crosses bearish.
    - Signal exit on reverse MACD crossover; trailing exits are handled by
      ``backtest_entries_with_exits``.
    """
    cfg = config or AdaptiveRegimeConfig()
    _validate_regime_mode(cfg.regime_mode)
    result = calculate_bollinger_bands(data, window=cfg.bb_window, num_std=cfg.bb_num_std, price_col=price_col)
    result = add_rsi(result, window=cfg.rsi_window, price_col=price_col)
    result = add_macd(result, fast=cfg.macd_fast, slow=cfg.macd_slow, signal=cfg.macd_signal, price_col=price_col)
    result = add_volume_confirmation(result, window=cfg.volume_window, multiplier=cfg.volume_multiplier)
    result = add_entry_filters(result, cfg)

    price = result[price_col].astype(float)
    bandwidth = result["bb_bandwidth"]
    rsi = result[f"rsi_{cfg.rsi_window}"]
    macd = result[f"macd_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"]
    macd_signal = result[f"macd_signal_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"]

    squeeze_threshold = bandwidth.rolling(cfg.bandwidth_lookback, min_periods=cfg.bb_window).quantile(cfg.squeeze_quantile)
    wide_threshold = bandwidth.rolling(cfg.bandwidth_lookback, min_periods=cfg.bb_window).quantile(cfg.wide_quantile)
    squeeze = bandwidth <= squeeze_threshold
    squeeze_recent = squeeze.rolling(cfg.squeeze_release_bars, min_periods=1).max().astype(bool)
    wide_bandwidth = bandwidth >= wide_threshold

    macd_cross_up = (macd.shift(1) <= macd_signal.shift(1)) & (macd > macd_signal)
    macd_cross_down = (macd.shift(1) >= macd_signal.shift(1)) & (macd < macd_signal)
    volume_ok = result["volume_confirmed"] if cfg.require_volume_confirmation else pd.Series(True, index=result.index)

    lower_cross_up = (price.shift(1) < result["bb_lower"].shift(1)) & (price > result["bb_lower"])
    upper_cross_down = (price.shift(1) > result["bb_upper"].shift(1)) & (price < result["bb_upper"])
    middle_cross_up = (price.shift(1) <= result["bb_middle"].shift(1)) & (price >= result["bb_middle"])
    middle_cross_down = (price.shift(1) >= result["bb_middle"].shift(1)) & (price <= result["bb_middle"])

    breakout_upper = price > result["bb_upper"] * (1.0 + cfg.breakout_buffer)
    breakout_lower = price < result["bb_lower"] * (1.0 - cfg.breakout_buffer)

    entry_filter = result["entry_filter_pass"]
    mean_reversion_enabled = cfg.regime_mode in {"hybrid", "mean_reversion"}
    breakout_enabled = cfg.regime_mode in {"hybrid", "breakout"}

    mean_reversion_long_raw = wide_bandwidth & lower_cross_up & (rsi < cfg.rsi_oversold)
    mean_reversion_short_raw = wide_bandwidth & upper_cross_down & (rsi > cfg.rsi_overbought)
    breakout_long_raw = squeeze_recent & breakout_upper & macd_cross_up & volume_ok
    breakout_short_raw = squeeze_recent & breakout_lower & macd_cross_down & volume_ok

    mean_reversion_long = mean_reversion_long_raw & entry_filter & mean_reversion_enabled
    mean_reversion_short = mean_reversion_short_raw & entry_filter & mean_reversion_enabled
    breakout_long = breakout_long_raw & entry_filter & breakout_enabled
    breakout_short = breakout_short_raw & entry_filter & breakout_enabled
    long_exit = pd.Series(False, index=result.index)
    short_exit = pd.Series(False, index=result.index)
    if mean_reversion_enabled:
        long_exit = long_exit | middle_cross_up.fillna(False)
        short_exit = short_exit | middle_cross_down.fillna(False)
    if breakout_enabled:
        long_exit = long_exit | macd_cross_down.fillna(False)
        short_exit = short_exit | macd_cross_up.fillna(False)

    result["squeeze_threshold"] = squeeze_threshold
    result["wide_threshold"] = wide_threshold
    result["is_squeeze"] = squeeze.fillna(False)
    result["squeeze_recent"] = squeeze_recent.fillna(False)
    result["wide_bandwidth"] = wide_bandwidth.fillna(False)
    result["macd_cross_up"] = macd_cross_up.fillna(False)
    result["macd_cross_down"] = macd_cross_down.fillna(False)
    result["mean_reversion_long_raw"] = mean_reversion_long_raw.fillna(False)
    result["mean_reversion_short_raw"] = mean_reversion_short_raw.fillna(False)
    result["breakout_long_raw"] = breakout_long_raw.fillna(False)
    result["breakout_short_raw"] = breakout_short_raw.fillna(False)
    result["mean_reversion_long"] = mean_reversion_long.fillna(False)
    result["mean_reversion_short"] = mean_reversion_short.fillna(False)
    result["breakout_long"] = breakout_long.fillna(False)
    result["breakout_short"] = breakout_short.fillna(False)
    result["long_entry"] = result["mean_reversion_long"] | result["breakout_long"]
    result["short_entry"] = result["mean_reversion_short"] | result["breakout_short"]
    result["long_exit"] = long_exit.fillna(False)
    result["short_exit"] = short_exit.fillna(False)
    result["signal"] = np.select([result["long_entry"], result["short_entry"]], [BUY, SELL], default=FLAT)
    result["regime"] = np.select(
        [result["breakout_long"] | result["breakout_short"], result["mean_reversion_long"] | result["mean_reversion_short"], result["is_squeeze"]],
        ["breakout", "mean_reversion", "squeeze"],
        default="neutral",
    )
    return result


def _validate_regime_mode(regime_mode: str) -> None:
    if regime_mode not in {"hybrid", "mean_reversion", "breakout"}:
        raise ValueError("regime_mode must be one of: hybrid, mean_reversion, breakout")


def _spread_filter(data: pd.DataFrame, config: AdaptiveRegimeConfig) -> pd.Series:
    if config.max_spread is None:
        return pd.Series(True, index=data.index)
    if config.max_spread < 0:
        raise ValueError("max_spread must not be negative")
    if config.spread_col not in data.columns:
        return pd.Series(False, index=data.index)
    return data[config.spread_col].astype(float).le(float(config.max_spread)).fillna(False)


def _session_filter(data: pd.DataFrame, config: AdaptiveRegimeConfig) -> pd.Series:
    if config.session_start is None and config.session_end is None:
        return pd.Series(True, index=data.index)
    if config.session_start is None or config.session_end is None:
        raise ValueError("session_start and session_end must be provided together")
    if not isinstance(data.index, pd.DatetimeIndex):
        return pd.Series(False, index=data.index)

    start = pd.to_datetime(config.session_start).time()
    end = pd.to_datetime(config.session_end).time()
    times = pd.Series(data.index.time, index=data.index)
    if start <= end:
        return (times >= start) & (times <= end)
    return (times >= start) | (times <= end)


def backtest_entries_with_exits(
    data: pd.DataFrame,
    exit_plan: ExitPlan | None = None,
    price_col: str = "close",
    initial_capital: float = 1.0,
) -> BacktestResult:
    """Backtest entry signals with explicit stop, target, trail, and time exits."""
    plan = exit_plan or ExitPlan()
    _require_columns(data, (price_col, "high", "low", "long_entry", "short_entry", "long_exit", "short_exit"))
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if plan.take_profit_rr <= 0:
        raise ValueError("take_profit_rr must be positive")
    if plan.atr_stop_multiplier <= 0 or plan.trailing_atr_multiplier <= 0:
        raise ValueError("ATR multipliers must be positive")

    result = add_atr(data, window=plan.atr_length)
    atr_col = f"atr_{plan.atr_length}"
    price = result[price_col].astype(float)
    price_values = price.to_numpy(dtype=float)
    high_values = result["high"].astype(float).to_numpy(dtype=float)
    low_values = result["low"].astype(float).to_numpy(dtype=float)
    atr_values = result[atr_col].to_numpy(dtype=float)
    long_entries = result["long_entry"].fillna(False).to_numpy(dtype=bool)
    short_entries = result["short_entry"].fillna(False).to_numpy(dtype=bool)
    long_exits = result["long_exit"].fillna(False).to_numpy(dtype=bool)
    short_exits = result["short_exit"].fillna(False).to_numpy(dtype=bool)

    position = FLAT
    entry_price = 0.0
    stop_price = float("nan")
    take_profit_price = float("nan")
    risk_per_unit = 0.0
    entry_bar = -1
    favorable_extreme = 0.0
    trades: list[dict[str, object]] = []
    positions: list[int] = []
    exit_reasons: list[str] = []
    accepted_signals: list[int] = []

    for bar, (timestamp, price_value) in enumerate(zip(result.index, price_values)):
        accepted = FLAT
        exit_reason = ""
        current_price = float(price_value)
        current_high = float(high_values[bar])
        current_low = float(low_values[bar])
        current_atr = float(atr_values[bar])

        if position != FLAT:
            bars_held = bar - entry_bar
            if position == BUY:
                favorable_extreme = max(favorable_extreme, current_high)
                stop_price = _updated_long_stop(
                    stop_price=stop_price,
                    entry_price=entry_price,
                    favorable_extreme=favorable_extreme,
                    atr_value=current_atr,
                    risk_per_unit=risk_per_unit,
                    plan=plan,
                )
                exit_reason = _long_exit_reason(
                    current_price=current_price,
                    stop_price=stop_price,
                    take_profit_price=take_profit_price,
                    entry_price=entry_price,
                    bars_held=bars_held,
                    signal_exit=bool(long_exits[bar]) if plan.use_signal_exit else False,
                    plan=plan,
                )
            else:
                favorable_extreme = min(favorable_extreme, current_low)
                stop_price = _updated_short_stop(
                    stop_price=stop_price,
                    entry_price=entry_price,
                    favorable_extreme=favorable_extreme,
                    atr_value=current_atr,
                    risk_per_unit=risk_per_unit,
                    plan=plan,
                )
                exit_reason = _short_exit_reason(
                    current_price=current_price,
                    stop_price=stop_price,
                    take_profit_price=take_profit_price,
                    entry_price=entry_price,
                    bars_held=bars_held,
                    signal_exit=bool(short_exits[bar]) if plan.use_signal_exit else False,
                    plan=plan,
                )

            if exit_reason:
                trades.append(
                    {
                        "timestamp": timestamp,
                        "action": "EXIT_LONG" if position == BUY else "EXIT_SHORT",
                        "price": current_price,
                        "position_after": FLAT,
                        "reason": exit_reason,
                    }
                )
                position = FLAT
                stop_price = float("nan")
                take_profit_price = float("nan")
                risk_per_unit = 0.0
                entry_bar = -1

        if position == FLAT and np.isfinite(current_atr):
            if long_entries[bar]:
                position = BUY
                accepted = BUY
                entry_price = current_price
                risk_per_unit = max(current_atr * plan.atr_stop_multiplier, float(np.finfo(float).eps))
                stop_price = entry_price - risk_per_unit
                take_profit_price = entry_price + risk_per_unit * plan.take_profit_rr
                favorable_extreme = current_high
                entry_bar = bar
                trades.append(_entry_trade(timestamp, "ENTER_LONG", current_price, position, stop_price, take_profit_price))
            elif short_entries[bar]:
                position = SELL
                accepted = SELL
                entry_price = current_price
                risk_per_unit = max(current_atr * plan.atr_stop_multiplier, float(np.finfo(float).eps))
                stop_price = entry_price + risk_per_unit
                take_profit_price = entry_price - risk_per_unit * plan.take_profit_rr
                favorable_extreme = current_low
                entry_bar = bar
                trades.append(_entry_trade(timestamp, "ENTER_SHORT", current_price, position, stop_price, take_profit_price))

        accepted_signals.append(accepted)
        positions.append(position)
        exit_reasons.append(exit_reason)

    result["accepted_signal"] = accepted_signals
    result["position"] = positions
    result["exit_reason"] = exit_reasons
    result["asset_return"] = price.pct_change().fillna(0.0)
    result["strategy_return"] = result["position"].shift(1).fillna(0).astype(float) * result["asset_return"]
    result["equity"] = initial_capital * (1.0 + result["strategy_return"]).cumprod()
    result["buy_hold_equity"] = initial_capital * (1.0 + result["asset_return"]).cumprod()

    trades_df = pd.DataFrame(
        trades,
        columns=["timestamp", "action", "price", "position_after", "reason", "stop_price", "take_profit_price"],
    )
    relative_roi = float(result["equity"].iloc[-1] / initial_capital - 1.0) if len(result) else 0.0
    buy_hold_roi = float(result["buy_hold_equity"].iloc[-1] / initial_capital - 1.0) if len(result) else 0.0
    max_drawdown = _max_drawdown(result["equity"])
    exit_counts = trades_df["reason"].value_counts() if len(trades_df) else pd.Series(dtype=int)
    metrics: dict[str, float | int] = {
        "initial_capital": float(initial_capital),
        "final_equity": float(result["equity"].iloc[-1]) if len(result) else float(initial_capital),
        "relative_roi": relative_roi,
        "relative_roi_pct": relative_roi * 100.0,
        "buy_hold_roi": buy_hold_roi,
        "buy_hold_roi_pct": buy_hold_roi * 100.0,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100.0,
        "trade_count": int(len(trades_df)),
        "entries": int(trades_df["action"].astype(str).str.startswith("ENTER").sum()) if len(trades_df) else 0,
        "exits": int(trades_df["action"].astype(str).str.startswith("EXIT").sum()) if len(trades_df) else 0,
        "stop_exits": int(exit_counts.get("stop_loss", 0)),
        "take_profit_exits": int(exit_counts.get("take_profit", 0)),
        "signal_exits": int(exit_counts.get("signal_exit", 0)),
        "time_exits": int(exit_counts.get("time_stop", 0)),
    }
    return BacktestResult(data=result, trades=trades_df, metrics=metrics)


def _entry_trade(
    timestamp: object,
    action: str,
    price: float,
    position: int,
    stop_price: float,
    take_profit_price: float,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "action": action,
        "price": price,
        "position_after": position,
        "reason": "entry",
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
    }


def _updated_long_stop(
    *,
    stop_price: float,
    entry_price: float,
    favorable_extreme: float,
    atr_value: float,
    risk_per_unit: float,
    plan: ExitPlan,
) -> float:
    if not np.isfinite(atr_value):
        return stop_price
    if favorable_extreme < entry_price + risk_per_unit * plan.trail_activation_rr:
        return stop_price
    trailing_stop = favorable_extreme - atr_value * plan.trailing_atr_multiplier
    return max(stop_price, trailing_stop)


def _updated_short_stop(
    *,
    stop_price: float,
    entry_price: float,
    favorable_extreme: float,
    atr_value: float,
    risk_per_unit: float,
    plan: ExitPlan,
) -> float:
    if not np.isfinite(atr_value):
        return stop_price
    if favorable_extreme > entry_price - risk_per_unit * plan.trail_activation_rr:
        return stop_price
    trailing_stop = favorable_extreme + atr_value * plan.trailing_atr_multiplier
    return min(stop_price, trailing_stop)


def _long_exit_reason(
    *,
    current_price: float,
    stop_price: float,
    take_profit_price: float,
    entry_price: float,
    bars_held: int,
    signal_exit: bool,
    plan: ExitPlan,
) -> str:
    if current_price <= stop_price:
        return "stop_loss"
    if current_price >= take_profit_price:
        return "take_profit"
    if signal_exit:
        return "signal_exit"
    if bars_held >= plan.max_hold_bars and current_price <= entry_price:
        return "time_stop"
    return ""


def _short_exit_reason(
    *,
    current_price: float,
    stop_price: float,
    take_profit_price: float,
    entry_price: float,
    bars_held: int,
    signal_exit: bool,
    plan: ExitPlan,
) -> str:
    if current_price >= stop_price:
        return "stop_loss"
    if current_price <= take_profit_price:
        return "take_profit"
    if signal_exit:
        return "signal_exit"
    if bars_held >= plan.max_hold_bars and current_price >= entry_price:
        return "time_stop"
    return ""


def backtest_signals(
    data: pd.DataFrame,
    signal_col: str = "signal",
    price_col: str = "close",
    initial_capital: float = 1.0,
) -> BacktestResult:
    """Backtest long/short signals with no consecutive same-side actions.

    Signals are generated from completed bars and executed at that bar's close.
    Returns are earned from the following bar onward via ``position.shift(1)``.
    A BUY sets the strategy long, a SELL sets it short, and duplicate same-side
    actions are ignored until the position changes.
    """
    _require_columns(data, (price_col, signal_col))
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")

    result = data.copy()
    raw_signal = result[signal_col].fillna(FLAT).astype(int)
    price = result[price_col].astype(float)

    position = FLAT
    accepted_signals: list[int] = []
    positions: list[int] = []
    trades: list[dict[str, object]] = []
    signal_values = raw_signal.to_numpy(dtype=int)
    price_values = price.to_numpy(dtype=float)

    for timestamp, signal, current_price in zip(result.index, signal_values, price_values):
        accepted = FLAT
        if signal == BUY and position != BUY:
            position = BUY
            accepted = BUY
        elif signal == SELL and position != SELL:
            position = SELL
            accepted = SELL

        accepted_signals.append(accepted)
        positions.append(position)
        if accepted != FLAT:
            trades.append(
                {
                    "timestamp": timestamp,
                    "action": "BUY" if accepted == BUY else "SELL",
                    "price": current_price,
                    "position_after": position,
                }
            )

    result["accepted_signal"] = accepted_signals
    result["position"] = positions
    result["asset_return"] = price.pct_change().fillna(0.0)
    result["strategy_return"] = result["position"].shift(1).fillna(0).astype(float) * result["asset_return"]
    result["equity"] = initial_capital * (1.0 + result["strategy_return"]).cumprod()
    result["buy_hold_equity"] = initial_capital * (1.0 + result["asset_return"]).cumprod()

    trades_df = pd.DataFrame(trades, columns=["timestamp", "action", "price", "position_after"])
    relative_roi = float(result["equity"].iloc[-1] / initial_capital - 1.0) if len(result) else 0.0
    buy_hold_roi = float(result["buy_hold_equity"].iloc[-1] / initial_capital - 1.0) if len(result) else 0.0
    max_drawdown = _max_drawdown(result["equity"])

    metrics: dict[str, float | int] = {
        "initial_capital": float(initial_capital),
        "final_equity": float(result["equity"].iloc[-1]) if len(result) else float(initial_capital),
        "relative_roi": relative_roi,
        "relative_roi_pct": relative_roi * 100.0,
        "buy_hold_roi": buy_hold_roi,
        "buy_hold_roi_pct": buy_hold_roi * 100.0,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100.0,
        "trade_count": int(len(trades_df)),
        "long_entries": int((trades_df["action"] == "BUY").sum()) if len(trades_df) else 0,
        "short_entries": int((trades_df["action"] == "SELL").sum()) if len(trades_df) else 0,
    }
    return BacktestResult(data=result, trades=trades_df, metrics=metrics)


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def run_strategy(
    data: pd.DataFrame,
    strategy: str = "adaptive",
    window: int = 20,
    num_std: float = 2.0,
    price_col: str = "close",
    initial_capital: float = 1.0,
    exit_plan: ExitPlan | None = None,
    use_explicit_exits: bool = True,
    adaptive_config: AdaptiveRegimeConfig | None = None,
) -> BacktestResult:
    """Calculate indicators, generate signals, and run the backtest."""
    adaptive_strategies = {
        "adaptive": "hybrid",
        "adaptive_mean_reversion": "mean_reversion",
        "adaptive_breakout": "breakout",
    }
    if strategy in adaptive_strategies:
        config = adaptive_config or AdaptiveRegimeConfig(bb_window=window, bb_num_std=num_std)
        if strategy != "adaptive":
            config = replace(config, regime_mode=adaptive_strategies[strategy])
        signaled = generate_adaptive_bollinger_signals(
            data,
            config=config,
            price_col=price_col,
        )
    elif strategy == "mean_reversion":
        enriched = calculate_bollinger_bands(data, window=window, num_std=num_std, price_col=price_col)
        signaled = generate_mean_reversion_signals(enriched, price_col=price_col)
    elif strategy == "bbma":
        enriched = calculate_bollinger_bands(data, window=window, num_std=num_std, price_col=price_col)
        signaled = generate_bbma_signals(enriched, price_col=price_col)
    elif strategy == "bb_rsi":
        enriched = calculate_bollinger_bands(data, window=window, num_std=num_std, price_col=price_col)
        signaled = generate_bb_rsi_signals(enriched, price_col=price_col)
    else:
        raise ValueError("strategy must be one of: mean_reversion, bbma, bb_rsi, adaptive, adaptive_mean_reversion, adaptive_breakout")

    if use_explicit_exits:
        return backtest_entries_with_exits(signaled, exit_plan=exit_plan, price_col=price_col, initial_capital=initial_capital)
    return backtest_signals(signaled, price_col=price_col, initial_capital=initial_capital)


def optimize_bollinger_parameters(
    data: pd.DataFrame,
    strategy: str = "adaptive",
    windows: Iterable[int] = (10, 20, 30),
    num_stds: Iterable[float] = (1.5, 2.0, 2.5),
    atr_stop_multipliers: Iterable[float] = (1.5, 2.0, 2.5),
    take_profit_rrs: Iterable[float] = (1.5, 2.0, 3.0),
    initial_capital: float = 1.0,
    score_col: str = "relative_roi",
) -> pd.DataFrame:
    """Grid-search entry and exit parameters and return sorted metrics.

    This is research tooling, not live optimization. Use walk-forward validation
    before trusting any chosen parameter set.
    """
    rows: list[dict[str, float | int]] = []
    for window in windows:
        for num_std in num_stds:
            for atr_stop_multiplier in atr_stop_multipliers:
                for take_profit_rr in take_profit_rrs:
                    exit_plan = ExitPlan(
                        atr_stop_multiplier=float(atr_stop_multiplier),
                        take_profit_rr=float(take_profit_rr),
                    )
                    result = run_strategy(
                        data,
                        strategy=strategy,
                        window=int(window),
                        num_std=float(num_std),
                        initial_capital=initial_capital,
                        exit_plan=exit_plan,
                    )
                    row: dict[str, float | int] = {
                        "window": int(window),
                        "num_std": float(num_std),
                        "atr_stop_multiplier": float(atr_stop_multiplier),
                        "take_profit_rr": float(take_profit_rr),
                    }
                    row.update(result.metrics)
                    rows.append(row)

    results = pd.DataFrame(rows)
    if score_col not in results.columns:
        raise ValueError(f"score_col must be one of: {list(results.columns)}")
    return results.sort_values(score_col, ascending=False).reset_index(drop=True)


def load_ohlcv_csv(path: str | Path, date_col: str | None = None) -> pd.DataFrame:
    """Load a standard OHLCV CSV and normalize column names to lowercase."""
    data = pd.read_csv(path)
    data.columns = [column.strip().lower() for column in data.columns]

    if date_col:
        normalized_date_col = date_col.lower()
        data[normalized_date_col] = pd.to_datetime(data[normalized_date_col])
        data = data.set_index(normalized_date_col)

    _require_columns(data, ("open", "high", "low", "close", "volume"))
    return data.sort_index()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest Bollinger Bands strategies on OHLCV CSV data.")
    parser.add_argument("csv", type=Path, help="Path to an OHLCV CSV file.")
    parser.add_argument("--date-col", default=None, help="Optional datetime column to use as index.")
    parser.add_argument(
        "--strategy",
        choices=("mean_reversion", "bbma", "bb_rsi", "adaptive"),
        default="adaptive",
        help="Signal module to backtest.",
    )
    parser.add_argument("--window", type=int, default=20, help="Bollinger SMA/std window.")
    parser.add_argument("--num-std", type=float, default=2.0, help="Bollinger standard deviation multiplier.")
    parser.add_argument("--initial-capital", type=float, default=1.0, help="Starting equity for relative ROI.")
    parser.add_argument("--legacy-flip-backtest", action="store_true", help="Use old signal-flip backtest.")
    parser.add_argument("--atr-length", type=int, default=14, help="ATR period for exit rules.")
    parser.add_argument("--atr-stop-mult", type=float, default=2.0, help="ATR stop-loss multiplier.")
    parser.add_argument("--take-profit-rr", type=float, default=2.0, help="Risk/reward take-profit target.")
    parser.add_argument("--trailing-atr-mult", type=float, default=2.5, help="ATR trailing stop multiplier.")
    parser.add_argument("--trail-activation-rr", type=float, default=1.0, help="R multiple before trailing activates.")
    parser.add_argument("--max-hold-bars", type=int, default=50, help="Exit losing trades after this many bars.")
    parser.add_argument("--rsi-oversold", type=float, default=30.0, help="Adaptive strategy oversold RSI threshold.")
    parser.add_argument("--rsi-overbought", type=float, default=70.0, help="Adaptive strategy overbought RSI threshold.")
    parser.add_argument("--bandwidth-lookback", type=int, default=120, help="Adaptive strategy bandwidth quantile lookback.")
    parser.add_argument("--squeeze-quantile", type=float, default=0.20, help="Adaptive strategy squeeze quantile.")
    parser.add_argument("--wide-quantile", type=float, default=0.60, help="Adaptive strategy wide-bandwidth quantile.")
    parser.add_argument("--squeeze-release-bars", type=int, default=5, help="Bars after squeeze eligible for breakout.")
    parser.add_argument("--breakout-buffer", type=float, default=0.0, help="Required close beyond band as decimal buffer.")
    parser.add_argument("--require-volume-confirmation", action="store_true", help="Require breakout volume above baseline.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    data = load_ohlcv_csv(args.csv, date_col=args.date_col)
    exit_plan = ExitPlan(
        atr_length=args.atr_length,
        atr_stop_multiplier=args.atr_stop_mult,
        take_profit_rr=args.take_profit_rr,
        trailing_atr_multiplier=args.trailing_atr_mult,
        trail_activation_rr=args.trail_activation_rr,
        max_hold_bars=args.max_hold_bars,
    )
    adaptive_config = AdaptiveRegimeConfig(
        bb_window=args.window,
        bb_num_std=args.num_std,
        rsi_oversold=args.rsi_oversold,
        rsi_overbought=args.rsi_overbought,
        bandwidth_lookback=args.bandwidth_lookback,
        squeeze_quantile=args.squeeze_quantile,
        wide_quantile=args.wide_quantile,
        squeeze_release_bars=args.squeeze_release_bars,
        breakout_buffer=args.breakout_buffer,
        require_volume_confirmation=args.require_volume_confirmation,
    )
    result = run_strategy(
        data,
        strategy=args.strategy,
        window=args.window,
        num_std=args.num_std,
        initial_capital=args.initial_capital,
        exit_plan=exit_plan,
        adaptive_config=adaptive_config,
        use_explicit_exits=not args.legacy_flip_backtest,
    )

    print("Backtest metrics")
    for key, value in result.metrics.items():
        print(f"{key}: {value}")

    if not result.trades.empty:
        print("\nTrades")
        print(result.trades.to_string(index=False))


if __name__ == "__main__":
    main()
