"""Label creation and ML matrix preparation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_data.ohlcv import validate_ohlcv
from strategies.DirectionalForexML.config import DirectionalForexMLConfig
from strategies.DirectionalForexML.features import compute_directional_features


def build_directional_labels(
    ohlcv: pd.DataFrame,
    *,
    horizon: int = 1,
) -> tuple[pd.Series, pd.Series]:
    """Return binary direction labels and realized open-to-future-close returns."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    data = validate_ohlcv(ohlcv)
    future_close = data["close"].shift(-horizon)
    forward_return = future_close / data["open"].replace(0.0, np.nan) - 1.0
    labels = forward_return.gt(0.0).astype("int64").rename("target_up")
    labels[forward_return.isna()] = pd.NA
    return labels, forward_return.rename("forward_return")


def prepare_ml_dataset(
    ohlcv: pd.DataFrame,
    config: DirectionalForexMLConfig | None = None,
    *,
    macro: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return aligned features, labels, and forward returns."""
    cfg = config or DirectionalForexMLConfig()
    features = compute_directional_features(
        ohlcv,
        feature_set=cfg.feature_set,
        macro=macro,
        include_macro=cfg.use_macro_features,
    )
    labels, forward_returns = build_directional_labels(ohlcv, horizon=cfg.horizon)
    dataset = pd.concat([features, labels, forward_returns], axis=1).dropna()
    feature_columns = list(features.columns)
    return (
        dataset[feature_columns].astype(float),
        dataset["target_up"].astype(int),
        dataset["forward_return"].astype(float),
    )
