"""vectorbt adapter for Scalper Major High Volatility."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pandas as pd

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
    signals: pd.DataFrame


def run_scalper_major_vectorbt(
    ohlcv: pd.DataFrame,
    *,
    strategy_config: ScalperMajorConfig | None = None,
    vectorbt_config: ScalperMajorVectorBTConfig | None = None,
) -> ScalperMajorVectorBTResult:
    """Run Scalper Major through vectorbt from prepared entry/exit signals."""
    vbt = _require_vectorbt()
    cfg = strategy_config or ScalperMajorConfig()
    vbt_cfg = vectorbt_config or ScalperMajorVectorBTConfig(
        init_cash=cfg.initial_cash,
        fees=cfg.commission_per_turnover,
        slippage=cfg.slippage,
    )
    signals = generate_scalper_major_signals(ohlcv, cfg)
    portfolio = vbt.Portfolio.from_signals(
        close=ohlcv["close"],
        entries=signals["long_entry"],
        exits=signals["long_exit"],
        short_entries=signals["short_entry"],
        short_exits=signals["short_exit"],
        init_cash=vbt_cfg.init_cash,
        fees=vbt_cfg.fees,
        slippage=vbt_cfg.slippage,
        size=vbt_cfg.size,
        size_type="percent",
        freq=vbt_cfg.freq,
    )
    pandas_result = backtest_scalper_major(ohlcv, cfg)
    return ScalperMajorVectorBTResult(
        portfolio=portfolio,
        pandas_result=pandas_result,
        stats=portfolio.stats(),
        metrics=pandas_result.metrics,
        signals=signals,
    )


def _require_vectorbt() -> Any:
    try:
        return import_module("vectorbt")
    except ImportError as exc:
        raise RuntimeError(
            "vectorbt is not installed. Install research backtesting dependencies with "
            "`python -m pip install -r requirements-backtest.txt`."
        ) from exc
