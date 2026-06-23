"""Rising Assets portfolio rotation strategy.

The strategy is a long-only monthly cross-asset momentum rotation:
- score each asset by average trailing 1/3/6/12 month total return
- select the top N assets
- weight selected assets by inverse trailing 63-day volatility
- hold until the next month-end rebalance
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd


RISK_ASSETS: tuple[str, ...] = ("SPY", "IWM", "QQQ", "EFA", "EEM", "VNQ", "LQD")
RISK_OFF_ASSETS: tuple[str, ...] = ("GLD", "SHY", "IEF", "TLT", "AGG")
RISING_ASSETS_UNIVERSE: tuple[str, ...] = (*RISK_ASSETS, *RISK_OFF_ASSETS)


@dataclass(frozen=True)
class RisingAssetsConfig:
    """Configuration for the Rising Assets strategy."""

    momentum_lookbacks: tuple[int, ...] = (21, 63, 126, 252)
    volatility_window: int = 63
    top_n: int = 5
    rebalance_frequency: str = "M"
    min_history: int | None = None
    positive_momentum_only: bool = False
    initial_cash: float = 10_000.0
    trading_cost: float = 0.0
    annualization: int = 252
    live_required_universe: tuple[str, ...] = RISING_ASSETS_UNIVERSE

    def __post_init__(self) -> None:
        if not self.momentum_lookbacks:
            raise ValueError("momentum_lookbacks must not be empty")
        if any(lookback <= 0 for lookback in self.momentum_lookbacks):
            raise ValueError("momentum_lookbacks must be positive")
        if self.volatility_window <= 1:
            raise ValueError("volatility_window must be greater than 1")
        if self.top_n < 1:
            raise ValueError("top_n must be positive")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.trading_cost < 0:
            raise ValueError("trading_cost must not be negative")

    @property
    def required_history(self) -> int:
        return self.min_history or max(max(self.momentum_lookbacks), self.volatility_window)


@dataclass(frozen=True)
class RisingAssetsBacktestResult:
    """Backtest artifacts for Rising Assets."""

    prices: pd.DataFrame
    momentum: pd.DataFrame
    target_weights: pd.DataFrame
    weights: pd.DataFrame
    returns: pd.Series
    equity: pd.Series
    drawdown: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, float | int | None]
    config: RisingAssetsConfig


def compute_momentum_scores(
    prices: pd.DataFrame,
    *,
    lookbacks: tuple[int, ...] = (21, 63, 126, 252),
) -> pd.DataFrame:
    """Average trailing total returns over the configured lookbacks."""
    clean = _validate_prices(prices)
    returns = [(clean / clean.shift(lookback) - 1.0) for lookback in lookbacks]
    return pd.concat(returns, keys=lookbacks, names=["lookback", "date"]).groupby(level="date").mean()


def compute_inverse_volatility_weights(volatility: pd.Series, *, top_assets: list[str]) -> pd.Series:
    """Compute inverse-volatility weights for selected assets."""
    selected_vol = volatility.reindex(top_assets).replace([np.inf, -np.inf], np.nan).dropna()
    selected_vol = selected_vol[selected_vol > 0]
    if selected_vol.empty:
        return pd.Series(dtype=float)
    inverse = 1.0 / selected_vol
    return inverse / inverse.sum()


def generate_monthly_target_weights(
    prices: pd.DataFrame,
    config: RisingAssetsConfig | None = None,
) -> pd.DataFrame:
    """Generate target weights on rebalance dates, forward-filled between rebalances."""
    cfg = config or RisingAssetsConfig()
    clean = _validate_prices(prices)
    momentum = compute_momentum_scores(clean, lookbacks=cfg.momentum_lookbacks)
    volatility = clean.pct_change(fill_method=None).rolling(cfg.volatility_window).std()
    rebalance_dates = _rebalance_dates(clean, cfg.rebalance_frequency)
    target = pd.DataFrame(np.nan, index=clean.index, columns=clean.columns)
    effective_top_n = min(cfg.top_n, len(clean.columns))

    for date in rebalance_dates:
        if clean.index.get_loc(date) < cfg.required_history:
            continue
        scores = momentum.loc[date].replace([np.inf, -np.inf], np.nan).dropna()
        if cfg.positive_momentum_only:
            scores = scores[scores > 0]
        if scores.empty:
            continue
        top_assets = scores.sort_values(ascending=False).head(effective_top_n).index.tolist()
        weights = compute_inverse_volatility_weights(volatility.loc[date], top_assets=top_assets)
        if weights.empty:
            continue
        target.loc[date] = 0.0
        target.loc[date, weights.index] = weights

    return target.ffill().fillna(0.0)


def backtest_rising_assets(
    prices: pd.DataFrame,
    config: RisingAssetsConfig | None = None,
) -> RisingAssetsBacktestResult:
    """Backtest Rising Assets with one-bar delayed monthly target weights."""
    cfg = config or RisingAssetsConfig()
    clean = _validate_prices(prices)
    momentum = compute_momentum_scores(clean, lookbacks=cfg.momentum_lookbacks)
    target_weights = generate_monthly_target_weights(clean, cfg)
    weights = target_weights.shift(1).fillna(0.0)
    asset_returns = clean.pct_change(fill_method=None).fillna(0.0)
    gross_returns = (weights * asset_returns).sum(axis=1)
    turnover = target_weights.diff().abs().sum(axis=1).fillna(target_weights.abs().sum(axis=1))
    net_returns = gross_returns - turnover.shift(1).fillna(0.0) * cfg.trading_cost
    equity = cfg.initial_cash * (1.0 + net_returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    trades = build_rebalance_trade_table(target_weights, prices=clean)
    metrics = compute_portfolio_metrics(net_returns, equity, drawdown, cfg)
    metrics["rebalance_count"] = int(trades["timestamp"].nunique()) if not trades.empty else 0
    return RisingAssetsBacktestResult(
        prices=clean,
        momentum=momentum,
        target_weights=target_weights,
        weights=weights,
        returns=net_returns,
        equity=equity,
        drawdown=drawdown,
        trades=trades,
        metrics=metrics,
        config=cfg,
    )


def build_rebalance_trade_table(target_weights: pd.DataFrame, *, prices: pd.DataFrame) -> pd.DataFrame:
    """Build a monthly allocation-change table from target weights."""
    rows: list[dict[str, Any]] = []
    previous = pd.Series(0.0, index=target_weights.columns)
    for timestamp, weights in target_weights.iterrows():
        if weights.equals(previous):
            continue
        changes = (weights - previous).replace(0.0, np.nan).dropna()
        for symbol, delta in changes.items():
            action = "BUY" if delta > 0 else "SELL"
            rows.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "action": action,
                    "price": float(prices.loc[timestamp, symbol]),
                    "target_weight": float(weights[symbol]),
                    "weight_change": float(delta),
                    "reason": "month_end_rebalance",
                }
            )
        previous = weights.copy()
    return pd.DataFrame(
        rows,
        columns=["timestamp", "symbol", "action", "price", "target_weight", "weight_change", "reason"],
    )


def generate_live_rebalance_orders(
    *,
    current_weights: pd.Series,
    target_weights: pd.Series,
    portfolio_value: float,
    prices: pd.Series,
    min_weight_change: float = 0.005,
) -> pd.DataFrame:
    """Generate target rebalance order instructions for a live/paper broker bridge.

    The output is broker-agnostic. A live adapter must convert these target
    value deltas into broker-specific orders after checking tradability,
    fractional-share rules, cash, fees, and existing positions.
    """
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
    config: RisingAssetsConfig | None = None,
    *,
    broker_symbol_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return live-readiness status and blockers for Rising Assets."""
    cfg = config or RisingAssetsConfig()
    clean = _validate_prices(prices)
    required = set(cfg.live_required_universe)
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
    if cfg.top_n > len(clean.columns):
        blockers.append("available assets are fewer than top_n selection count")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "available_assets": sorted(available),
        "missing_data": missing_data,
        "missing_broker_symbols": missing_broker_symbols,
        "rows": int(len(clean)),
        "required_history": int(cfg.required_history),
    }


