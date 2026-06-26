"""vectorbt adapter for Directional Forex ML signals."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pandas as pd

from strategies.DirectionalForexML.core import (
    DirectionalForexMLArtifact,
    DirectionalForexMLConfig,
    backtest_directional_forex_ml,
    generate_directional_ml_signals,
)


@dataclass(frozen=True)
class DirectionalForexMLVectorBTConfig:
    """Execution assumptions for vectorbt portfolio simulation."""

    init_cash: float = 10_000.0
    size: float = 0.95
    freq: str = "1d"


@dataclass(frozen=True)
class DirectionalForexMLVectorBTResult:
    """vectorbt portfolio plus pandas artifacts."""

    portfolio: Any
    pandas_result: Any
    stats: pd.Series
    signals: pd.DataFrame


def run_directional_forex_ml_vectorbt(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    artifact: DirectionalForexMLArtifact | None = None,
    strategy_config: DirectionalForexMLConfig | None = None,
    vectorbt_config: DirectionalForexMLVectorBTConfig | None = None,
) -> DirectionalForexMLVectorBTResult:
    """Run ML signals through vectorbt."""
    vbt = _require_vectorbt()
    cfg = strategy_config or DirectionalForexMLConfig()
    pandas_result = (
        backtest_directional_forex_ml(ohlcv, symbol=symbol, config=cfg)
        if artifact is None
        else None
    )
    trained = artifact or pandas_result.artifact
    signals = generate_directional_ml_signals(ohlcv, trained)
    vbt_cfg = vectorbt_config or DirectionalForexMLVectorBTConfig(init_cash=cfg.initial_cash)
    fees = ohlcv["close"].map(trained.cost_spec.one_way_pct).reindex(signals.index).fillna(0.0)
    portfolio = vbt.Portfolio.from_signals(
        close=ohlcv["close"].reindex(signals.index),
        entries=signals["long_entry"],
        exits=signals["long_exit"],
        short_entries=signals["short_entry"],
        short_exits=signals["short_exit"],
        init_cash=vbt_cfg.init_cash,
        fees=fees,
        size=vbt_cfg.size,
        size_type="percent",
        freq=vbt_cfg.freq,
    )
    return DirectionalForexMLVectorBTResult(
        portfolio=portfolio,
        pandas_result=pandas_result,
        stats=portfolio.stats(),
        signals=signals,
    )


def _require_vectorbt() -> Any:
    try:
        return import_module("vectorbt")
    except ImportError as exc:
        raise RuntimeError(
            "vectorbt is not installed. Install research backtesting dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc
