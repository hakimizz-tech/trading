"""Connors Research Weekly Mean Reversion strategy.

The strategy is a long-only weekly stock mean-reversion system:
- only open new stock positions when SPY's trailing 126-day return is positive
- restrict candidates to the most liquid stocks by 200-day dollar volume
- buy weekly RSI(2) pullbacks below 20
- rank entries by lowest trailing 100-day volatility
- hold up to 10 equal-weight stock positions
- sell on weekly RSI(2) above 80 or a daily 10% stop from entry
- invest idle capital in SHY when SHY data is available
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_data.ohlcv import load_ohlcv_csv


DEFAULT_CONNORS_UNIVERSE: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "QQQ")


@dataclass(frozen=True)
class ConnorsWeeklyMeanReversionConfig:
    """Configuration for the Connors weekly mean-reversion strategy."""

    regime_symbol: str = "SPY"
    cash_symbol: str = "SHY"
    regime_lookback: int = 126
    weekly_rsi_period: int = 2
    entry_rsi: float = 20.0
    exit_rsi: float = 80.0
    volatility_lookback: int = 100
    liquidity_lookback: int = 200
    liquid_universe_size: int = 500
    max_positions: int = 10
    stop_loss_pct: float = 0.10
    initial_cash: float = 10_000.0
    trading_cost: float = 0.0
    annualization: int = 252
    live_required_symbols: tuple[str, ...] = (
        "SPY",
        "SHY",
        *DEFAULT_CONNORS_UNIVERSE,
    )

    def __post_init__(self) -> None:
        if self.regime_lookback <= 0:
            raise ValueError("regime_lookback must be positive")
        if self.weekly_rsi_period <= 0:
            raise ValueError("weekly_rsi_period must be positive")
        if not 0 <= self.entry_rsi <= 100:
            raise ValueError("entry_rsi must be between 0 and 100")
        if not 0 <= self.exit_rsi <= 100:
            raise ValueError("exit_rsi must be between 0 and 100")
        if self.volatility_lookback <= 1:
            raise ValueError("volatility_lookback must be greater than 1")
        if self.liquidity_lookback <= 1:
            raise ValueError("liquidity_lookback must be greater than 1")
        if self.liquid_universe_size < 1:
            raise ValueError("liquid_universe_size must be positive")
        if self.max_positions < 1:
            raise ValueError("max_positions must be positive")
        if not 0 < self.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct must be between 0 and 1")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.trading_cost < 0:
            raise ValueError("trading_cost must not be negative")
        if self.annualization <= 0:
            raise ValueError("annualization must be positive")

    @property
    def required_history(self) -> int:
        return max(self.regime_lookback, self.volatility_lookback, self.liquidity_lookback)


@dataclass(frozen=True)
class ConnorsWeeklyMeanReversionResult:
    """Backtest artifacts for Connors Weekly Mean Reversion."""

    prices: pd.DataFrame
    volumes: pd.DataFrame
    weekly_rsi: pd.DataFrame
    regime: pd.Series
    volatility: pd.DataFrame
    average_dollar_volume: pd.DataFrame
    target_weights: pd.DataFrame
    weights: pd.DataFrame
    returns: pd.Series
    equity: pd.Series
    drawdown: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, float | int | None]
    config: ConnorsWeeklyMeanReversionConfig


def load_connors_ohlcv_universe(
    paths: dict[str, str | Path] | list[str | Path],
    *,
    join: str = "inner",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load stock/ETF OHLCV CSVs and return aligned close and volume matrices."""
    if isinstance(paths, dict):
        items = list(paths.items())
    else:
        items = [(Path(path).parent.name.upper().replace(" ", "_"), path) for path in paths]
    if not items:
        raise ValueError("paths must not be empty")

    closes: list[pd.Series] = []
    volumes: list[pd.Series] = []
    for symbol, path in items:
        ohlcv = load_ohlcv_csv(path, symbol=symbol)
        closes.append(ohlcv["close"].rename(symbol))
        volumes.append(ohlcv["volume"].rename(symbol))

    prices = pd.concat(closes, axis=1).sort_index().ffill()
    volume_frame = pd.concat(volumes, axis=1).sort_index().ffill().fillna(0.0)
    if join == "inner":
        prices = prices.dropna(how="any")
        volume_frame = volume_frame.reindex(prices.index).fillna(0.0)
    elif join == "outer":
        prices = prices.dropna(how="all")
        volume_frame = volume_frame.reindex(prices.index).fillna(0.0)
    else:
        raise ValueError("join must be 'inner' or 'outer'")
    return _validate_prices(prices), _validate_volumes(volume_frame.reindex(prices.index))


