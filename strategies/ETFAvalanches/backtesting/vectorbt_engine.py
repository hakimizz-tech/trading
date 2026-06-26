"""vectorbt adapter for ETF Avalanches."""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import import_module
from typing import Any

import pandas as pd

from strategies.ETFAvalanches.core import (
    ETFAvalanchesConfig,
    ETFAvalanchesResult,
    backtest_etf_avalanches,
    compute_portfolio_metrics,
    generate_etf_avalanche_target_weights,
)


@dataclass(frozen=True)
class ETFAvalanchesVectorBTConfig:
    """Execution assumptions for vectorbt target-percent orders."""

    init_cash: float = 10_000.0
    fees: float = 0.0
    slippage: float = 0.0
    freq: str = "1d"


@dataclass(frozen=True)
class ETFAvalanchesVectorBTResult:
    """vectorbt portfolio plus ETF Avalanches artifacts."""

    portfolio: Any
    pandas_result: ETFAvalanchesResult
    metrics: dict[str, float | int | None]
    stats: pd.Series
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series
    target_orders: pd.DataFrame


def run_etf_avalanches_vectorbt(
    prices: pd.DataFrame,
    highs: pd.DataFrame,
    *,
    strategy_config: ETFAvalanchesConfig | None = None,
    vectorbt_config: ETFAvalanchesVectorBTConfig | None = None,
) -> ETFAvalanchesVectorBTResult:
    """Run ETF Avalanches through vectorbt target-percent orders."""
    vbt = _require_vectorbt()
    cfg = strategy_config or ETFAvalanchesConfig()
    vbt_cfg = vectorbt_config or ETFAvalanchesVectorBTConfig(init_cash=cfg.initial_cash, fees=cfg.trading_cost)
    target_weights, trades, _ = generate_etf_avalanche_target_weights(prices, highs, cfg)
    target_orders = _target_order_matrix(target_weights)
    portfolio = vbt.Portfolio.from_orders(
        close=prices.loc[:, target_weights.columns],
        size=target_orders,
        size_type=vbt.portfolio.enums.SizeType.TargetPercent,
        direction="both",
        init_cash=vbt_cfg.init_cash,
        cash_sharing=True,
        group_by=True,
        fees=vbt_cfg.fees,
        slippage=vbt_cfg.slippage,
        freq=vbt_cfg.freq,
    )
    equity = _portfolio_series(portfolio.value)
    returns = equity.pct_change(fill_method=None).fillna(0.0)
    drawdown = equity / equity.cummax() - 1.0
    pandas_result = backtest_etf_avalanches(prices, highs, cfg)
    metrics = compute_portfolio_metrics(returns, equity, drawdown, trades, pandas_result.closed_trades, cfg)
    pandas_result = replace(pandas_result, returns=returns, equity=equity, drawdown=drawdown, metrics=metrics)
    return ETFAvalanchesVectorBTResult(
        portfolio=portfolio,
        pandas_result=pandas_result,
        metrics=metrics,
        stats=portfolio.stats(),
        equity=equity,
        returns=returns,
        drawdown=drawdown,
        target_orders=target_orders,
    )


def _target_order_matrix(target_weights: pd.DataFrame) -> pd.DataFrame:
    changed = target_weights.ne(target_weights.shift()).any(axis=1)
    orders = target_weights.where(changed).shift(1)
    return orders.dropna(how="all").reindex(target_weights.index)


def _portfolio_series(fn: Any) -> pd.Series:
    value = fn()
    if isinstance(value, pd.DataFrame):
        if value.shape[1] == 1:
            return value.iloc[:, 0].astype(float)
        return value.sum(axis=1).astype(float)
    if isinstance(value, pd.Series):
        return value.astype(float)
    return pd.Series(value, dtype=float)


def _require_vectorbt() -> Any:
    try:
        return import_module("vectorbt")
    except ImportError as exc:
        raise RuntimeError(
            "vectorbt is not installed. Install research backtesting dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc
