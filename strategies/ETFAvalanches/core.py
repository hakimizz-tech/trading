"""ETF Avalanches short-only mean-reversion strategy.

The strategy sells short bear-market rallies in global/sector equity ETFs:
- 252-day and 21-day trailing returns must both be negative
- RSI(2) must be above 70 before a next-day sell-limit order is placed
- entry limit is 3% above the prior close and fills when next-day high reaches it
- hold up to five short positions ranked by highest trailing 100-day volatility
- cover when RSI(2) drops below 15 or 21-day return turns positive
- idle capital is allocated to SHY when available
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_data.ohlcv import load_ohlcv_csv


ETF_AVALANCHES_CORE_UNIVERSE: tuple[str, ...] = ("SPY", "IWM", "EFA", "EEM", "VNQ")
ETF_AVALANCHES_RESEARCH_UNIVERSE: tuple[str, ...] = (
    "SPY",
    "IWM",
    "EFA",
    "EEM",
    "VNQ",
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
    "EWA",
    "EWC",
    "EWG",
    "EWH",
    "EWJ",
    "EWS",
    "EWT",
    "EWU",
    "EWY",
    "EWZ",
)


@dataclass(frozen=True)
class ETFAvalanchesConfig:
    """Configuration for ETF Avalanches."""

    cash_symbol: str = "SHY"
    long_lookback: int = 252
    intermediate_lookback: int = 21
    rsi_period: int = 2
    entry_rsi: float = 70.0
    exit_rsi: float = 15.0
    limit_entry_pct: float = 0.03
    volatility_lookback: int = 100
    max_positions: int = 5
    initial_cash: float = 10_000.0
    trading_cost: float = 0.0
    annualization: int = 252
    live_required_symbols: tuple[str, ...] = (*ETF_AVALANCHES_CORE_UNIVERSE, "SHY")

    def __post_init__(self) -> None:
        if self.long_lookback <= 0:
            raise ValueError("long_lookback must be positive")
        if self.intermediate_lookback <= 0:
            raise ValueError("intermediate_lookback must be positive")
        if self.rsi_period <= 0:
            raise ValueError("rsi_period must be positive")
        if not 0 <= self.entry_rsi <= 100:
            raise ValueError("entry_rsi must be between 0 and 100")
        if not 0 <= self.exit_rsi <= 100:
            raise ValueError("exit_rsi must be between 0 and 100")
        if self.limit_entry_pct < 0:
            raise ValueError("limit_entry_pct must not be negative")
        if self.volatility_lookback <= 1:
            raise ValueError("volatility_lookback must be greater than 1")
        if self.max_positions < 1:
            raise ValueError("max_positions must be positive")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.trading_cost < 0:
            raise ValueError("trading_cost must not be negative")
        if self.annualization <= 0:
            raise ValueError("annualization must be positive")

    @property
    def required_history(self) -> int:
        return max(self.long_lookback, self.intermediate_lookback, self.volatility_lookback, self.rsi_period + 1)

    @property
    def slot_weight(self) -> float:
        return 1.0 / float(self.max_positions)


@dataclass(frozen=True)
class ETFAvalanchesResult:
    """Backtest artifacts for ETF Avalanches."""

    prices: pd.DataFrame
    highs: pd.DataFrame
    rsi: pd.DataFrame
    long_returns: pd.DataFrame
    intermediate_returns: pd.DataFrame
    volatility: pd.DataFrame
    candidate_signals: pd.DataFrame
    target_weights: pd.DataFrame
    weights: pd.DataFrame
    returns: pd.Series
    equity: pd.Series
    drawdown: pd.Series
    trades: pd.DataFrame
    closed_trades: pd.DataFrame
    metrics: dict[str, float | int | None]
    asset_performance: pd.DataFrame
    config: ETFAvalanchesConfig


def load_etf_avalanche_ohlcv(
    paths: dict[str, str | Path] | list[str | Path],
    *,
    join: str = "inner",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load ETF OHLCV CSVs and return aligned close, high, and volume matrices."""
    if isinstance(paths, dict):
        items = list(paths.items())
    else:
        items = [(Path(path).parent.name.upper().replace(" ", "_"), path) for path in paths]
    if not items:
        raise ValueError("paths must not be empty")

    closes: list[pd.Series] = []
    highs: list[pd.Series] = []
    volumes: list[pd.Series] = []
    for symbol, path in items:
        frame = load_ohlcv_csv(path, symbol=symbol)
        closes.append(frame["close"].rename(symbol.upper()))
        highs.append(frame["high"].rename(symbol.upper()))
        volumes.append(frame["volume"].rename(symbol.upper()))

    prices = pd.concat(closes, axis=1).sort_index().ffill()
    high_frame = pd.concat(highs, axis=1).sort_index().ffill()
    volume_frame = pd.concat(volumes, axis=1).sort_index().ffill().fillna(0.0)
    if join == "inner":
        prices = prices.dropna(how="any")
        high_frame = high_frame.reindex(prices.index).ffill()
        volume_frame = volume_frame.reindex(prices.index).fillna(0.0)
    elif join == "outer":
        prices = prices.dropna(how="all")
        high_frame = high_frame.reindex(prices.index).ffill()
        volume_frame = volume_frame.reindex(prices.index).fillna(0.0)
    else:
        raise ValueError("join must be 'inner' or 'outer'")
    return _validate_prices(prices), _validate_prices(high_frame.reindex(prices.index)), _validate_volumes(volume_frame.reindex(prices.index))


