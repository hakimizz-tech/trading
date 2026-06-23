"""Directional forex machine-learning strategy and signal gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from market_data.ohlcv import validate_ohlcv
from strategies.DirectionalForexML.analytics import performance_metrics
from strategies.DirectionalForexML.config import DirectionalForexMLConfig, FeatureSet, ModelName
from strategies.DirectionalForexML.costs import (
    PAPER_FOREX_COSTS,
    USD_BASE_TO_PAPER_SYMBOL,
    ForexCostSpec,
    break_even_move_pct,
    cost_spec_for_symbol,
)
from strategies.DirectionalForexML.features import compute_directional_features, invert_usd_base_quote
from strategies.DirectionalForexML.labels import build_directional_labels, prepare_ml_dataset
from strategies.DirectionalForexML.models import (
    DirectionalForexMLArtifact,
    madl_score,
    optimize_probability_threshold,
    predict_directional_probabilities,
    train_directional_forex_model,
)


@dataclass(frozen=True)
class DirectionalForexMLResult:
    """Backtest artifacts for a trained directional forex ML strategy."""

    data: pd.DataFrame
    features: pd.DataFrame
    labels: pd.Series
    probabilities: pd.Series
    signals: pd.DataFrame
    returns: pd.Series
    equity: pd.Series
    drawdown: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, float | int | None | str]
    artifact: DirectionalForexMLArtifact


def estimate_expected_move(
    ohlcv: pd.DataFrame,
    probabilities: pd.Series,
    *,
    window: int = 20,
) -> pd.Series:
    """Estimate tradable move size from probability confidence and past volatility."""
    data = validate_ohlcv(ohlcv)
    realized_abs = data["close"].pct_change(fill_method=None).abs().rolling(window).mean()
    confidence = (probabilities - 0.5).abs() * 2.0
    return (confidence * realized_abs.reindex(probabilities.index)).rename("expected_move_pct")


def generate_directional_ml_signals(
    ohlcv: pd.DataFrame,
    artifact: DirectionalForexMLArtifact,
    *,
    macro: pd.DataFrame | None = None,
    probability_threshold: float | None = None,
    cost_multiplier: float = 1.0,
) -> pd.DataFrame:
    """Generate standalone long/short ML signals after cost-aware filtering."""
    cfg = artifact.config
    threshold = probability_threshold
    if threshold is None:
        threshold = artifact.selected_threshold or cfg.probability_threshold
    data = validate_ohlcv(ohlcv)
    probabilities = predict_directional_probabilities(data, artifact, macro=macro)
    expected_move = estimate_expected_move(data, probabilities, window=cfg.expected_move_window)
    one_way_cost = data["close"].reindex(probabilities.index).map(artifact.cost_spec.one_way_pct)
    hurdle = one_way_cost * cost_multiplier + cfg.cost_buffer_pct
    long_entry = probabilities.ge(threshold) & expected_move.gt(hurdle)
    short_entry = probabilities.le(1.0 - threshold) & expected_move.gt(hurdle)
    signals = pd.DataFrame(
        {
            "probability_up": probabilities,
            "expected_move_pct": expected_move,
            "one_way_cost_pct": one_way_cost,
            "cost_hurdle_pct": hurdle,
            "long_entry": long_entry.fillna(False),
            "short_entry": short_entry.fillna(False),
        },
        index=probabilities.index,
    )
    signals["long_exit"] = signals["long_entry"].shift(cfg.horizon, fill_value=False).astype(bool)
    signals["short_exit"] = signals["short_entry"].shift(cfg.horizon, fill_value=False).astype(bool)
    return signals


def apply_ml_probability_gate(
    base_long_entries: pd.Series,
    base_short_entries: pd.Series,
    probabilities: pd.Series,
    expected_move: pd.Series,
    cost_hurdle: pd.Series,
    *,
    threshold: float = 0.54,
) -> pd.DataFrame:
    """Filter another strategy's entries with ML probability and cost hurdle."""
    index = base_long_entries.index.union(base_short_entries.index).union(probabilities.index)
    prob = probabilities.reindex(index)
    move = expected_move.reindex(index)
    hurdle = cost_hurdle.reindex(index)
    long_approved = base_long_entries.reindex(index, fill_value=False) & prob.ge(threshold) & move.gt(hurdle)
    short_approved = base_short_entries.reindex(index, fill_value=False) & prob.le(1.0 - threshold) & move.gt(hurdle)
    return pd.DataFrame(
        {
            "ml_long_approved": long_approved.fillna(False),
            "ml_short_approved": short_approved.fillna(False),
            "ml_probability_up": prob,
            "ml_expected_move_pct": move,
            "ml_cost_hurdle_pct": hurdle,
        },
        index=index,
    )


def build_ml_gate_for_signals(
    ohlcv: pd.DataFrame,
    base_signals: pd.DataFrame,
    artifact: DirectionalForexMLArtifact,
    *,
    macro: pd.DataFrame | None = None,
    long_column: str = "long_entry",
    short_column: str = "short_entry",
    threshold: float | None = None,
    cost_multiplier: float = 1.0,
) -> pd.DataFrame:
    """Build ML approvals for a base strategy signal table."""
    signals = generate_directional_ml_signals(
        ohlcv,
        artifact,
        macro=macro,
        probability_threshold=threshold,
        cost_multiplier=cost_multiplier,
    )
    if long_column not in base_signals.columns or short_column not in base_signals.columns:
        raise ValueError(f"base_signals must include {long_column!r} and {short_column!r}")
    return apply_ml_probability_gate(
        base_long_entries=base_signals[long_column],
        base_short_entries=base_signals[short_column],
        probabilities=signals["probability_up"],
        expected_move=signals["expected_move_pct"],
        cost_hurdle=signals["cost_hurdle_pct"],
        threshold=threshold if threshold is not None else artifact.config.probability_threshold,
    )


