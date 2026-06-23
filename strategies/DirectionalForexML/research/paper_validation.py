"""Paper-style validation helpers for Directional Forex ML."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from market_data.ohlcv import validate_ohlcv
from strategies.DirectionalForexML.config import DirectionalForexMLConfig
from strategies.DirectionalForexML.core import backtest_directional_forex_ml


PAPER_REGIME_PERIODS: dict[str, tuple[str, str]] = {
    "pre_covid": ("2018-01-01", "2019-12-31"),
    "covid": ("2020-01-01", "2021-12-31"),
    "post_covid": ("2022-01-01", "2023-12-31"),
    "full": ("2018-01-01", "2023-12-31"),
}


def run_regime_period_validation(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    config: DirectionalForexMLConfig,
    macro: pd.DataFrame | None = None,
    periods: dict[str, tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Evaluate the paper's pre-COVID, COVID, post-COVID, and full periods."""
    data = validate_ohlcv(ohlcv)
    rows: list[dict[str, object]] = []
    for period_name, (start, end) in (periods or PAPER_REGIME_PERIODS).items():
        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        period_data = data.loc[(data.index >= start_ts) & (data.index <= end_ts)]
        period_macro = macro.reindex(period_data.index) if macro is not None and not period_data.empty else None
        try:
            result = backtest_directional_forex_ml(period_data, symbol=symbol, config=config, macro=period_macro)
            row = {"period": period_name, "start": period_data.index.min(), "end": period_data.index.max(), **result.metrics}
        except ValueError as exc:
            row = {"period": period_name, "start": start, "end": end, "error": str(exc)}
        rows.append(row)
    return pd.DataFrame(rows)


def run_future_validation(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    config: DirectionalForexMLConfig,
    train_end: str = "2022-12-31",
    future_start: str = "2023-01-01",
    macro: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Train through one date and evaluate on a future-only validation period."""
    data = validate_ohlcv(ohlcv)
    train_end_ts = pd.Timestamp(train_end, tz="UTC")
    future_start_ts = pd.Timestamp(future_start, tz="UTC")
    combined = data.loc[data.index <= train_end_ts].copy()
    future = data.loc[data.index >= future_start_ts].copy()
    if combined.empty or future.empty:
        raise ValueError("future validation requires both train and future rows")
    joined = pd.concat([combined, future])
    split_fraction = len(combined) / len(joined)
    result = backtest_directional_forex_ml(
        joined,
        symbol=symbol,
        config=config,
        macro=macro.reindex(joined.index) if macro is not None else None,
        train_fraction=split_fraction,
    )
    return {
        "train_end": train_end,
        "future_start": future_start,
        "future_rows": len(future),
        **result.metrics,
    }


def run_cost_sensitivity(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    config: DirectionalForexMLConfig,
    multipliers: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0),
    macro: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Evaluate strategy performance under spread/cost multipliers."""
    rows: list[dict[str, object]] = []
    for multiplier in multipliers:
        try:
            result = backtest_directional_forex_ml(
                ohlcv,
                symbol=symbol,
                config=replace(config),
                macro=macro,
                cost_multiplier=multiplier,
            )
            row = {"cost_multiplier": multiplier, **result.metrics}
        except ValueError as exc:
            row = {"cost_multiplier": multiplier, "error": str(exc)}
        rows.append(row)
    return pd.DataFrame(rows)