def compute_rsi(prices: pd.DataFrame, *, period: int = 2) -> pd.DataFrame:
    """Compute RSI for each ETF close series."""
    clean = _validate_prices(prices)
    if period <= 0:
        raise ValueError("period must be positive")
    return _rsi(clean, period=period)


def compute_trailing_returns(prices: pd.DataFrame, *, lookback: int) -> pd.DataFrame:
    """Compute trailing total returns."""
    clean = _validate_prices(prices)
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    return clean / clean.shift(lookback) - 1.0


def compute_historical_volatility(prices: pd.DataFrame, *, lookback: int = 100) -> pd.DataFrame:
    """Compute trailing daily-return volatility for ranking short candidates."""
    clean = _validate_prices(prices)
    if lookback <= 1:
        raise ValueError("lookback must be greater than 1")
    return clean.pct_change(fill_method=None).rolling(lookback).std(ddof=0)


def generate_etf_avalanche_target_weights(
    prices: pd.DataFrame,
    highs: pd.DataFrame,
    config: ETFAvalanchesConfig | None = None,
    *,
    trade_start: pd.Timestamp | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate target weights, trade rows, and daily candidate signals."""
    cfg = config or ETFAvalanchesConfig()
    clean_prices = _validate_prices(prices)
    clean_highs = _validate_prices(highs).reindex(clean_prices.index).ffill()
    start_timestamp = pd.Timestamp(trade_start) if trade_start is not None else None
    short_symbols = _short_symbols(clean_prices.columns, cfg)
    rsi = compute_rsi(clean_prices, period=cfg.rsi_period)
    long_returns = compute_trailing_returns(clean_prices, lookback=cfg.long_lookback)
    intermediate_returns = compute_trailing_returns(clean_prices, lookback=cfg.intermediate_lookback)
    volatility = compute_historical_volatility(clean_prices, lookback=cfg.volatility_lookback)

    target = pd.DataFrame(0.0, index=clean_prices.index, columns=clean_prices.columns)
    holdings: dict[str, dict[str, Any]] = {}
    trade_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    for i, timestamp in enumerate(clean_prices.index):
        trading_enabled = start_timestamp is None or pd.Timestamp(timestamp) >= start_timestamp
        prices_today = clean_prices.loc[timestamp]

        if trading_enabled:
            for symbol, position in list(holdings.items()):
                rsi_value = rsi.loc[timestamp, symbol]
                intermediate_value = intermediate_returns.loc[timestamp, symbol]
                exit_reason = None
                if pd.notna(rsi_value) and float(rsi_value) < cfg.exit_rsi:
                    exit_reason = "rsi_cover"
                elif pd.notna(intermediate_value) and float(intermediate_value) > 0.0:
                    exit_reason = "intermediate_momentum_cover"
                if exit_reason is not None:
                    exit_price = float(prices_today[symbol])
                    return_pct = (float(position["entry_price"]) - exit_price) / float(position["entry_price"]) * 100.0
                    trade_rows.append(
                        _trade_row(
                            timestamp=timestamp,
                            symbol=symbol,
                            action="EXIT_SHORT",
                            price=exit_price,
                            target_weight=0.0,
                            reason=exit_reason,
                            trade_id=str(position["trade_id"]),
                            entry_price=float(position["entry_price"]),
                            pnl=return_pct / 100.0 * cfg.initial_cash * cfg.slot_weight,
                            return_pct=return_pct,
                            status="closed",
                        )
                    )
                    del holdings[symbol]

        if trading_enabled and i > 0 and len(holdings) < cfg.max_positions:
            signal_timestamp = clean_prices.index[i - 1]
            open_slots = cfg.max_positions - len(holdings)
            candidates = _entry_candidates(
                signal_timestamp=signal_timestamp,
                trade_timestamp=timestamp,
                short_symbols=short_symbols,
                holdings=set(holdings),
                prices=clean_prices,
                highs=clean_highs,
                rsi=rsi,
                long_returns=long_returns,
                intermediate_returns=intermediate_returns,
                volatility=volatility,
                config=cfg,
            )
            for candidate in candidates:
                candidate_rows.append(candidate)
            for candidate in candidates[:open_slots]:
                symbol = str(candidate["symbol"])
                entry_price = float(candidate["limit_price"])
                trade_id = f"{pd.Timestamp(timestamp).isoformat()}:{symbol}:SHORT"
                holdings[symbol] = {
                    "trade_id": trade_id,
                    "entry_timestamp": timestamp,
                    "entry_price": entry_price,
                }
                trade_rows.append(
                    _trade_row(
                        timestamp=timestamp,
                        symbol=symbol,
                        action="ENTER_SHORT",
                        price=entry_price,
                        target_weight=-cfg.slot_weight,
                        reason="bear_rally_limit_fill",
                        trade_id=trade_id,
                        entry_price=entry_price,
                        pnl=None,
                        return_pct=None,
                        status="open",
                    )
                )

        for symbol in holdings:
            target.loc[timestamp, symbol] = -cfg.slot_weight
        if cfg.cash_symbol in target.columns:
            short_exposure = float(target.loc[timestamp, short_symbols].abs().sum()) if short_symbols else 0.0
            target.loc[timestamp, cfg.cash_symbol] = max(0.0, 1.0 - short_exposure)

    trades = pd.DataFrame(
        trade_rows,
        columns=[
            "trade_id",
            "timestamp",
            "symbol",
            "action",
            "price",
            "target_weight",
            "reason",
            "entry_price",
            "side",
            "size",
            "pnl",
            "return_pct",
            "status",
        ],
    )
    candidates = pd.DataFrame(
        candidate_rows,
        columns=[
            "signal_timestamp",
            "trade_timestamp",
            "symbol",
            "close",
            "high",
            "limit_price",
            "rsi",
            "long_return",
            "intermediate_return",
            "volatility",
            "filled",
        ],
    )
    return target, trades, candidates


def backtest_etf_avalanches(
    prices: pd.DataFrame,
    highs: pd.DataFrame,
    config: ETFAvalanchesConfig | None = None,
    *,
    trade_start: pd.Timestamp | str | None = None,
) -> ETFAvalanchesResult:
    """Backtest ETF Avalanches with one-bar-delayed target weights."""
    cfg = config or ETFAvalanchesConfig()
    clean_prices = _validate_prices(prices)
    clean_highs = _validate_prices(highs).reindex(clean_prices.index).ffill()
    target_weights, trades, candidates = generate_etf_avalanche_target_weights(
        clean_prices,
        clean_highs,
        cfg,
        trade_start=trade_start,
    )
    weights = target_weights.shift(1).fillna(0.0)
    if cfg.cash_symbol in weights.columns:
        weights.loc[weights.index[0], cfg.cash_symbol] = 1.0
    asset_returns = clean_prices.loc[:, weights.columns].pct_change(fill_method=None).fillna(0.0)
    gross_returns = (weights * asset_returns).sum(axis=1)
    turnover = target_weights.diff().abs().sum(axis=1).fillna(target_weights.abs().sum(axis=1))
    net_returns = gross_returns - turnover.shift(1).fillna(0.0) * cfg.trading_cost
    equity = cfg.initial_cash * (1.0 + net_returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    closed_trades = build_etf_avalanche_closed_trades(trades, initial_cash=cfg.initial_cash, slot_weight=cfg.slot_weight)
    metrics = compute_portfolio_metrics(net_returns, equity, drawdown, trades, closed_trades, cfg)
    asset_performance = compute_asset_performance(clean_prices.loc[:, weights.columns], weights, cfg)
    return ETFAvalanchesResult(
        prices=clean_prices.loc[:, weights.columns],
        highs=clean_highs.loc[:, weights.columns],
        rsi=compute_rsi(clean_prices, period=cfg.rsi_period),
        long_returns=compute_trailing_returns(clean_prices, lookback=cfg.long_lookback),
        intermediate_returns=compute_trailing_returns(clean_prices, lookback=cfg.intermediate_lookback),
        volatility=compute_historical_volatility(clean_prices, lookback=cfg.volatility_lookback),
        candidate_signals=candidates,
        target_weights=target_weights,
        weights=weights,
        returns=net_returns,
        equity=equity,
        drawdown=drawdown,
        trades=trades,
        closed_trades=closed_trades,
        metrics=metrics,
        asset_performance=asset_performance,
        config=cfg,
    )


def build_etf_avalanche_closed_trades(
    trades: pd.DataFrame,
    *,
    initial_cash: float = 10_000.0,
    slot_weight: float = 0.2,
) -> pd.DataFrame:
    """Pair ENTER_SHORT and EXIT_SHORT rows into closed short trades."""
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
    open_positions: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for _, row in trades.sort_values("timestamp").iterrows():
        action = str(row["action"]).upper()
        symbol = str(row["symbol"])
        if action == "ENTER_SHORT":
            open_positions[symbol] = row.to_dict()
        elif action == "EXIT_SHORT" and symbol in open_positions:
            entry = open_positions.pop(symbol)
            entry_price = float(entry["price"])
            exit_price = float(row["price"])
            return_pct = (entry_price - exit_price) / entry_price * 100.0
            entry_time = pd.Timestamp(entry["timestamp"])
            exit_time = pd.Timestamp(row["timestamp"])
            rows.append(
                {
                    "trade_id": entry["trade_id"],
                    "symbol": symbol,
                    "entry_timestamp": entry_time,
                    "exit_timestamp": exit_time,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "size": abs(float(entry.get("target_weight", slot_weight))),
                    "pnl": return_pct / 100.0 * initial_cash * slot_weight,
                    "return_pct": return_pct,
                    "exit_reason": row.get("reason", ""),
                    "holding_days": int(max((exit_time - entry_time).days, 0)),
                    "status": "closed",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def compute_asset_performance(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    config: ETFAvalanchesConfig | None = None,
) -> pd.DataFrame:
    """Summarize per-ETF short/cash contribution, exposure, and drawdown."""
    cfg = config or ETFAvalanchesConfig()
    clean_prices = _validate_prices(prices).loc[:, weights.columns]
    asset_returns = clean_prices.pct_change(fill_method=None).fillna(0.0)
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
                "min_weight": float(symbol_weights.min()),
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


def generate_live_short_orders(
    *,
    current_weights: pd.Series,
    target_weights: pd.Series,
    portfolio_value: float,
    prices: pd.Series,
    min_weight_change: float = 0.005,
) -> pd.DataFrame:
    """Generate broker-agnostic orders from current to target ETF Avalanche weights."""
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
        delta = float(target[symbol] - current[symbol])
        if abs(delta) < min_weight_change:
            continue
        value_delta = delta * portfolio_value
        if value_delta < 0:
            action = "SELL_SHORT" if target[symbol] < 0 else "SELL"
        else:
            action = "BUY_TO_COVER" if current[symbol] < 0 else "BUY"
        rows.append(
            {
                "symbol": symbol,
                "action": action,
                "current_weight": float(current[symbol]),
                "target_weight": float(target[symbol]),
                "weight_delta": delta,
                "target_value_delta": value_delta,
                "estimated_quantity": abs(value_delta) / float(price),
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
    highs: pd.DataFrame,
    config: ETFAvalanchesConfig | None = None,
    *,
    broker_symbol_map: dict[str, str] | None = None,
    shortable_symbols: set[str] | None = None,
) -> dict[str, Any]:
    """Return live-readiness status and blockers for ETF Avalanches."""
    cfg = config or ETFAvalanchesConfig()
    clean_prices = _validate_prices(prices)
    clean_highs = _validate_prices(highs).reindex(clean_prices.index)
    required = set(cfg.live_required_symbols)
    available = set(clean_prices.columns) & set(clean_highs.columns)
    missing_data = sorted(required - available)
    symbol_map = broker_symbol_map or {}
    shortable = shortable_symbols or set()
    short_required = sorted(symbol for symbol in required if symbol != cfg.cash_symbol)
    missing_broker_symbols = sorted(symbol for symbol in required if symbol not in symbol_map)
    missing_shortable = sorted(symbol for symbol in short_required if symbol not in shortable)
    enough_history = len(clean_prices) > cfg.required_history
    blockers: list[str] = []
    if missing_data:
        blockers.append(f"missing OHLC data for: {', '.join(missing_data)}")
    if missing_broker_symbols:
        blockers.append(f"missing broker symbol mapping for: {', '.join(missing_broker_symbols)}")
    if missing_shortable:
        blockers.append(f"missing shortable confirmation for: {', '.join(missing_shortable)}")
    if not enough_history:
        blockers.append(f"need more than {cfg.required_history} rows of price history")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "available_symbols": sorted(available),
        "missing_data": missing_data,
        "missing_broker_symbols": missing_broker_symbols,
        "missing_shortable": missing_shortable,
        "rows": int(len(clean_prices)),
        "required_history": int(cfg.required_history),
    }


def compute_portfolio_metrics(
    returns: pd.Series,
    equity: pd.Series,
    drawdown: pd.Series,
    trades: pd.DataFrame,
    closed_trades: pd.DataFrame,
    config: ETFAvalanchesConfig,
) -> dict[str, float | int | None]:
    """Compute core performance metrics for a short strategy."""
    clean_returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    trade_count = int(len(closed_trades))
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
            "win_rate": None,
            "profit_factor": None,
        }
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) > 1 else 0.0
    periods = max(len(clean_returns), 1)
    annualized_return = (1.0 + total_return) ** (config.annualization / periods) - 1.0
    annualized_volatility = float(clean_returns.std(ddof=0) * math.sqrt(config.annualization))
    sharpe = annualized_return / annualized_volatility if annualized_volatility > 0 else None
    pnl = pd.to_numeric(closed_trades.get("pnl", pd.Series(dtype=float)), errors="coerce").dropna()
    gross_profit = float(pnl[pnl > 0].sum()) if len(pnl) else 0.0
    gross_loss = abs(float(pnl[pnl < 0].sum())) if len(pnl) else 0.0
    return {
        "total_return": total_return,
        "total_return_pct": total_return * 100.0,
        "annualized_return": float(annualized_return),
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": float(sharpe) if sharpe is not None else None,
        "max_drawdown": float(drawdown.min()),
        "max_drawdown_pct": float(drawdown.min() * 100.0),
        "trade_count": trade_count,
        "entry_count": int((trades["action"] == "ENTER_SHORT").sum()) if not trades.empty else 0,
        "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
    }


def _entry_candidates(
    *,
    signal_timestamp: pd.Timestamp,
    trade_timestamp: pd.Timestamp,
    short_symbols: list[str],
    holdings: set[str],
    prices: pd.DataFrame,
    highs: pd.DataFrame,
    rsi: pd.DataFrame,
    long_returns: pd.DataFrame,
    intermediate_returns: pd.DataFrame,
    volatility: pd.DataFrame,
    config: ETFAvalanchesConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in short_symbols:
        if symbol in holdings:
            continue
        close = prices.loc[signal_timestamp, symbol]
        high = highs.loc[trade_timestamp, symbol]
        rsi_value = rsi.loc[signal_timestamp, symbol]
        long_return = long_returns.loc[signal_timestamp, symbol]
        intermediate_return = intermediate_returns.loc[signal_timestamp, symbol]
        vol = volatility.loc[signal_timestamp, symbol]
        if any(pd.isna(value) for value in (close, high, rsi_value, long_return, intermediate_return, vol)):
            continue
        limit_price = float(close) * (1.0 + config.limit_entry_pct)
        filled = float(high) >= limit_price
        if float(long_return) < 0.0 and float(intermediate_return) < 0.0 and float(rsi_value) > config.entry_rsi and filled:
            rows.append(
                {
                    "signal_timestamp": signal_timestamp,
                    "trade_timestamp": trade_timestamp,
                    "symbol": symbol,
                    "close": float(close),
                    "high": float(high),
                    "limit_price": limit_price,
                    "rsi": float(rsi_value),
                    "long_return": float(long_return),
                    "intermediate_return": float(intermediate_return),
                    "volatility": float(vol),
                    "filled": True,
                }
            )
    rows.sort(key=lambda row: float(row["volatility"]), reverse=True)
    return rows


def _trade_row(
    *,
    timestamp: pd.Timestamp,
    symbol: str,
    action: str,
    price: float,
    target_weight: float,
    reason: str,
    trade_id: str,
    entry_price: float,
    pnl: float | None,
    return_pct: float | None,
    status: str,
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "timestamp": timestamp,
        "symbol": symbol,
        "action": action,
        "price": price,
        "target_weight": target_weight,
        "reason": reason,
        "entry_price": entry_price,
        "side": "short",
        "size": abs(target_weight) if target_weight else pd.NA,
        "pnl": pnl,
        "return_pct": return_pct,
        "status": status,
    }


def _short_symbols(columns: pd.Index, config: ETFAvalanchesConfig) -> list[str]:
    return [str(column) for column in columns if str(column) != config.cash_symbol]


def _rsi(prices: pd.DataFrame, *, period: int) -> pd.DataFrame:
    delta = prices.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.rolling(period, min_periods=period).mean()
    avg_loss = losses.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    fallback = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    fallback = fallback.mask(avg_loss.eq(0.0) & avg_gain.gt(0.0), 100.0)
    fallback = fallback.mask(avg_gain.eq(0.0) & avg_loss.gt(0.0), 0.0)
    return rsi.fillna(fallback)


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
    clean = _validate_prices(volumes)
    return clean.fillna(0.0).clip(lower=0.0)


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
