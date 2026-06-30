"""Shared signal preparation for backtesting engines."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from backtesting import PreparedSignals
from strategies.BollingerBand.core import (
    AdaptiveRegimeConfig,
    ExitPlan,
    add_atr,
    calculate_bollinger_bands,
    generate_adaptive_bollinger_signals,
    generate_bb_rsi_signals,
    generate_bbma_signals,
    generate_mean_reversion_signals,
)


def prepare_bollinger_signals(
    data: pd.DataFrame,
    *,
    strategy: str = "adaptive",
    adaptive_config: AdaptiveRegimeConfig | None = None,
    exit_plan: ExitPlan | None = None,
    price_col: str = "close",
) -> PreparedSignals:
    """Prepare Bollinger strategy signals for vectorized/event engines."""
    adaptive_strategies = {
        "adaptive": "hybrid",
        "adaptive_mean_reversion": "mean_reversion",
        "adaptive_breakout": "breakout",
    }
    if strategy in adaptive_strategies:
        config = adaptive_config or AdaptiveRegimeConfig()
        if strategy != "adaptive":
            config = replace(config, regime_mode=adaptive_strategies[strategy])
        signaled = generate_adaptive_bollinger_signals(data, config=config, price_col=price_col)
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
            raise ValueError(
                "strategy must be one of: adaptive, adaptive_mean_reversion, "
                "adaptive_breakout, mean_reversion, bbma, bb_rsi"
            )

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

    long_entries = signaled["long_entry"].fillna(False).astype(bool)
    short_entries = signaled["short_entry"].fillna(False).astype(bool)
    long_exits = signaled["long_exit"].fillna(False).astype(bool) & ~long_entries
    short_exits = signaled["short_exit"].fillna(False).astype(bool) & ~short_entries

    return PreparedSignals(
        data=signaled,
        close=close,
        long_entries=long_entries,
        long_exits=long_exits,
        short_entries=short_entries,
        short_exits=short_exits,
        stop_loss=stop_loss,
        take_profit=take_profit,
        signal_columns=("long_entry", "long_exit", "short_entry", "short_exit"),
        minimum_feature_lag=1,
    )