def compute_weekly_rsi(prices: pd.DataFrame, *, period: int = 2) -> pd.DataFrame:
    """Compute weekly RSI and forward-fill it onto the daily index."""
    clean = _validate_prices(prices)
    if period <= 0:
        raise ValueError("period must be positive")
    weekly_close = clean.resample("W-FRI").last().dropna(how="all")
    weekly_rsi = _rsi(weekly_close, period=period)
    return weekly_rsi.reindex(clean.index, method="ffill")


def compute_regime_filter(
    prices: pd.DataFrame,
    *,
    regime_symbol: str = "SPY",
    lookback: int = 126,
) -> pd.Series:
    """Return True when the regime symbol's trailing return is positive."""
    clean = _validate_prices(prices)
    if regime_symbol not in clean.columns:
        raise ValueError(f"{regime_symbol} is required for the regime filter")
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    regime_return = clean[regime_symbol] / clean[regime_symbol].shift(lookback) - 1.0
    return regime_return.gt(0.0).fillna(False).rename("regime_up")


def compute_historical_volatility(prices: pd.DataFrame, *, lookback: int = 100) -> pd.DataFrame:
    """Compute trailing daily return volatility used for candidate ranking."""
    clean = _validate_prices(prices)
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1")
    return clean.pct_change(fill_method=None).rolling(lookback).std(ddof=0)


def compute_average_dollar_volume(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    lookback: int = 200,
) -> pd.DataFrame:
    """Compute trailing average dollar volume used for liquidity screening."""
    clean_prices = _validate_prices(prices)
    clean_volumes = _validate_volumes(volumes).reindex(clean_prices.index).fillna(0.0)
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1")
    return (clean_prices * clean_volumes).rolling(lookback).mean()


