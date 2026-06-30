"""vectorbt adapter for ETF Avalanches."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from backtesting import VectorBTTargetOrdersConfig, run_vectorbt_target_orders
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
    cfg = strategy_config or ETFAvalanchesConfig()
    vbt_cfg = vectorbt_config or ETFAvalanchesVectorBTConfig(init_cash=cfg.initial_cash, fees=cfg.trading_cost)
    target_weights, trades, _ = generate_etf_avalanche_target_weights(prices, highs, cfg)
    target_orders = _target_order_matrix(target_weights)
    shared = run_vectorbt_target_orders(
        prices.loc[:, target_weights.columns],
        target_orders,
        config=VectorBTTargetOrdersConfig(
            init_cash=vbt_cfg.init_cash,
            fees=vbt_cfg.fees,
            slippage=vbt_cfg.slippage,
            freq=vbt_cfg.freq,
            direction="both",
        ),
    )
    pandas_result = backtest_etf_avalanches(prices, highs, cfg)
    metrics = compute_portfolio_metrics(
        shared.returns,
        shared.equity,
        shared.drawdown,
        trades,
        pandas_result.closed_trades,
        cfg,
    )
    pandas_result = replace(
        pandas_result,
        returns=shared.returns,
        equity=shared.equity,
        drawdown=shared.drawdown,
        metrics=metrics,
    )
    return ETFAvalanchesVectorBTResult(
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
    changed = target_weights.ne(target_weights.shift()).any(axis=1)
    orders = target_weights.where(changed).shift(1)
    return orders.dropna(how="all").reindex(target_weights.index)

