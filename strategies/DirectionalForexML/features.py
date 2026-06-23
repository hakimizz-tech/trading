"""No-lookahead feature construction for Directional Forex ML."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_data.ohlcv import validate_ohlcv
from strategies.DirectionalForexML.config import FeatureSet


def compute_directional_features(
    ohlcv: pd.DataFrame,
    *,
    feature_set: FeatureSet = "paper_technical",
    macro: pd.DataFrame | None = None,
    include_macro: bool = False,
) -> pd.DataFrame:
    """Build leakage-safe technical and optional macro features.

    Completed OHLC features are shifted by one bar because the decision is made
    at the current open. The current opening gap is allowed because it is known
    at decision time.
    """
    data = validate_ohlcv(ohlcv)
    close = data["close"]
    previous_close = close.shift(1)
    completed_return = np.log(close / previous_close)
    completed_range = (data["high"] - data["low"]) / close.replace(0.0, np.nan)
    features = pd.DataFrame(index=data.index)
    features["daily_return"] = completed_return.shift(1)
    features["high_low_range"] = completed_range.shift(1)
    features["opening_gap"] = (data["open"] - previous_close) / previous_close.replace(0.0, np.nan)
    if feature_set == "extended":
        features["abs_return"] = completed_return.abs().shift(1)
        features["rolling_vol_20"] = completed_return.rolling(20).std(ddof=0).shift(1)
        features["rolling_return_5"] = close.pct_change(5, fill_method=None).shift(1)
        features["rolling_return_20"] = close.pct_change(20, fill_method=None).shift(1)
        features["rolling_skew_20"] = completed_return.rolling(20).skew().shift(1)
        features["rolling_kurtosis_20"] = completed_return.rolling(20).kurt().shift(1)
    elif feature_set != "paper_technical":
        raise ValueError("feature_set must be 'paper_technical' or 'extended'")

    if include_macro and macro is not None and not macro.empty:
        aligned = macro.reindex(data.index).ffill()
        for column in aligned.columns:
            features[f"macro_{column}"] = pd.to_numeric(aligned[column], errors="coerce").shift(1)
            features[f"macro_{column}_change"] = features[f"macro_{column}"].diff()
        if {"rate_5y", "rate_13w"}.issubset(set(aligned.columns)):
            features["macro_yield_slope"] = aligned["rate_5y"].shift(1) - aligned["rate_13w"].shift(1)
            features["macro_yield_slope_change"] = features["macro_yield_slope"].diff()

    return features.replace([np.inf, -np.inf], np.nan)


def rolling_zscore(features: pd.DataFrame, *, window: int = 60) -> pd.DataFrame:
    """Rolling z-score normalization without full-sample leakage."""
    mean = features.rolling(window).mean()
    std = features.rolling(window).std(ddof=0)
    return ((features - mean) / std.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)


def invert_usd_base_quote(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Convert broker-style USDXXX OHLC into paper-style XXXUSD OHLC."""
    data = validate_ohlcv(ohlcv)
    inverted = pd.DataFrame(index=data.index)
    inverted["open"] = 1.0 / data["open"].replace(0.0, np.nan)
    inverted["high"] = 1.0 / data["low"].replace(0.0, np.nan)
    inverted["low"] = 1.0 / data["high"].replace(0.0, np.nan)
    inverted["close"] = 1.0 / data["close"].replace(0.0, np.nan)
    inverted["volume"] = data["volume"]
    inverted.attrs.update(data.attrs)
    inverted.attrs["inverted_quote"] = True
    return validate_ohlcv(inverted.dropna(subset=["open", "high", "low", "close"]))
