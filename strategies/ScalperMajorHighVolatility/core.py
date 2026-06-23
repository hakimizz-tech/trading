"""Research implementation of the Scalper Major high-volatility strategy.

This module turns the paper's MT5 Expert Advisor idea into testable pandas code:
- RSI and SMA-20 extension as the technical heuristic
- Marubozu candlestick confirmation
- volatility/risk-aware filtering
- progressive lot-sizing and recovery-sequence helpers
- practical single-position backtesting with ATR exits

The grid/martingale recovery behavior from the paper is represented as sizing
helpers and metadata. It is deliberately not wired into live execution here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

import numpy as np
import pandas as pd


TIMEFRAME_RULES: dict[str, str] = {
    "m1": "1min",
    "m5": "5min",
    "m15": "15min",
    "m30": "30min",
    "h1": "1h",
    "h4": "4h",
    "d1": "1D",
}


@dataclass(frozen=True)
class ScalperMajorConfig:
    """Configuration for the paper-inspired Scalper Major research strategy."""

    rsi_period: int = 14
    sma_period: int = 20
    atr_period: int = 14
    oversold_rsi: float = 30.0
    overbought_rsi: float = 70.0
    exit_rsi_midline: float = 50.0
    min_sma_distance_atr: float = 0.25
    min_body_to_range: float = 0.75
    max_wick_to_range: float = 0.15
    stop_atr_multiple: float = 1.5
    take_profit_atr_multiple: float = 1.0
    max_holding_bars: int = 12
    allow_short: bool = True
    initial_cash: float = 20_000.0
    risk_fraction: float = 0.01
    max_symbol_drawdown: float = 0.10
    max_global_drawdown: float = 0.25
    commission_per_turnover: float = 0.00007
    slippage: float = 0.00005
    annualization: int = 252
    base_lot: float = 0.01
    base_capital_threshold: float = 1_000.0
    rebalance_threshold: float = 10_000.0
    rebalance_increment: float = 1_000.0
    max_recovery_positions: int = 14
    use_talib: bool = True

    def __post_init__(self) -> None:
        if self.rsi_period <= 0 or self.sma_period <= 0 or self.atr_period <= 0:
            raise ValueError("indicator periods must be positive")
        if not 0 <= self.oversold_rsi < self.overbought_rsi <= 100:
            raise ValueError("RSI thresholds must satisfy 0 <= oversold < overbought <= 100")
        if not 0 <= self.exit_rsi_midline <= 100:
            raise ValueError("exit_rsi_midline must be between 0 and 100")
        if self.min_sma_distance_atr < 0:
            raise ValueError("min_sma_distance_atr must not be negative")
        if not 0 <= self.min_body_to_range <= 1:
            raise ValueError("min_body_to_range must be between 0 and 1")
        if not 0 <= self.max_wick_to_range <= 1:
            raise ValueError("max_wick_to_range must be between 0 and 1")
        if self.stop_atr_multiple <= 0 or self.take_profit_atr_multiple <= 0:
            raise ValueError("ATR exit multiples must be positive")
        if self.max_holding_bars <= 0:
            raise ValueError("max_holding_bars must be positive")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not 0 < self.risk_fraction <= 1:
            raise ValueError("risk_fraction must be in (0, 1]")
        if self.max_symbol_drawdown <= 0 or self.max_global_drawdown <= 0:
            raise ValueError("drawdown limits must be positive")
        if self.commission_per_turnover < 0 or self.slippage < 0:
            raise ValueError("costs must not be negative")

    @property
    def required_history(self) -> int:
        return max(self.rsi_period + 1, self.sma_period, self.atr_period + 1)


@dataclass(frozen=True)
class ScalperMajorResult:
    """Backtest artifacts for Scalper Major research runs."""

    data: pd.DataFrame
    indicators: pd.DataFrame
    signals: pd.DataFrame
    returns: pd.Series
    equity: pd.Series
    drawdown: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, Any]
    config: ScalperMajorConfig


class _OpenPosition(TypedDict):
    direction: int
    entry_price: float
    entry_timestamp: object
    entry_equity: float
    weight: float
    bars_held: int


def compute_scalper_major_indicators(
    ohlcv: pd.DataFrame,
    config: ScalperMajorConfig | None = None,
) -> pd.DataFrame:
    """Compute RSI, SMA, ATR, Marubozu, and volatility-regime features."""
    cfg = config or ScalperMajorConfig()
    data = validate_ohlcv(ohlcv)
    close = data["close"]
    returns = close.pct_change(fill_method=None)
    talib = _optional_talib() if cfg.use_talib else None
    sma = compute_sma(close, cfg.sma_period, talib=talib)
    rsi = compute_rsi(close, cfg.rsi_period, talib=talib)
    atr = compute_atr(data, cfg.atr_period, talib=talib)
    distance_atr = (close - sma) / atr.replace(0.0, np.nan)
    realized_vol = returns.rolling(cfg.sma_period).std(ddof=0)
    vol_percentile = rolling_percentile(realized_vol, window=max(cfg.sma_period * 5, 50))

    candle_range = (data["high"] - data["low"]).replace(0.0, np.nan)
    body = (data["close"] - data["open"]).abs()
    upper_wick = data["high"] - data[["open", "close"]].max(axis=1)
    lower_wick = data[["open", "close"]].min(axis=1) - data["low"]
    body_ratio = body / candle_range
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range
    bullish_marubozu, bearish_marubozu = detect_marubozu(data, cfg, talib=talib)

    return pd.DataFrame(
        {
            "sma": sma,
            "rsi": rsi,
            "atr": atr,
            "sma_distance_atr": distance_atr,
            "realized_vol": realized_vol,
            "vol_percentile": vol_percentile,
            "body_ratio": body_ratio,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "bullish_marubozu": bullish_marubozu.fillna(False),
            "bearish_marubozu": bearish_marubozu.fillna(False),
            "indicator_backend": "ta-lib" if talib is not None else "pandas",
        },
        index=data.index,
    )


def generate_scalper_major_signals(
    ohlcv: pd.DataFrame,
    config: ScalperMajorConfig | None = None,
) -> pd.DataFrame:
    """Generate long/short entries and exits from paper-inspired rules."""
    cfg = config or ScalperMajorConfig()
    indicators = compute_scalper_major_indicators(ohlcv, cfg)
    long_entry = (
        indicators["rsi"].lt(cfg.oversold_rsi)
        & indicators["sma_distance_atr"].le(-cfg.min_sma_distance_atr)
        & indicators["bearish_marubozu"]
    )
    short_entry = (
        indicators["rsi"].gt(cfg.overbought_rsi)
        & indicators["sma_distance_atr"].ge(cfg.min_sma_distance_atr)
        & indicators["bullish_marubozu"]
        & bool(cfg.allow_short)
    )
    long_exit = indicators["rsi"].ge(cfg.exit_rsi_midline) | short_entry
    short_exit = indicators["rsi"].le(cfg.exit_rsi_midline) | long_entry
    return pd.DataFrame(
        {
            "long_entry": long_entry.fillna(False),
            "long_exit": long_exit.fillna(False),
            "short_entry": short_entry.fillna(False),
            "short_exit": short_exit.fillna(False),
            "approved_by_risk": True,
        },
        index=indicators.index,
    )


def generate_scalper_major_ml_filtered_signals(
    ohlcv: pd.DataFrame,
    ml_artifact: Any,
    config: ScalperMajorConfig | None = None,
    *,
    threshold: float | None = None,
) -> pd.DataFrame:
    """Generate Scalper Major signals filtered by Directional Forex ML.

    The base RSI/SMA/Marubozu signal is accepted only when the ML classifier
    agrees with direction and the expected move clears transaction costs.
    """
    base = generate_scalper_major_signals(ohlcv, config)
    from strategies.DirectionalForexML import build_ml_gate_for_signals

    gate = build_ml_gate_for_signals(
        ohlcv=ohlcv,
        base_signals=base,
        artifact=ml_artifact,
        threshold=threshold,
    )
    filtered = base.copy()
    filtered["ml_probability_up"] = gate["ml_probability_up"].reindex(filtered.index)
    filtered["ml_expected_move_pct"] = gate["ml_expected_move_pct"].reindex(filtered.index)
    filtered["ml_cost_hurdle_pct"] = gate["ml_cost_hurdle_pct"].reindex(filtered.index)
    filtered["base_long_entry"] = filtered["long_entry"]
    filtered["base_short_entry"] = filtered["short_entry"]
    filtered["long_entry"] = filtered["long_entry"] & gate["ml_long_approved"].reindex(filtered.index, fill_value=False)
    filtered["short_entry"] = filtered["short_entry"] & gate["ml_short_approved"].reindex(filtered.index, fill_value=False)
    return filtered


def backtest_scalper_major(
    ohlcv: pd.DataFrame,
    config: ScalperMajorConfig | None = None,
    *,
    trade_start: pd.Timestamp | str | None = None,
) -> ScalperMajorResult:
    """Run a conservative one-position-at-a-time research backtest."""
    cfg = config or ScalperMajorConfig()
    data = validate_ohlcv(ohlcv)
    indicators = compute_scalper_major_indicators(data, cfg)
    signals = generate_scalper_major_signals(data, cfg)
    start_timestamp = pd.Timestamp(trade_start) if trade_start is not None else None

    returns = pd.Series(0.0, index=data.index, name="returns")
    equity = pd.Series(cfg.initial_cash, index=data.index, name="equity")
    position: _OpenPosition | None = None
    trade_rows: list[dict[str, object]] = []

    for i, timestamp in enumerate(data.index):
        price = float(data["close"].iloc[i])
        atr = float(indicators["atr"].iloc[i]) if pd.notna(indicators["atr"].iloc[i]) else np.nan
        previous_equity = float(equity.iloc[i - 1]) if i > 0 else cfg.initial_cash
        current_equity = previous_equity
        can_trade = start_timestamp is None or pd.Timestamp(timestamp) >= start_timestamp

        if position is not None:
            direction = int(position["direction"])
            entry_price = float(position["entry_price"])
            entry_equity = float(position["entry_equity"])
            bars_held = int(position["bars_held"]) + 1
            raw_return = direction * (price / entry_price - 1.0)
            current_equity = entry_equity * (1.0 + raw_return * float(position["weight"]))
            exit_reason = _exit_reason(direction, signals.iloc[i], price, entry_price, atr, bars_held, cfg)
            if exit_reason:
                cost = cfg.commission_per_turnover + cfg.slippage
                trade_return = raw_return * float(position["weight"]) - cost
                current_equity = entry_equity * (1.0 + trade_return)
                trade_rows.append(
                    {
                        "entry_timestamp": position["entry_timestamp"],
                        "exit_timestamp": timestamp,
                        "direction": "long" if direction > 0 else "short",
                        "entry_price": entry_price,
                        "exit_price": price,
                        "bars_held": bars_held,
                        "weight": float(position["weight"]),
                        "return_pct": trade_return * 100.0,
                        "pnl": current_equity - entry_equity,
                        "exit_reason": exit_reason,
                    }
                )
                position = None
            else:
                position["bars_held"] = bars_held

        if can_trade and position is None and i >= cfg.required_history:
            portfolio_drawdown = current_equity / max(float(equity.iloc[: i + 1].max()), cfg.initial_cash) - 1.0
            if portfolio_drawdown > -cfg.max_global_drawdown:
                direction = 0
                if bool(signals["long_entry"].iloc[i]):
                    direction = 1
                elif bool(signals["short_entry"].iloc[i]):
                    direction = -1
                if direction != 0 and pd.notna(atr) and atr > 0:
                    stop_distance_pct = cfg.stop_atr_multiple * atr / price
                    weight = min(1.0, cfg.risk_fraction / max(stop_distance_pct, 1e-12))
                    position = {
                        "direction": direction,
                        "entry_price": price,
                        "entry_timestamp": timestamp,
                        "entry_equity": current_equity,
                        "weight": weight,
                        "bars_held": 0,
                    }

        equity.iloc[i] = current_equity
        if i > 0:
            returns.iloc[i] = equity.iloc[i] / equity.iloc[i - 1] - 1.0

    drawdown = equity / equity.cummax() - 1.0
    trades = pd.DataFrame(trade_rows)
    metrics = compute_scalper_major_metrics(returns, equity, drawdown, trades, cfg)
    return ScalperMajorResult(data, indicators, signals, returns, equity, drawdown, trades, metrics, cfg)


def compute_scalper_major_metrics(
    returns: pd.Series,
    equity: pd.Series,
    drawdown: pd.Series,
    trades: pd.DataFrame,
    config: ScalperMajorConfig | None = None,
) -> dict[str, float | int | None]:
    """Compute the paper's return, risk, and risk-adjusted metrics."""
    cfg = config or ScalperMajorConfig()
    clean_returns = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) else 0.0
    periods = max(len(clean_returns), 1)
    annualized_return = float((1.0 + total_return) ** (cfg.annualization / periods) - 1.0)
    volatility = float(clean_returns.std(ddof=0) * np.sqrt(cfg.annualization))
    sharpe = float(clean_returns.mean() / clean_returns.std(ddof=0) * np.sqrt(cfg.annualization)) if clean_returns.std(ddof=0) > 0 else None
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
    gross_profit = gross_loss = 0.0
    win_rate = expected_payoff = profit_factor = recovery_factor = None
    if not trades.empty:
        pnl = pd.to_numeric(trades["pnl"], errors="coerce").fillna(0.0)
        gross_profit = float(pnl[pnl > 0].sum())
        gross_loss = float(abs(pnl[pnl < 0].sum()))
        win_rate = float((pnl > 0).mean())
        expected_payoff = float(pnl.mean())
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else None
    net_profit = float(equity.iloc[-1] - equity.iloc[0]) if len(equity) else 0.0
    recovery_factor = float(net_profit / abs(max_drawdown * equity.iloc[0])) if max_drawdown < 0 and len(equity) else None
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "profit_factor": profit_factor,
        "expected_payoff": expected_payoff,
        "recovery_factor": recovery_factor,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": net_profit,
        "win_rate": win_rate,
        "trade_count": int(len(trades)),
    }


