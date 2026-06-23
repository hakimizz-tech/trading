"""Connors Research Dynamic Treasuries strategy.

The strategy is a long-only weekly US Treasury duration-rotation system:
- IEF, TLH, and TLT each receive 0-25% allocation in 5% increments
- each positive trailing 1/2/3/4/5-month return contributes 5%
- any residual allocation goes to IEI as the short-duration anchor
- the portfolio is always fully invested in Treasury ETFs
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_data.ohlcv import load_ohlcv_csv


TREASURY_ANCHOR = "IEI"
TREASURY_DURATION_ASSETS: tuple[str, ...] = ("IEF", "TLH", "TLT")
DYNAMIC_TREASURIES_UNIVERSE: tuple[str, ...] = (TREASURY_ANCHOR, *TREASURY_DURATION_ASSETS)
TREASURY_DURATIONS: dict[str, float] = {
    "IEI": 4.5,
    "IEF": 7.5,
    "TLH": 11.5,
    "TLT": 17.4,
}


@dataclass(frozen=True)
class DynamicTreasuriesConfig:
    """Configuration for Connors Research Dynamic Treasuries."""

    anchor_symbol: str = TREASURY_ANCHOR
    duration_assets: tuple[str, ...] = TREASURY_DURATION_ASSETS
    momentum_lookbacks: tuple[int, ...] = (21, 42, 63, 84, 105)
    signal_weight: float = 0.05
    rebalance_frequency: str = "W-FRI"
    initial_cash: float = 10_000.0
    trading_cost: float = 0.0
    annualization: int = 252
    live_required_symbols: tuple[str, ...] = DYNAMIC_TREASURIES_UNIVERSE

    def __post_init__(self) -> None:
        if not self.duration_assets:
            raise ValueError("duration_assets must not be empty")
        if self.anchor_symbol in self.duration_assets:
            raise ValueError("anchor_symbol must not be included in duration_assets")
        if not self.momentum_lookbacks:
            raise ValueError("momentum_lookbacks must not be empty")
        if any(lookback <= 0 for lookback in self.momentum_lookbacks):
            raise ValueError("momentum_lookbacks must be positive")
        if self.signal_weight <= 0:
            raise ValueError("signal_weight must be positive")
        if self.signal_weight * len(self.momentum_lookbacks) * len(self.duration_assets) > 1.0:
            raise ValueError("signal weights can allocate more than 100%")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.trading_cost < 0:
            raise ValueError("trading_cost must not be negative")
        if self.annualization <= 0:
            raise ValueError("annualization must be positive")

    @property
    def required_history(self) -> int:
        return max(self.momentum_lookbacks)

    @property
    def symbols(self) -> tuple[str, ...]:
        return (self.anchor_symbol, *self.duration_assets)


@dataclass(frozen=True)
class DynamicTreasuriesBacktestResult:
    """Backtest artifacts for Dynamic Treasuries."""

    prices: pd.DataFrame
    momentum_returns: pd.DataFrame
    positive_signal_counts: pd.DataFrame
    target_weights: pd.DataFrame
    weights: pd.DataFrame
    duration_exposure: pd.Series
    returns: pd.Series
    equity: pd.Series
    drawdown: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, float | int | None]
    asset_performance: pd.DataFrame
    config: DynamicTreasuriesConfig


def load_dynamic_treasuries_prices(
    paths: Mapping[str, str | Path] | Sequence[str | Path],
    *,
    join: str = "inner",
) -> pd.DataFrame:
    """Load Treasury ETF OHLCV CSVs and return an aligned close matrix."""
    if isinstance(paths, Mapping):
        items = list(paths.items())
    else:
        items = [(Path(path).parent.name.upper().replace(" ", "_"), path) for path in paths]
    if not items:
        raise ValueError("paths must not be empty")

    series = []
    for symbol, path in items:
        frame = load_ohlcv_csv(path, symbol=symbol)
        series.append(frame["close"].rename(symbol))
    prices = pd.concat(series, axis=1).sort_index().ffill()
    if join == "inner":
        prices = prices.dropna(how="any")
    elif join == "outer":
        prices = prices.dropna(how="all")
    else:
        raise ValueError("join must be 'inner' or 'outer'")
    return _validate_prices(prices)


def compute_momentum_returns(
    prices: pd.DataFrame,
    config: DynamicTreasuriesConfig | None = None,
) -> pd.DataFrame:
    """Compute trailing total returns for each duration ETF/lookback pair."""
    cfg = config or DynamicTreasuriesConfig()
    clean = _validate_prices(prices)
    missing = [symbol for symbol in cfg.duration_assets if symbol not in clean.columns]
    if missing:
        raise ValueError(f"prices missing duration assets: {missing}")
    frames: list[pd.DataFrame] = []
    for lookback in cfg.momentum_lookbacks:
        returns = clean.loc[:, cfg.duration_assets] / clean.loc[:, cfg.duration_assets].shift(lookback) - 1.0
        returns.columns = pd.MultiIndex.from_product([[lookback], returns.columns], names=["lookback", "symbol"])
        frames.append(returns)
    return pd.concat(frames, axis=1).sort_index(axis=1)


def compute_positive_signal_counts(
    prices: pd.DataFrame,
    config: DynamicTreasuriesConfig | None = None,
) -> pd.DataFrame:
    """Count positive momentum lookbacks for each duration ETF."""
    cfg = config or DynamicTreasuriesConfig()
    momentum = compute_momentum_returns(prices, cfg)
    counts = pd.DataFrame(0, index=momentum.index, columns=list(cfg.duration_assets), dtype=int)
    for symbol in cfg.duration_assets:
        symbol_returns = momentum.xs(symbol, axis=1, level="symbol")
        counts[symbol] = symbol_returns.gt(0.0).sum(axis=1).astype(int)
    return counts


def generate_dynamic_treasuries_target_weights(
    prices: pd.DataFrame,
    config: DynamicTreasuriesConfig | None = None,
    *,
    trade_start: pd.Timestamp | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate weekly target weights and rebalance rows from strategy rules."""
    cfg = config or DynamicTreasuriesConfig()
    clean = _validate_prices(prices)
    _require_symbols(clean, cfg)
    start_timestamp = pd.Timestamp(trade_start) if trade_start is not None else None
    counts = compute_positive_signal_counts(clean, cfg)
    rebalance_dates = set(_rebalance_dates(clean, cfg.rebalance_frequency))
    target = pd.DataFrame(0.0, index=clean.index, columns=list(cfg.symbols))
    target[cfg.anchor_symbol] = 1.0
    rows: list[dict[str, Any]] = []
    previous = pd.Series(0.0, index=target.columns)
    previous[cfg.anchor_symbol] = 1.0

    for timestamp in clean.index:
        if timestamp in rebalance_dates:
            trading_enabled = start_timestamp is None or pd.Timestamp(timestamp) >= start_timestamp
            if trading_enabled and clean.index.get_loc(timestamp) >= cfg.required_history:
                weights = pd.Series(0.0, index=target.columns, dtype=float)
                for symbol in cfg.duration_assets:
                    weights[symbol] = float(counts.loc[timestamp, symbol]) * cfg.signal_weight
                weights[cfg.anchor_symbol] = max(0.0, 1.0 - float(weights.loc[list(cfg.duration_assets)].sum()))
                target.loc[timestamp] = weights
                changes = (weights - previous).replace(0.0, np.nan).dropna()
                for symbol, delta in changes.items():
                    rows.append(
                        {
                            "timestamp": timestamp,
                            "symbol": symbol,
                            "action": "BUY" if float(delta) > 0 else "SELL",
                            "price": float(clean.loc[timestamp, symbol]),
                            "target_weight": float(weights[symbol]),
                            "weight_change": float(delta),
                            "reason": "weekly_duration_rebalance",
                        }
                    )
                previous = weights
        else:
            target.loc[timestamp] = previous

    target = target.ffill().fillna(0.0)
    trades = pd.DataFrame(
        rows,
        columns=["timestamp", "symbol", "action", "price", "target_weight", "weight_change", "reason"],
    )
    if not trades.empty:
        trades["trade_id"] = trades["timestamp"].astype(str) + ":" + trades["symbol"].astype(str)
        trades["side"] = "long"
        trades["size"] = trades["weight_change"].abs()
        trades["pnl"] = pd.NA
        trades["return_pct"] = pd.NA
        trades["status"] = "rebalance"
    return target, trades