def backtest_directional_forex_ml(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    config: DirectionalForexMLConfig | None = None,
    macro: pd.DataFrame | None = None,
    cost_spec: ForexCostSpec | None = None,
    train_fraction: float | None = None,
    cost_multiplier: float = 1.0,
) -> DirectionalForexMLResult:
    """Train on the first window and evaluate one-period OOS ML signals."""
    cfg = config or DirectionalForexMLConfig()
    data = validate_ohlcv(ohlcv)
    split_fraction = train_fraction if train_fraction is not None else cfg.train_fraction
    split_idx = int(len(data) * split_fraction)
    if split_idx <= cfg.expected_move_window or split_idx >= len(data) - cfg.horizon:
        raise ValueError("dataset is too small for train/test split")

    train = data.iloc[:split_idx]
    artifact = train_directional_forex_model(
        train,
        symbol=symbol,
        config=cfg,
        macro=macro.reindex(train.index) if macro is not None else None,
        cost_spec=cost_spec,
    )
    signals = generate_directional_ml_signals(data, artifact, macro=macro, cost_multiplier=cost_multiplier)
    features, labels, forward_returns = prepare_ml_dataset(data, cfg, macro=macro)
    test_index = forward_returns.index[forward_returns.index >= data.index[split_idx]]
    probabilities = signals["probability_up"].reindex(test_index).dropna()
    test_index = probabilities.index
    direction = pd.Series(0.0, index=test_index, name="direction")
    direction.loc[signals["long_entry"].reindex(test_index, fill_value=False)] = 1.0
    direction.loc[signals["short_entry"].reindex(test_index, fill_value=False)] = -1.0
    costs = data["close"].reindex(test_index).map(artifact.cost_spec.round_trip_pct).fillna(0.0) * cost_multiplier
    returns = direction * forward_returns.reindex(test_index) - np.where(direction.ne(0.0), costs, 0.0)
    returns = returns.fillna(0.0).rename("returns")
    equity = (1.0 + returns).cumprod() * cfg.initial_cash
    equity.name = "equity"
    drawdown = (equity / equity.cummax() - 1.0).rename("drawdown")
    trades = _trades_from_one_period_signals(data, direction, forward_returns.reindex(test_index), costs, horizon=cfg.horizon)
    metrics = performance_metrics(returns, equity, trades, initial_cash=cfg.initial_cash, annualization=cfg.annualization)
    metrics["model_name"] = artifact.model_name
    metrics["symbol"] = symbol.upper()
    metrics["validation_score"] = artifact.validation_score
    metrics["selected_threshold"] = artifact.selected_threshold
    report_data = data.reindex(test_index).copy()
    return DirectionalForexMLResult(
        data=report_data,
        features=features.reindex(test_index),
        labels=labels.reindex(test_index),
        probabilities=probabilities,
        signals=signals.reindex(test_index),
        returns=returns,
        equity=equity,
        drawdown=drawdown,
        trades=trades,
        metrics=metrics,
        artifact=artifact,
    )


def _trades_from_one_period_signals(
    data: pd.DataFrame,
    direction: pd.Series,
    forward_returns: pd.Series,
    costs: pd.Series,
    *,
    horizon: int = 1,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for timestamp, side_value in direction[direction.ne(0.0)].items():
        entry_price = float(data["open"].reindex([timestamp]).iloc[0])
        exit_pos = data.index.get_indexer([timestamp])[0] + horizon
        exit_timestamp = data.index[min(exit_pos, len(data.index) - 1)]
        exit_price = float(data["close"].iloc[min(exit_pos, len(data.index) - 1)])
        gross_return = float(side_value * forward_returns.loc[timestamp])
        net_return = gross_return - float(costs.loc[timestamp])
        rows.append(
            {
                "entry_timestamp": timestamp,
                "exit_timestamp": exit_timestamp,
                "direction": "long" if side_value > 0 else "short",
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return_pct": gross_return * 100.0,
                "cost_pct": float(costs.loc[timestamp]) * 100.0,
                "return_pct": net_return * 100.0,
                "pnl": net_return,
                "exit_reason": "horizon_exit",
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "DirectionalForexMLArtifact",
    "DirectionalForexMLConfig",
    "DirectionalForexMLResult",
    "FeatureSet",
    "ForexCostSpec",
    "ModelName",
    "PAPER_FOREX_COSTS",
    "USD_BASE_TO_PAPER_SYMBOL",
    "apply_ml_probability_gate",
    "backtest_directional_forex_ml",
    "break_even_move_pct",
    "build_directional_labels",
    "build_ml_gate_for_signals",
    "compute_directional_features",
    "cost_spec_for_symbol",
    "estimate_expected_move",
    "generate_directional_ml_signals",
    "invert_usd_base_quote",
    "madl_score",
    "optimize_probability_threshold",
    "predict_directional_probabilities",
    "prepare_ml_dataset",
    "train_directional_forex_model",
]
