"""vectorbt adapter for Directional Forex ML signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtesting import PreparedSignals, VectorBTConfig, run_vectorbt
from strategies.DirectionalForexML.core import (
    DirectionalForexMLArtifact,
    DirectionalForexMLConfig,
    backtest_directional_forex_ml,
    generate_directional_ml_signals,
)
from strategies.DirectionalForexML.features import compute_directional_features


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
    metrics: dict[str, float | int | None]
    signals: pd.DataFrame
    prepared_signals: PreparedSignals


def run_directional_forex_ml_vectorbt(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    artifact: DirectionalForexMLArtifact | None = None,
    strategy_config: DirectionalForexMLConfig | None = None,
    vectorbt_config: DirectionalForexMLVectorBTConfig | None = None,
    macro: pd.DataFrame | None = None,
) -> DirectionalForexMLVectorBTResult:
    """Run ML signals through vectorbt."""
    cfg = strategy_config or DirectionalForexMLConfig()
    pandas_result = (
        backtest_directional_forex_ml(ohlcv, symbol=symbol, config=cfg, macro=macro)
        if artifact is None
        else None
    )
    trained = artifact or pandas_result.artifact
    signals = generate_directional_ml_signals(ohlcv, trained, macro=macro)
    vbt_cfg = vectorbt_config or DirectionalForexMLVectorBTConfig(init_cash=cfg.initial_cash)
    fees = ohlcv["close"].map(trained.cost_spec.one_way_pct).reindex(signals.index).fillna(0.0)
    prepared = _prepare_directional_forex_ml_signals(ohlcv, signals, trained, macro=macro)
    shared = run_vectorbt(
        prepared,
        config=VectorBTConfig(
            init_cash=vbt_cfg.init_cash,
            fees=fees,
            size=vbt_cfg.size,
            size_type="percent",
            freq=vbt_cfg.freq,
        ),
    )
    return DirectionalForexMLVectorBTResult(
        portfolio=shared.portfolio,
        pandas_result=pandas_result,
        stats=shared.stats,
        metrics=shared.metrics,
        signals=signals,
        prepared_signals=prepared,
    )


def _prepare_directional_forex_ml_signals(
    ohlcv: pd.DataFrame,
    signals: pd.DataFrame,
    artifact: DirectionalForexMLArtifact,
    macro: pd.DataFrame | None = None,
) -> PreparedSignals:
    features = compute_directional_features(
        ohlcv,
        feature_set=artifact.config.feature_set,
        macro=macro,
        include_macro=artifact.config.use_macro_features,
    )
    data = ohlcv.reindex(signals.index).join(features.reindex(signals.index), how="left")
    data = data.join(signals, how="left")
    return PreparedSignals(
        data=data,
        close=ohlcv["close"].reindex(signals.index).astype(float),
        long_entries=signals["long_entry"].fillna(False).astype(bool),
        long_exits=signals["long_exit"].fillna(False).astype(bool),
        short_entries=signals["short_entry"].fillna(False).astype(bool),
        short_exits=signals["short_exit"].fillna(False).astype(bool),
        feature_columns=artifact.feature_columns,
        signal_columns=(
            "probability_up",
            "expected_move_pct",
            "one_way_cost_pct",
            "cost_hurdle_pct",
            "long_entry",
            "long_exit",
            "short_entry",
            "short_exit",
        ),
        minimum_feature_lag=1,
    )