def generate_connors_target_weights(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    config: ConnorsWeeklyMeanReversionConfig | None = None,
    *,
    trade_start: pd.Timestamp | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate daily target weights and trade-intent rows from Connors rules."""
    cfg = config or ConnorsWeeklyMeanReversionConfig()
    clean_prices = _validate_prices(prices)
    clean_volumes = _validate_volumes(volumes).reindex(clean_prices.index).fillna(0.0)
    start_timestamp = pd.Timestamp(trade_start) if trade_start is not None else None
    weekly_rsi = compute_weekly_rsi(clean_prices, period=cfg.weekly_rsi_period)
    regime = compute_regime_filter(clean_prices, regime_symbol=cfg.regime_symbol, lookback=cfg.regime_lookback)
    volatility = compute_historical_volatility(clean_prices, lookback=cfg.volatility_lookback)
    average_dollar_volume = compute_average_dollar_volume(clean_prices, clean_volumes, lookback=cfg.liquidity_lookback)
    weekly_dates = set(_weekly_check_dates(clean_prices))
    stock_symbols = _stock_symbols(clean_prices.columns, cfg)
    target = pd.DataFrame(0.0, index=clean_prices.index, columns=clean_prices.columns)
    holdings: dict[str, float] = {}
    trade_rows: list[dict[str, Any]] = []

    for timestamp in clean_prices.index:
        prices_today = clean_prices.loc[timestamp]
        trading_enabled = start_timestamp is None or pd.Timestamp(timestamp) >= start_timestamp

        if trading_enabled:
            for symbol, entry_price in list(holdings.items()):
                current_price = float(prices_today[symbol])
                if np.isfinite(current_price) and current_price <= entry_price * (1.0 - cfg.stop_loss_pct):
                    trade_rows.append(
                        _trade_row(timestamp, symbol, "SELL", current_price, 0.0, "daily_stop_loss", entry_price)
                    )
                    del holdings[symbol]

        if trading_enabled and timestamp in weekly_dates:
            for symbol in list(holdings):
                rsi_value = weekly_rsi.loc[timestamp, symbol]
                if pd.notna(rsi_value) and float(rsi_value) > cfg.exit_rsi:
                    trade_rows.append(
                        _trade_row(
                            timestamp,
                            symbol,
                            "SELL",
                            float(prices_today[symbol]),
                            0.0,
                            "weekly_rsi_exit",
                            holdings[symbol],
                        )
                    )
                    del holdings[symbol]

            open_slots = cfg.max_positions - len(holdings)
            if open_slots > 0 and bool(regime.loc[timestamp]):
                candidates = _entry_candidates(
                    timestamp=timestamp,
                    stock_symbols=stock_symbols,
                    existing=set(holdings),
                    weekly_rsi=weekly_rsi,
                    volatility=volatility,
                    average_dollar_volume=average_dollar_volume,
                    prices=clean_prices,
                    config=cfg,
                )
                for symbol in candidates[:open_slots]:
                    entry_price = float(prices_today[symbol])
                    holdings[symbol] = entry_price
                    trade_rows.append(
                        _trade_row(
                            timestamp,
                            symbol,
                            "BUY",
                            entry_price,
                            1.0 / cfg.max_positions,
                            "weekly_rsi_entry",
                            entry_price,
                        )
                    )

        if holdings:
            for symbol in holdings:
                target.loc[timestamp, symbol] = 1.0 / cfg.max_positions
        if cfg.cash_symbol in target.columns:
            target.loc[timestamp, cfg.cash_symbol] = max(0.0, 1.0 - len(holdings) / cfg.max_positions)

    trades = pd.DataFrame(
        trade_rows,
        columns=[
            "timestamp",
            "symbol",
            "action",
            "price",
            "target_weight",
            "reason",
            "entry_price",
        ],
    )
    if not trades.empty:
        trades["trade_id"] = trades["timestamp"].astype(str) + ":" + trades["symbol"].astype(str) + ":" + trades["action"]
        trades["side"] = "long"
        trades["size"] = trades["target_weight"].abs()
        trades["pnl"] = pd.NA
        trades["return_pct"] = pd.NA
        trades["status"] = "signal"
    return target, trades


def build_connors_closed_trades(
    trades: pd.DataFrame,
    *,
    initial_cash: float = 10_000.0,
) -> pd.DataFrame:
    """Pair Connors BUY/SELL signal rows into closed round-trip trades."""
    columns = [
        "trade_id",
        "symbol",
        "entry_timestamp",
        "exit_timestamp",
        "entry_price",
        "exit_price",
        "size",
        "pnl",
        "return_pct",
        "exit_reason",
        "holding_days",
        "status",
    ]
    if trades.empty:
        return pd.DataFrame(columns=columns)

    open_by_symbol: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    ordered = trades.sort_values("timestamp")
    for _, row in ordered.iterrows():
        symbol = str(row["symbol"])
        action = str(row["action"]).upper()
        if action == "BUY":
            open_by_symbol[symbol] = row.to_dict()
            continue
        if action != "SELL" or symbol not in open_by_symbol:
            continue

        entry = open_by_symbol.pop(symbol)
        entry_time = pd.Timestamp(entry["timestamp"])
        exit_time = pd.Timestamp(row["timestamp"])
        entry_price = float(entry["price"])
        exit_price = float(row["price"])
        size = float(entry.get("target_weight", 0.0) or 0.0)
        return_decimal = exit_price / entry_price - 1.0 if entry_price > 0 else 0.0
        rows.append(
            {
                "trade_id": f"{entry_time.isoformat()}:{symbol}",
                "symbol": symbol,
                "entry_timestamp": entry_time,
                "exit_timestamp": exit_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "size": size,
                "pnl": return_decimal * size * initial_cash,
                "return_pct": return_decimal * 100.0,
                "exit_reason": row.get("reason", "exit"),
                "holding_days": int(max((exit_time - entry_time).days, 0)),
                "status": "closed",
            }
        )

    return pd.DataFrame(rows, columns=columns)


def backtest_connors_weekly_mean_reversion(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    config: ConnorsWeeklyMeanReversionConfig | None = None,
    *,
    trade_start: pd.Timestamp | str | None = None,
) -> ConnorsWeeklyMeanReversionResult:
    """Backtest Connors rules with one-bar delayed target weights."""
    cfg = config or ConnorsWeeklyMeanReversionConfig()
    clean_prices = _validate_prices(prices)
    clean_volumes = _validate_volumes(volumes).reindex(clean_prices.index).fillna(0.0)
    weekly_rsi = compute_weekly_rsi(clean_prices, period=cfg.weekly_rsi_period)
    regime = compute_regime_filter(clean_prices, regime_symbol=cfg.regime_symbol, lookback=cfg.regime_lookback)
    volatility = compute_historical_volatility(clean_prices, lookback=cfg.volatility_lookback)
    average_dollar_volume = compute_average_dollar_volume(clean_prices, clean_volumes, lookback=cfg.liquidity_lookback)
    target_weights, trades = generate_connors_target_weights(clean_prices, clean_volumes, cfg, trade_start=trade_start)
    weights = target_weights.shift(1).fillna(0.0)
    asset_returns = clean_prices.pct_change(fill_method=None).fillna(0.0)
    gross_returns = (weights * asset_returns).sum(axis=1)
    turnover = target_weights.diff().abs().sum(axis=1).fillna(target_weights.abs().sum(axis=1))
    net_returns = gross_returns - turnover.shift(1).fillna(0.0) * cfg.trading_cost
    equity = cfg.initial_cash * (1.0 + net_returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    metrics = compute_portfolio_metrics(net_returns, equity, drawdown, trades, cfg)
    return ConnorsWeeklyMeanReversionResult(
        prices=clean_prices,
        volumes=clean_volumes,
        weekly_rsi=weekly_rsi,
        regime=regime,
        volatility=volatility,
        average_dollar_volume=average_dollar_volume,
        target_weights=target_weights,
        weights=weights,
        returns=net_returns,
        equity=equity,
        drawdown=drawdown,
        trades=trades,
        metrics=metrics,
        config=cfg,
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
    volumes: pd.DataFrame,
    config: ConnorsWeeklyMeanReversionConfig | None = None,
    *,
    broker_symbol_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return live-readiness status and blockers for Connors weekly strategy."""
    cfg = config or ConnorsWeeklyMeanReversionConfig()
    clean_prices = _validate_prices(prices)
    clean_volumes = _validate_volumes(volumes).reindex(clean_prices.index).fillna(0.0)
    required = set(cfg.live_required_symbols)
    available = set(clean_prices.columns)
    missing_data = sorted(required - available)
    symbol_map = broker_symbol_map or {}
    missing_broker_symbols = sorted(symbol for symbol in required if symbol not in symbol_map)
    enough_history = len(clean_prices) > cfg.required_history
    has_volume = bool((clean_volumes.sum(axis=0) > 0).any())
    blockers: list[str] = []
    if cfg.regime_symbol not in available:
        blockers.append(f"missing regime symbol: {cfg.regime_symbol}")
    if cfg.cash_symbol not in available:
        blockers.append(f"missing idle-cash symbol: {cfg.cash_symbol}")
    if missing_data:
        blockers.append(f"missing price data for: {', '.join(missing_data)}")
    if missing_broker_symbols:
        blockers.append(f"missing broker symbol mapping for: {', '.join(missing_broker_symbols)}")
    if not enough_history:
        blockers.append(f"need more than {cfg.required_history} rows of price history")
    if not has_volume:
        blockers.append("volume data is required for the 200-day liquidity filter")
    if len(_stock_symbols(clean_prices.columns, cfg)) < 1:
        blockers.append("need at least one tradable stock candidate besides SPY and SHY")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "available_symbols": sorted(available),
        "missing_data": missing_data,
        "missing_broker_symbols": missing_broker_symbols,
        "rows": int(len(clean_prices)),
        "required_history": int(cfg.required_history),
        "has_volume": has_volume,
    }


