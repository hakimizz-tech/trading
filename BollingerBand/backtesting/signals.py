"""Shared signal preparation for backtesting engines."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from BollingerBand.core import (
    AdaptiveRegimeConfig,
    ExitPlan,
    add_atr,
    calculate_bollinger_bands,
    generate_adaptive_bollinger_signals,
    generate_bb_rsi_signals,
    generate_bbma_signals,
    generate_mean_reversion_signals,
)


@dataclass(frozen=True)
class PreparedSignals:
    """Normalized strategy signals for backtesting engines."""

    data: pd.DataFrame
    close: pd.Series
    long_entries: pd.Series
    long_exits: pd.Series
    short_entries: pd.Series
    short_exits: pd.Series
    stop_loss: pd.Series | None = None
    take_profit: pd.Series | None = None


def prepare_bollinger_signals(
    data: pd.DataFrame,
    *,
    strategy: str = "adaptive",
    adaptive_config: AdaptiveRegimeConfig | None = None,
    exit_plan: ExitPlan | None = None,
    price_col: str = "close",
) -> PreparedSignals:
    """Prepare Bollinger strategy signals for vectorized/event engines."""
    if strategy == "adaptive":
        signaled = generate_adaptive_bollinger_signals(data, config=adaptive_config, price_col=price_col)
    else:
        config = adaptive_config or AdaptiveRegimeConfig()
        enriched = calculate_bollinger_bands(
            data,
            window=config.bb_window,
            num_std=config.bb_num_std,
            price_col=price_col,
        )
        if strategy == "mean_reversion":
            signaled = generate_mean_reversion_signals(enriched, price_col=price_col)
        elif strategy == "bbma":
            signaled = generate_bbma_signals(enriched, price_col=price_col)
        elif strategy == "bb_rsi":
            signaled = generate_bb_rsi_signals(enriched, price_col=price_col)
        else:
            raise ValueError("strategy must be one of: adaptive, mean_reversion, bbma, bb_rsi")

    close = signaled[price_col].astype(float)
    stop_loss = None
    take_profit = None

    if exit_plan is not None:
        with_atr = add_atr(signaled, window=exit_plan.atr_length)
        atr = with_atr[f"atr_{exit_plan.atr_length}"].astype(float)
        stop_loss = (atr * exit_plan.atr_stop_multiplier / close).clip(lower=0.0)
        take_profit = stop_loss * exit_plan.take_profit_rr
        signaled[f"atr_{exit_plan.atr_length}"] = atr
        signaled["sl_stop_pct"] = stop_loss
        signaled["tp_stop_pct"] = take_profit

    return PreparedSignals(
        data=signaled,
        close=close,
        long_entries=signaled["long_entry"].fillna(False).astype(bool),
        long_exits=signaled["long_exit"].fillna(False).astype(bool),
        short_entries=signaled["short_entry"].fillna(False).astype(bool),
        short_exits=signaled["short_exit"].fillna(False).astype(bool),
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