def resample_ohlcv_timeframes(
    ohlcv: pd.DataFrame,
    *,
    timeframes: tuple[str, ...] = ("m1", "m5", "m15", "m30", "h1", "h4", "d1"),
) -> dict[str, pd.DataFrame]:
    """Resample canonical OHLCV data from M1-style input up to D1."""
    data = validate_ohlcv(ohlcv)
    frames: dict[str, pd.DataFrame] = {}
    for timeframe in timeframes:
        rule = TIMEFRAME_RULES.get(timeframe.lower(), timeframe)
        frames[timeframe.lower()] = (
            data.resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna(subset=["open", "high", "low", "close"])
        )
    return frames


def recovery_lot_sequence(base_lot: float = 0.01, *, max_positions: int = 14) -> list[float]:
    """Return the paper's paired martingale sequence: 0.01, 0.01, 0.02, 0.02..."""
    if base_lot <= 0:
        raise ValueError("base_lot must be positive")
    if max_positions <= 0:
        raise ValueError("max_positions must be positive")
    return [float(base_lot * (2 ** (i // 2))) for i in range(max_positions)]


def progressive_lot_size(
    historical_profit: float,
    *,
    base_lot: float = 0.01,
    base_capital_threshold: float = 1_000.0,
    rebalance_threshold: float = 10_000.0,
    rebalance_increment: float = 1_000.0,
) -> float:
    """Compute the paper's progressive lot size from accumulated profit."""
    if base_lot <= 0:
        raise ValueError("base_lot must be positive")
    if base_capital_threshold <= 0:
        raise ValueError("base_capital_threshold must be positive")
    if rebalance_threshold < 0 or rebalance_increment < 0:
        raise ValueError("rebalance inputs must not be negative")
    profit = max(0.0, float(historical_profit))
    rebalance_count = int(np.floor(profit / rebalance_threshold)) if rebalance_threshold > 0 else 0
    adjusted_base = base_capital_threshold + rebalance_increment * rebalance_count
    if profit < adjusted_base:
        return 0.0
    return float(base_lot * np.floor(profit / adjusted_base))


def compute_sma(close: pd.Series, period: int, *, talib: Any | None = None) -> pd.Series:
    if talib is not None:
        values = talib.SMA(close.to_numpy(dtype=np.float64), timeperiod=period)
        return pd.Series(values, index=close.index, name="sma")
    return close.rolling(period).mean()


def compute_rsi(close: pd.Series, period: int, *, talib: Any | None = None) -> pd.Series:
    if talib is not None:
        values = talib.RSI(close.to_numpy(dtype=np.float64), timeperiod=period)
        return pd.Series(values, index=close.index, name="rsi").fillna(50.0)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def compute_atr(ohlcv: pd.DataFrame, period: int, *, talib: Any | None = None) -> pd.Series:
    if talib is not None:
        values = talib.ATR(
            ohlcv["high"].to_numpy(dtype=np.float64),
            ohlcv["low"].to_numpy(dtype=np.float64),
            ohlcv["close"].to_numpy(dtype=np.float64),
            timeperiod=period,
        )
        return pd.Series(values, index=ohlcv.index, name="atr")
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    true_range = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def detect_marubozu(
    ohlcv: pd.DataFrame,
    config: ScalperMajorConfig,
    *,
    talib: Any | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Detect Marubozu using TA-Lib when available, else body/wick rules."""
    talib_bullish = pd.Series(False, index=ohlcv.index)
    talib_bearish = pd.Series(False, index=ohlcv.index)
    if talib is not None and hasattr(talib, "CDLMARUBOZU"):
        values = talib.CDLMARUBOZU(
            ohlcv["open"].to_numpy(dtype=np.float64),
            ohlcv["high"].to_numpy(dtype=np.float64),
            ohlcv["low"].to_numpy(dtype=np.float64),
            ohlcv["close"].to_numpy(dtype=np.float64),
        )
        pattern = pd.Series(values, index=ohlcv.index)
        talib_bullish = pattern.gt(0)
        talib_bearish = pattern.lt(0)

    candle_range = (ohlcv["high"] - ohlcv["low"]).replace(0.0, np.nan)
    body = (ohlcv["close"] - ohlcv["open"]).abs()
    upper_wick = ohlcv["high"] - ohlcv[["open", "close"]].max(axis=1)
    lower_wick = ohlcv[["open", "close"]].min(axis=1) - ohlcv["low"]
    body_ratio = body / candle_range
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range
    bullish = (
        ohlcv["close"].gt(ohlcv["open"])
        & body_ratio.ge(config.min_body_to_range)
        & upper_wick_ratio.le(config.max_wick_to_range)
        & lower_wick_ratio.le(config.max_wick_to_range)
    )
    bearish = (
        ohlcv["close"].lt(ohlcv["open"])
        & body_ratio.ge(config.min_body_to_range)
        & upper_wick_ratio.le(config.max_wick_to_range)
        & lower_wick_ratio.le(config.max_wick_to_range)
    )
    return bullish | talib_bullish, bearish | talib_bearish


def rolling_percentile(series: pd.Series, *, window: int) -> pd.Series:
    def percentile(values: np.ndarray) -> float:
        current = values[-1]
        if np.isnan(current):
            return np.nan
        return float(np.mean(values <= current))

    return series.rolling(window, min_periods=max(5, window // 5)).apply(percentile, raw=True)


def validate_ohlcv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(ohlcv, pd.DataFrame):
        raise TypeError("ohlcv must be a pandas DataFrame")
    missing = {"open", "high", "low", "close", "volume"} - set(ohlcv.columns)
    if missing:
        raise ValueError(f"ohlcv missing required columns: {sorted(missing)}")
    data = ohlcv.loc[:, ["open", "high", "low", "close", "volume"]].copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index, errors="coerce")
    data = data.dropna(axis=0, subset=["open", "high", "low", "close"]).sort_index()
    data = data.loc[~data.index.duplicated(keep="last")]
    for column in data.columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=["open", "high", "low", "close"])


def _optional_talib() -> Any | None:
    try:
        import talib
    except ImportError:
        return None
    return talib


def _exit_reason(
    direction: int,
    signal_row: pd.Series,
    price: float,
    entry_price: float,
    atr: float,
    bars_held: int,
    config: ScalperMajorConfig,
) -> Literal["signal_exit", "stop_loss", "take_profit", "time_stop"] | None:
    if direction > 0 and bool(signal_row["long_exit"]):
        return "signal_exit"
    if direction < 0 and bool(signal_row["short_exit"]):
        return "signal_exit"
    if pd.notna(atr) and atr > 0:
        if direction > 0 and price <= entry_price - config.stop_atr_multiple * atr:
            return "stop_loss"
        if direction < 0 and price >= entry_price + config.stop_atr_multiple * atr:
            return "stop_loss"
        if direction > 0 and price >= entry_price + config.take_profit_atr_multiple * atr:
            return "take_profit"
        if direction < 0 and price <= entry_price - config.take_profit_atr_multiple * atr:
            return "take_profit"
    if bars_held >= config.max_holding_bars:
        return "time_stop"
    return None