def load_price_csv(path: str | Path, *, symbol: str | None = None) -> pd.Series:
    """Load a stock/ETF price CSV into an adjusted-close price series."""
    csv_path = Path(path)
    data = pd.read_csv(csv_path)
    if data.empty:
        raise ValueError(f"{csv_path} is empty")
    date_col = _find_column(data, ("date", "trade_date", "timestamp", "time"))
    if date_col is None:
        raise ValueError(f"{csv_path} must include a date column")
    price_col = _find_column(data, ("adj close", "adj_close", "close", "price"))
    if price_col is None:
        non_date_cols = [column for column in data.columns if column != date_col]
        if len(non_date_cols) == 1:
            price_col = non_date_cols[0]
        else:
            raise ValueError(f"{csv_path} must include an adjusted close, close, price, or single ticker price column")
    dates = pd.to_datetime(data[date_col], errors="coerce", dayfirst=_looks_dayfirst(data[date_col]))
    prices = pd.to_numeric(data[price_col], errors="coerce")
    name = symbol or _symbol_from_path_or_column(csv_path, price_col)
    series = pd.Series(prices.to_numpy(dtype=float), index=dates, name=name).dropna()
    series = series[~series.index.duplicated(keep="last")].sort_index()
    if series.empty:
        raise ValueError(f"{csv_path} did not produce any valid prices")
    return series


