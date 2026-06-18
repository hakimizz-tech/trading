"""Signal preparation for Rising Assets portfolio backtests."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategies.RisingAssest.core import RisingAssetsConfig, compute_momentum_scores, generate_monthly_target_weights


@dataclass(frozen=True)
class RisingAssetsPreparedSignals:
    """Portfolio-level signal contract for monthly rotation strategies."""

    prices: pd.DataFrame
    momentum: pd.DataFrame
    target_weights: pd.DataFrame
    execution_weights: pd.DataFrame


def prepare_rising_assets_signals(
    prices: pd.DataFrame,
    *,
    config: RisingAssetsConfig | None = None,
) -> RisingAssetsPreparedSignals:
    """Prepare monthly target weights and one-bar delayed execution weights."""
    cfg = config or RisingAssetsConfig()
    momentum = compute_momentum_scores(prices, lookbacks=cfg.momentum_lookbacks)
    target_weights = generate_monthly_target_weights(prices, cfg)
    return RisingAssetsPreparedSignals(
        prices=prices.sort_index().astype(float).ffill(),
        momentum=momentum,
        target_weights=target_weights,
        execution_weights=target_weights.shift(1).fillna(0.0),
    )
