"""vectorbt adapter for Connors Research Weekly Mean Reversion."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from backtesting import VectorBTTargetOrdersConfig, run_vectorbt_target_orders
from strategies.ConnorsResearchWeeklyMeanReversion.core import (
    ConnorsWeeklyMeanReversionConfig,
    ConnorsWeeklyMeanReversionResult,
    backtest_connors_weekly_mean_reversion,
    compute_portfolio_metrics,
    generate_connors_target_weights,
)


@dataclass(frozen=True)
class ConnorsVectorBTConfig:
    """Execution assumptions for the vectorbt backtest."""

    init_cash: float = 10_000.0
    fees: float = 0.0
    slippage: float = 0.0
    freq: str = "1d"


@dataclass(frozen=True)
class ConnorsVectorBTResult:
    """vectorbt portfolio plus strategy artifacts."""

    portfolio: Any
    pandas_result: ConnorsWeeklyMeanReversionResult
    metrics: dict[str, float | int | None]
    stats: pd.Series
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series
    target_orders: pd.DataFrame


def run_connors_vectorbt(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    strategy_config: ConnorsWeeklyMeanReversionConfig | None = None,
    vectorbt_config: ConnorsVectorBTConfig | None = None,
) -> ConnorsVectorBTResult:
    """Run Connors Weekly Mean Reversion through vectorbt target orders."""
    cfg = strategy_config or ConnorsWeeklyMeanReversionConfig()
    vbt_cfg = vectorbt_config or ConnorsVectorBTConfig(init_cash=cfg.initial_cash, fees=cfg.trading_cost)
    target_weights, trades = generate_connors_target_weights(prices, volumes, cfg)
    target_orders = _target_order_matrix(target_weights)
    shared = run_vectorbt_target_orders(
        prices,
        target_orders,
        config=VectorBTTargetOrdersConfig(
            init_cash=vbt_cfg.init_cash,
            fees=vbt_cfg.fees,
            slippage=vbt_cfg.slippage,
            freq=vbt_cfg.freq,
            direction="longonly",
        ),
    )
    pandas_result = backtest_connors_weekly_mean_reversion(prices, volumes, cfg)
    metrics = compute_portfolio_metrics(shared.returns, shared.equity, shared.drawdown, trades, cfg)
    pandas_result = replace(
        pandas_result,
        returns=shared.returns,
        equity=shared.equity,
        drawdown=shared.drawdown,
        metrics=metrics,
    )
    return ConnorsVectorBTResult(
        portfolio=shared.portfolio,
        pandas_result=pandas_result,
        metrics=metrics,
        stats=shared.stats,
        equity=shared.equity,
        returns=shared.returns,
        drawdown=shared.drawdown,
        target_orders=target_orders,
    )


def _target_order_matrix(target_weights: pd.DataFrame) -> pd.DataFrame:
    """Return sparse target-percent orders shifted one bar after target changes."""
    changed = target_weights.ne(target_weights.shift()).any(axis=1)
    orders = target_weights.where(changed).shift(1)
    return orders.dropna(how="all").reindex(target_weights.index)