def load_price_universe(paths: Mapping[str, str | Path] | Sequence[str | Path], *, join: str = "inner") -> pd.DataFrame:
    """Load multiple price CSVs and align them into one price matrix."""
    if isinstance(paths, Mapping):
        series = [load_price_csv(path, symbol=symbol) for symbol, path in paths.items()]
    else:
        series = [load_price_csv(path) for path in paths]
    if not series:
        raise ValueError("paths must not be empty")
    prices = pd.concat(series, axis=1).sort_index().ffill()
    if join == "inner":
        prices = prices.dropna(how="any")
    elif join == "outer":
        prices = prices.dropna(how="all")
    else:
        raise ValueError("join must be 'inner' or 'outer'")
    return _validate_prices(prices)


def compute_portfolio_metrics(
    returns: pd.Series,
    equity: pd.Series,
    drawdown: pd.Series,
    config: RisingAssetsConfig,
) -> dict[str, float | int | None]:
    """Compute core performance metrics."""
    clean_returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if clean_returns.empty:
        return {
            "total_return": None,
            "total_return_pct": None,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "max_drawdown_pct": None,
            "rebalance_count": 0,
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
        "rebalance_count": None,
    }


def _validate_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")
    if prices.empty:
        raise ValueError("prices must not be empty")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise TypeError("prices must use a DatetimeIndex")
    clean = prices.sort_index().astype(float)
    if clean.columns.empty:
        raise ValueError("prices must contain at least one asset column")
    if clean.isna().all(axis=None):
        raise ValueError("prices must contain at least one finite value")
    return clean.ffill()


def _rebalance_dates(prices: pd.DataFrame, frequency: str) -> pd.DatetimeIndex:
    if frequency.upper() not in {"M", "ME", "MONTH", "MONTHLY"}:
        raise ValueError("Only monthly rebalance_frequency is currently supported")
    index = prices.index.tz_localize(None) if prices.index.tz is not None else prices.index
    periods = index.to_period("M")
    period_series = pd.Series(periods, index=prices.index)
    return pd.DatetimeIndex(prices.index[period_series.ne(period_series.shift(-1))])


def _find_column(data: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lookup = {str(column).strip().lower(): str(column) for column in data.columns}
    for name in names:
        if name in lookup:
            return lookup[name]
    return None


def _looks_dayfirst(values: pd.Series) -> bool:
    sample = values.dropna().astype(str).head(5)
    return any("/" in value and len(value.split("/")[0]) <= 2 for value in sample)


def _symbol_from_path_or_column(path: Path, price_col: str) -> str:
    column = str(price_col).strip()
    if column.lower() not in {"adj close", "adj_close", "close", "price"}:
        return column.upper().replace(" ", "_")
    return path.parent.name.upper().replace(" ", "_")