def compute_asset_performance(result: ConnorsWeeklyMeanReversionResult) -> pd.DataFrame:
    """Summarize per-symbol strategy attribution and held-period performance."""
    asset_returns = result.prices.pct_change(fill_method=None).fillna(0.0)
    weighted_returns = result.weights.reindex(asset_returns.index).fillna(0.0) * asset_returns
    rows: list[dict[str, Any]] = []
    trades = result.trades.copy()
    closed_trades = build_connors_closed_trades(result.trades, initial_cash=result.config.initial_cash)
    if not trades.empty:
        trades["symbol"] = trades["symbol"].astype(str)
    if not closed_trades.empty:
        closed_trades["symbol"] = closed_trades["symbol"].astype(str)

    for symbol in result.prices.columns:
        weights = result.weights[symbol].reindex(asset_returns.index).fillna(0.0)
        contribution = weighted_returns[symbol].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        held_mask = weights.abs() > 0.0
        held_returns = asset_returns.loc[held_mask, symbol].replace([np.inf, -np.inf], np.nan).dropna()
        contribution_equity = (1.0 + contribution).cumprod()
        contribution_drawdown = contribution_equity / contribution_equity.cummax() - 1.0
        symbol_trades = trades.loc[trades["symbol"] == symbol] if not trades.empty else pd.DataFrame()
        symbol_closed = (
            closed_trades.loc[closed_trades["symbol"] == symbol] if not closed_trades.empty else pd.DataFrame()
        )
        entries = symbol_trades.loc[symbol_trades["action"] == "BUY"] if not symbol_trades.empty else pd.DataFrame()
        exits = symbol_trades.loc[symbol_trades["action"] == "SELL"] if not symbol_trades.empty else pd.DataFrame()
        closed_returns = (
            pd.to_numeric(symbol_closed["return_pct"], errors="coerce") if not symbol_closed.empty else pd.Series(dtype=float)
        )
        rows.append(
            {
                "symbol": symbol,
                "days_held": int(held_mask.sum()),
                "exposure_pct": float(held_mask.mean() * 100.0),
                "average_weight": float(weights.mean()),
                "max_weight": float(weights.max()),
                "entries": int(len(entries)),
                "exits": int(len(exits)),
                "weekly_rsi_exits": int((exits.get("reason", pd.Series(dtype=str)) == "weekly_rsi_exit").sum()),
                "stop_loss_exits": int((exits.get("reason", pd.Series(dtype=str)) == "daily_stop_loss").sum()),
                "closed_trades": int(len(symbol_closed)),
                "win_rate": _win_rate(closed_returns),
                "avg_trade_return_pct": _mean_or_none(closed_returns),
                "avg_holding_days": _mean_or_none(
                    pd.to_numeric(symbol_closed.get("holding_days", pd.Series(dtype=float)), errors="coerce")
                    if not symbol_closed.empty
                    else pd.Series(dtype=float)
                ),
                "asset_total_return_while_held": _compound_return(held_returns),
                "asset_sharpe_while_held": _series_sharpe(held_returns, result.config.annualization),
                "strategy_contribution_return": float(contribution.sum()),
                "strategy_contribution_return_pct": float(contribution.sum() * 100.0),
                "contribution_sharpe": _series_sharpe(contribution, result.config.annualization),
                "contribution_max_drawdown": float(contribution_drawdown.min()),
                "contribution_max_drawdown_pct": float(contribution_drawdown.min() * 100.0),
            }
        )
    return pd.DataFrame(rows).sort_values("strategy_contribution_return", ascending=False).reset_index(drop=True)