def backtest_dynamic_treasuries(
    prices: pd.DataFrame,
    config: DynamicTreasuriesConfig | None = None,
    *,
    trade_start: pd.Timestamp | str | None = None,
) -> DynamicTreasuriesBacktestResult:
    """Backtest Dynamic Treasuries with one-bar delayed weekly target weights."""
    cfg = config or DynamicTreasuriesConfig()
    clean = _validate_prices(prices)
    _require_symbols(clean, cfg)
    momentum = compute_momentum_returns(clean, cfg)
    counts = compute_positive_signal_counts(clean, cfg)
    target_weights, trades = generate_dynamic_treasuries_target_weights(clean, cfg, trade_start=trade_start)
    weights = target_weights.shift(1).fillna(0.0)
    asset_returns = clean.loc[:, target_weights.columns].pct_change(fill_method=None).fillna(0.0)
    gross_returns = (weights * asset_returns).sum(axis=1)
    turnover = target_weights.diff().abs().sum(axis=1).fillna(target_weights.abs().sum(axis=1))
    net_returns = gross_returns - turnover.shift(1).fillna(0.0) * cfg.trading_cost
    equity = cfg.initial_cash * (1.0 + net_returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    duration_exposure = compute_duration_exposure(weights)
    asset_performance = compute_asset_performance(clean.loc[:, target_weights.columns], weights, cfg)
    metrics = compute_portfolio_metrics(net_returns, equity, drawdown, trades, cfg)
    return DynamicTreasuriesBacktestResult(
        prices=clean.loc[:, target_weights.columns],
        momentum_returns=momentum,
        positive_signal_counts=counts,
        target_weights=target_weights,
        weights=weights,
        duration_exposure=duration_exposure,
        returns=net_returns,
        equity=equity,
        drawdown=drawdown,
        trades=trades,
        metrics=metrics,
        asset_performance=asset_performance,
        config=cfg,
    )


def compute_duration_exposure(weights: pd.DataFrame, durations: dict[str, float] | None = None) -> pd.Series:
    """Compute portfolio effective duration from target or execution weights."""
    duration_map = durations or TREASURY_DURATIONS
    aligned = pd.Series(duration_map).reindex(weights.columns).fillna(0.0)
    return (weights.fillna(0.0) * aligned).sum(axis=1).rename("duration_exposure")


def compute_asset_performance(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    config: DynamicTreasuriesConfig | None = None,
) -> pd.DataFrame:
    """Summarize per-ETF contribution, exposure, Sharpe, and drawdown."""
    cfg = config or DynamicTreasuriesConfig()
    clean = _validate_prices(prices).loc[:, weights.columns]
    asset_returns = clean.pct_change(fill_method=None).fillna(0.0)
    rows: list[dict[str, Any]] = []
    for symbol in weights.columns:
        symbol_weights = weights[symbol].reindex(asset_returns.index).fillna(0.0)
        contribution = symbol_weights * asset_returns[symbol]
        contribution_equity = (1.0 + contribution).cumprod()
        contribution_drawdown = contribution_equity / contribution_equity.cummax() - 1.0
        held_mask = symbol_weights.abs() > 0.0
        held_returns = asset_returns.loc[held_mask, symbol].replace([np.inf, -np.inf], np.nan).dropna()
        rows.append(
            {
                "symbol": symbol,
                "days_held": int(held_mask.sum()),
                "exposure_pct": float(held_mask.mean() * 100.0),
                "average_weight": float(symbol_weights.mean()),
                "max_weight": float(symbol_weights.max()),
                "asset_total_return_while_held": _compound_return(held_returns),
                "asset_sharpe_while_held": _series_sharpe(held_returns, cfg.annualization),
                "strategy_contribution_return": float(contribution.sum()),
                "strategy_contribution_return_pct": float(contribution.sum() * 100.0),
                "contribution_sharpe": _series_sharpe(contribution, cfg.annualization),
                "contribution_max_drawdown": float(contribution_drawdown.min()),
                "contribution_max_drawdown_pct": float(contribution_drawdown.min() * 100.0),
            }
        )
    return pd.DataFrame(rows).sort_values("strategy_contribution_return", ascending=False).reset_index(drop=True)


def build_rebalance_events(result: DynamicTreasuriesBacktestResult) -> pd.DataFrame:
    """Build rebalance-level diagnostics for an allocation strategy."""
    columns = [
        "timestamp",
        "turnover",
        "estimated_fee",
        "duration_before",
        "duration_after",
        "next_bar_return",
        "increases",
        "decreases",
    ]
    changed = result.target_weights.ne(result.target_weights.shift()).any(axis=1)
    rebalance_dates = result.target_weights.index[changed]
    if len(rebalance_dates) == 0:
        return pd.DataFrame(columns=columns)

    target_duration = compute_duration_exposure(result.target_weights)
    rows: list[dict[str, Any]] = []
    previous = pd.Series(0.0, index=result.target_weights.columns)
    previous[result.config.anchor_symbol] = 1.0
    for timestamp in rebalance_dates:
        current = result.target_weights.loc[timestamp]
        changes = current - previous
        turnover = float(changes.abs().sum())
        rows.append(
            {
                "timestamp": timestamp,
                "turnover": turnover,
                "estimated_fee": turnover * result.config.initial_cash * result.config.trading_cost,
                "duration_before": float((previous * pd.Series(TREASURY_DURATIONS).reindex(previous.index)).sum()),
                "duration_after": float(target_duration.loc[timestamp]),
                "next_bar_return": _next_value(result.returns, timestamp),
                "increases": int((changes > 0).sum()),
                "decreases": int((changes < 0).sum()),
            }
        )
        previous = current
    return pd.DataFrame(rows, columns=columns)


def summarize_rebalances(rebalance_events: pd.DataFrame) -> pd.DataFrame:
    """Return one-row rebalance diagnostics for reports."""
    columns = [
        "rebalances",
        "avg_turnover",
        "max_turnover",
        "total_estimated_fees",
        "avg_duration_before",
        "avg_duration_after",
        "avg_next_bar_return",
    ]
    if rebalance_events.empty:
        return pd.DataFrame(
            [
                {
                    "rebalances": 0,
                    "avg_turnover": 0.0,
                    "max_turnover": 0.0,
                    "total_estimated_fees": 0.0,
                    "avg_duration_before": None,
                    "avg_duration_after": None,
                    "avg_next_bar_return": None,
                }
            ],
            columns=columns,
        )
    return pd.DataFrame(
        [
            {
                "rebalances": int(len(rebalance_events)),
                "avg_turnover": float(rebalance_events["turnover"].mean()),
                "max_turnover": float(rebalance_events["turnover"].max()),
                "total_estimated_fees": float(rebalance_events["estimated_fee"].sum()),
                "avg_duration_before": float(rebalance_events["duration_before"].mean()),
                "avg_duration_after": float(rebalance_events["duration_after"].mean()),
                "avg_next_bar_return": float(rebalance_events["next_bar_return"].mean()),
            }
        ],
        columns=columns,
    )


def generate_live_rebalance_orders(
    *,
    current_weights: pd.Series,
    target_weights: pd.Series,
    portfolio_value: float,
    prices: pd.Series,
    min_weight_change: float = 0.005,
) -> pd.DataFrame:
    """Generate broker-agnostic target rebalance orders for live/paper adapters."""
    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive")
    symbols = list(dict.fromkeys([*target_weights.index, *current_weights.index, *prices.index]))
    current = current_weights.reindex(symbols).fillna(0.0).astype(float)
    target = target_weights.reindex(symbols).fillna(0.0).astype(float)
    latest_prices = prices.reindex(symbols).astype(float)
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        price = latest_prices[symbol]
        if pd.isna(price) or price <= 0:
            continue
        weight_delta = float(target[symbol] - current[symbol])
        if abs(weight_delta) < min_weight_change:
            continue
        target_value_delta = weight_delta * portfolio_value
        rows.append(
            {
                "symbol": symbol,
                "action": "BUY" if target_value_delta > 0 else "SELL",
                "current_weight": float(current[symbol]),
                "target_weight": float(target[symbol]),
                "weight_delta": weight_delta,
                "target_value_delta": target_value_delta,
                "estimated_quantity": target_value_delta / float(price),
                "price": float(price),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "symbol",
            "action",
            "current_weight",
            "target_weight",
            "weight_delta",
            "target_value_delta",
            "estimated_quantity",
            "price",
        ],
    )


def validate_live_readiness(
    prices: pd.DataFrame,
    config: DynamicTreasuriesConfig | None = None,
    *,
    broker_symbol_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return live-readiness status and blockers for Dynamic Treasuries."""
    cfg = config or DynamicTreasuriesConfig()
    clean = _validate_prices(prices)
    required = set(cfg.live_required_symbols)
    available = set(clean.columns)
    missing_data = sorted(required - available)
    symbol_map = broker_symbol_map or {}
    missing_broker_symbols = sorted(symbol for symbol in required if symbol not in symbol_map)
    enough_history = len(clean) > cfg.required_history
    blockers: list[str] = []
    if missing_data:
        blockers.append(f"missing price data for: {', '.join(missing_data)}")
    if missing_broker_symbols:
        blockers.append(f"missing broker symbol mapping for: {', '.join(missing_broker_symbols)}")
    if not enough_history:
        blockers.append(f"need more than {cfg.required_history} rows of price history")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "available_symbols": sorted(available),
        "missing_data": missing_data,
        "missing_broker_symbols": missing_broker_symbols,
        "rows": int(len(clean)),
        "required_history": int(cfg.required_history),
    }


def compute_portfolio_metrics(
    returns: pd.Series,
    equity: pd.Series,
    drawdown: pd.Series,
    trades: pd.DataFrame,
    config: DynamicTreasuriesConfig,
) -> dict[str, float | int | None]:
    """Compute core performance metrics."""
    clean_returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    rebalance_count = int(trades["timestamp"].nunique()) if not trades.empty else 0
    if clean_returns.empty:
        return {
            "total_return": None,
            "total_return_pct": None,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "max_drawdown_pct": None,
            "rebalance_count": rebalance_count,
        }
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) > 1 else 0.0
    periods = max(len(clean_returns), 1)
    annualized_return = (1.0 + total_return) ** (config.annualization / periods) - 1.0
    annualized_volatility = float(clean_returns.std(ddof=0) * math.sqrt(config.annualization))
    sharpe = annualized_return / annualized_volatility if annualized_volatility > 0 else None
    max_drawdown = float(drawdown.min())
    return {
        "total_return": total_return,
        "total_return_pct": total_return * 100.0,
        "annualized_return": float(annualized_return),
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": float(sharpe) if sharpe is not None else None,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100.0,
        "rebalance_count": rebalance_count,
    }


def _rebalance_dates(prices: pd.DataFrame, frequency: str) -> pd.DatetimeIndex:
    index = prices.index.tz_localize(None) if prices.index.tz is not None else prices.index
    periods = index.to_period(frequency)
    period_series = pd.Series(periods, index=prices.index)
    return pd.DatetimeIndex(prices.index[period_series.ne(period_series.shift(-1))])


def _require_symbols(prices: pd.DataFrame, config: DynamicTreasuriesConfig) -> None:
    missing = [symbol for symbol in config.symbols if symbol not in prices.columns]
    if missing:
        raise ValueError(f"prices missing required symbols: {missing}")


def _validate_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")
    if prices.empty:
        raise ValueError("prices must not be empty")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise TypeError("prices must use a DatetimeIndex")
    clean = prices.sort_index().astype(float)
    if clean.columns.empty:
        raise ValueError("prices must contain at least one symbol column")
    if clean.isna().all(axis=None):
        raise ValueError("prices must contain at least one finite value")
    return clean.ffill()


def _compound_return(returns: pd.Series) -> float | None:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    return float((1.0 + clean).prod() - 1.0)


def _series_sharpe(returns: pd.Series, annualization: int) -> float | None:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    volatility = float(clean.std(ddof=0) * math.sqrt(annualization))
    if volatility <= 0:
        return None
    annualized_return = float(clean.mean() * annualization)
    return annualized_return / volatility


def _next_value(series: pd.Series, timestamp: pd.Timestamp) -> float | None:
    try:
        loc = series.index.get_loc(timestamp)
    except KeyError:
        return None
    if isinstance(loc, slice):
        loc = loc.stop - 1
    if not isinstance(loc, (int, np.integer)) or loc + 1 >= len(series):
        return None
    value = series.iloc[int(loc) + 1]
    return float(value) if pd.notna(value) else None
