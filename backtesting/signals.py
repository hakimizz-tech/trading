"""Shared signal interfaces for vectorized and event-driven backtests."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PreparedSignals:
    """Normalized strategy signals consumed by backtesting engines.

    Strategy packages should build this object from their own indicator logic so
    vectorbt/backtrader adapters can share a stable contract.
    """

    data: pd.DataFrame
    close: pd.Series
    long_entries: pd.Series
    long_exits: pd.Series
    short_entries: pd.Series
    short_exits: pd.Series
    stop_loss: pd.Series | None = None
    take_profit: pd.Series | None = None