def compute_portfolio_metrics(
    returns: pd.Series,
    equity: pd.Series,
    drawdown: pd.Series,
    trades: pd.DataFrame,
    config: ConnorsWeeklyMeanReversionConfig,
) -> dict[str, float | int | None]:
    """Compute core strategy performance metrics."""
    clean_returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    trade_count = int((trades["action"] == "BUY").sum()) if not trades.empty and "action" in trades.columns else 0
    if clean_returns.empty:
        return {
            "total_return": None,
            "total_return_pct": None,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "max_drawdown_pct": None,
            "trade_count": trade_count,
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
        "trade_count": trade_count,
    }


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


def _mean_or_none(values: pd.Series) -> float | None:
    clean = values.replace([np.inf, -np.inf], np.nan).dropna()
    return float(clean.mean()) if len(clean) else None


def _win_rate(returns_pct: pd.Series) -> float | None:
    clean = returns_pct.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    return float((clean > 0.0).mean())


def _entry_candidates(
    *,
    timestamp: pd.Timestamp,
    stock_symbols: list[str],
    existing: set[str],
    weekly_rsi: pd.DataFrame,
    volatility: pd.DataFrame,
    average_dollar_volume: pd.DataFrame,
    prices: pd.DataFrame,
    config: ConnorsWeeklyMeanReversionConfig,
) -> list[str]:
    liquid = average_dollar_volume.loc[timestamp, stock_symbols].replace([np.inf, -np.inf], np.nan).dropna()
    liquid = liquid[liquid > 0].sort_values(ascending=False).head(config.liquid_universe_size).index
    rows: list[tuple[str, float]] = []
    for symbol in liquid:
        if symbol in existing:
            continue
        price = prices.loc[timestamp, symbol]
        rsi_value = weekly_rsi.loc[timestamp, symbol]
        vol_value = volatility.loc[timestamp, symbol]
        if pd.isna(price) or pd.isna(rsi_value) or pd.isna(vol_value):
            continue
        if float(price) <= 0 or float(vol_value) <= 0:
            continue
        if float(rsi_value) < config.entry_rsi:
            rows.append((symbol, float(vol_value)))
    return [symbol for symbol, _ in sorted(rows, key=lambda item: (item[1], item[0]))]


