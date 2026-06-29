"""Shared signal interfaces for vectorized and event-driven backtests."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backtesting.validation import SignalValidationReport, validate_prepared_signals


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

    def validate(
        self,
        *,
        raise_on_error: bool = True,
        check_lookahead_names: bool = True,
    ) -> SignalValidationReport:
        """Validate alignment, values, signal types, stops, and obvious leakage."""
        return validate_prepared_signals(
            self,
            raise_on_error=raise_on_error,
            check_lookahead_names=check_lookahead_names,
        )
