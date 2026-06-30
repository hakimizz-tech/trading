"""vectorbt adapter for Scalper Major High Volatility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtesting import PreparedSignals, VectorBTConfig, run_vectorbt
from strategies.ScalperMajorHighVolatility.core import (
    ScalperMajorConfig,
    ScalperMajorResult,
    backtest_scalper_major,
    generate_scalper_major_signals,
)


@dataclass(frozen=True)
class ScalperMajorVectorBTConfig:
    """Execution assumptions for vectorbt signal simulation."""

    init_cash: float = 20_000.0
    fees: float = 0.00007
    slippage: float = 0.00005
    size: float = 0.95
    freq: str = "1h"


@dataclass(frozen=True)
class ScalperMajorVectorBTResult:
    """vectorbt portfolio plus pandas strategy artifacts."""

    portfolio: Any
    pandas_result: ScalperMajorResult
    stats: pd.Series
    metrics: dict[str, float | int | None]
    vectorbt_metrics: dict[str, float | int | None]
    signals: pd.DataFrame
    prepared_signals: PreparedSignals


def run_scalper_major_vectorbt(
    ohlcv: pd.DataFrame,
    *,
    strategy_config: ScalperMajorConfig | None = None,
    vectorbt_config: ScalperMajorVectorBTConfig | None = None,
) -> ScalperMajorVectorBTResult:
    """Run Scalper Major through vectorbt from prepared entry/exit signals."""
    cfg = strategy_config or ScalperMajorConfig()
    vbt_cfg = vectorbt_config or ScalperMajorVectorBTConfig(
        init_cash=cfg.initial_cash,
        fees=cfg.commission_per_turnover,
        slippage=cfg.slippage,
    )
    signals = generate_scalper_major_signals(ohlcv, cfg)
    prepared = _prepare_scalper_major_signals(ohlcv, signals)
    shared = run_vectorbt(
        prepared,
        config=VectorBTConfig(
            init_cash=vbt_cfg.init_cash,
            fees=vbt_cfg.fees,
            slippage=vbt_cfg.slippage,
            size=vbt_cfg.size,
            size_type="percent",
            freq=vbt_cfg.freq,
        ),
    )
    pandas_result = backtest_scalper_major(ohlcv, cfg)
    return ScalperMajorVectorBTResult(
        portfolio=shared.portfolio,
        pandas_result=pandas_result,
        stats=shared.stats,
        metrics=pandas_result.metrics,
        vectorbt_metrics=shared.metrics,
        signals=signals,
        prepared_signals=prepared,
    )


def _prepare_scalper_major_signals(ohlcv: pd.DataFrame, signals: pd.DataFrame) -> PreparedSignals:
    data = ohlcv.join(signals, how="left")
    return PreparedSignals(
        data=data,
        close=ohlcv["close"].astype(float),
        long_entries=signals["long_entry"].fillna(False).astype(bool),
        long_exits=signals["long_exit"].fillna(False).astype(bool),
        short_entries=signals["short_entry"].fillna(False).astype(bool),
        short_exits=signals["short_exit"].fillna(False).astype(bool),
        signal_columns=("long_entry", "long_exit", "short_entry", "short_exit"),
        minimum_feature_lag=1,
    )