def _trade_row(
    timestamp: pd.Timestamp,
    symbol: str,
    action: str,
    price: float,
    target_weight: float,
    reason: str,
    entry_price: float,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "symbol": symbol,
        "action": action,
        "price": price,
        "target_weight": target_weight,
        "reason": reason,
        "entry_price": entry_price,
    }


def _rsi(prices: pd.DataFrame, *, period: int) -> pd.DataFrame:
    delta = prices.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.rolling(period, min_periods=period).mean()
    avg_loss = losses.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.mask((avg_loss == 0.0) & (avg_gain > 0.0), 100.0)
    rsi = rsi.mask((avg_gain == 0.0) & (avg_loss > 0.0), 0.0)
    return rsi


def _weekly_check_dates(prices: pd.DataFrame) -> pd.DatetimeIndex:
    index = prices.index.tz_localize(None) if prices.index.tz is not None else prices.index
    periods = index.to_period("W-FRI")
    period_series = pd.Series(periods, index=prices.index)
    return pd.DatetimeIndex(prices.index[period_series.ne(period_series.shift(-1))])


def _stock_symbols(columns: pd.Index, config: ConnorsWeeklyMeanReversionConfig) -> list[str]:
    excluded = {config.regime_symbol, config.cash_symbol}
    return [str(column) for column in columns if str(column) not in excluded]


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


def _validate_volumes(volumes: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(volumes, pd.DataFrame):
        raise TypeError("volumes must be a pandas DataFrame")
    if volumes.empty:
        raise ValueError("volumes must not be empty")
    if not isinstance(volumes.index, pd.DatetimeIndex):
        raise TypeError("volumes must use a DatetimeIndex")
    return volumes.sort_index().astype(float).ffill().fillna(0.0)
