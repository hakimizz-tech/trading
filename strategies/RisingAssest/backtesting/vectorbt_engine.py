"""vectorbt adapter for Rising Assets portfolio rotation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from backtesting import VectorBTTargetOrdersConfig, run_vectorbt_target_orders
from strategies.RisingAssest.core import (
    RisingAssetsBacktestResult,
    RisingAssetsConfig,
    backtest_rising_assets,
    compute_portfolio_metrics,
    generate_monthly_target_weights,
)


@dataclass(frozen=True)
class RisingAssetsVectorBTConfig:
    init_cash: float = 10_000.0
    fees: float = 0.0
    slippage: float = 0.0
    freq: str = "1d"


@dataclass(frozen=True)
class RisingAssetsVectorBTResult:
    portfolio: Any
    pandas_result: RisingAssetsBacktestResult
    metrics: dict[str, float | int | None]
    stats: pd.Series
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series
    target_orders: pd.DataFrame


def run_rising_assets_vectorbt(
    prices: pd.DataFrame,
    *,
    strategy_config: RisingAssetsConfig | None = None,
    vectorbt_config: RisingAssetsVectorBTConfig | None = None,
) -> RisingAssetsVectorBTResult:
    """Run Rising Assets through vectorbt ``Portfolio.from_orders``."""
    cfg = strategy_config or RisingAssetsConfig()
    vbt_cfg = vectorbt_config or RisingAssetsVectorBTConfig(init_cash=cfg.initial_cash, fees=cfg.trading_cost)
    target_weights = generate_monthly_target_weights(prices, cfg)
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
    pandas_result = backtest_rising_assets(prices, cfg)
    metrics = compute_portfolio_metrics(shared.returns, shared.equity, shared.drawdown, cfg)
    metrics["rebalance_count"] = pandas_result.metrics.get("rebalance_count")
    pandas_result = replace(
        pandas_result,
        returns=shared.returns,
        equity=shared.equity,
        drawdown=shared.drawdown,
        metrics=metrics,
    )
    return RisingAssetsVectorBTResult(
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
    """Return sparse target-percent orders shifted one bar after rebalance."""
    changed = target_weights.ne(target_weights.shift()).any(axis=1)
    orders = target_weights.where(changed).shift(1)
    return orders.dropna(how="all").reindex(target_weights.index)

