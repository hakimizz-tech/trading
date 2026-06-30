"""Runtime validation for normalized backtesting signals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from backtesting.signals import PreparedSignals


_SUSPICIOUS_COLUMN = re.compile(
    r"(^|_)(future|forward|fwd|lead|target|label|next[_-]?return)(_|$)",
    flags=re.IGNORECASE,
)


class SignalValidationError(ValueError):
    """Raised when prepared signals cannot be simulated safely."""

    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__("Invalid prepared signals: " + "; ".join(errors))


@dataclass(frozen=True)
class SignalValidationReport:
    """Structural validation outcome for one prepared signal set."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if self.errors:
            raise SignalValidationError(self.errors)


def validate_prepared_signals(
    signals: PreparedSignals,
    *,
    raise_on_error: bool = True,
    check_lookahead_names: bool = True,
    require_provenance: bool = False,
) -> SignalValidationReport:
    """Validate a ``PreparedSignals`` object without mutating it."""
    errors: list[str] = []
    warnings: list[str] = []
    data = signals.data

    if not isinstance(data, pd.DataFrame):
        errors.append("data must be a pandas DataFrame")
        index = pd.Index([])
    else:
        index = data.index
        if data.empty:
            errors.append("data must not be empty")
        if not index.is_unique:
            errors.append("data index must be unique")
        if not index.is_monotonic_increasing:
            errors.append("data index must be chronological")

    series_fields = {
        "close": signals.close,
        "long_entries": signals.long_entries,
        "long_exits": signals.long_exits,
        "short_entries": signals.short_entries,
        "short_exits": signals.short_exits,
        "stop_loss": signals.stop_loss,
        "take_profit": signals.take_profit,
    }
    for name, series in series_fields.items():
        if series is None:
            continue
        if not isinstance(series, pd.Series):
            errors.append(f"{name} must be a pandas Series")
            continue
        if len(series) != len(data):
            errors.append(f"{name} length must match data")
        if not series.index.equals(index):
            errors.append(f"{name} index must exactly match data index")

    if isinstance(signals.close, pd.Series):
        close = pd.to_numeric(signals.close, errors="coerce")
        if close.isna().any() or not np.isfinite(close.to_numpy(dtype=float)).all():
            errors.append("close must contain only finite numeric values")
        elif (close <= 0).any():
            errors.append("close prices must be positive")

    for name in ("long_entries", "long_exits", "short_entries", "short_exits"):
        series = getattr(signals, name)
        if isinstance(series, pd.Series):
            if not isinstance(series.dtype, pd.BooleanDtype) and series.dtype != bool:
                errors.append(f"{name} must have boolean dtype")
            if series.isna().any():
                errors.append(f"{name} must not contain missing values")

    for name in ("stop_loss", "take_profit"):
        series = getattr(signals, name)
        if isinstance(series, pd.Series):
            numeric = pd.to_numeric(series, errors="coerce")
            populated = numeric.dropna()
            if not np.isfinite(populated.to_numpy(dtype=float)).all():
                errors.append(f"{name} must contain only finite values or missing values")
            elif (populated < 0).any():
                errors.append(f"{name} must not contain negative distances")

    _check_conflicts(signals, errors)
    _check_provenance(signals, data, errors, warnings, require_provenance=require_provenance)

    if check_lookahead_names and isinstance(data, pd.DataFrame):
        suspicious = sorted(str(column) for column in data.columns if _SUSPICIOUS_COLUMN.search(str(column)))
        if suspicious:
            warnings.append(
                "possible look-ahead columns detected; confirm they are not used to generate current-bar signals: "
                + ", ".join(suspicious)
            )

    report = SignalValidationReport(errors=tuple(errors), warnings=tuple(warnings))
    if raise_on_error:
        report.require_valid()
    return report


def _check_provenance(
    signals: PreparedSignals,
    data: pd.DataFrame,
    errors: list[str],
    warnings: list[str],
    *,
    require_provenance: bool,
) -> None:
    feature_columns = tuple(str(column) for column in signals.feature_columns)
    label_columns = tuple(str(column) for column in signals.label_columns)
    signal_columns = tuple(str(column) for column in signals.signal_columns)

    if require_provenance and not feature_columns and not signal_columns:
        errors.append("signal provenance is required but feature_columns and signal_columns are empty")

    available = {str(column) for column in data.columns} if isinstance(data, pd.DataFrame) else set()
    for group_name, columns in (
        ("feature_columns", feature_columns),
        ("label_columns", label_columns),
        ("signal_columns", signal_columns),
    ):
        missing = sorted(column for column in columns if column not in available)
        if missing:
            errors.append(f"{group_name} reference columns missing from data: {', '.join(missing)}")

    label_set = set(label_columns)
    feature_set = set(feature_columns)
    signal_set = set(signal_columns)
    if label_set & feature_set:
        errors.append("label_columns must not overlap feature_columns")
    if label_set & signal_set:
        errors.append("label_columns must not overlap signal_columns")

    lag = signals.minimum_feature_lag
    if lag is not None and lag < 0:
        errors.append("minimum_feature_lag must not be negative")
    if require_provenance and (lag is None or lag < 1):
        errors.append("minimum_feature_lag must be at least 1 when provenance is required")
    elif lag is None and (feature_columns or signal_columns):
        warnings.append(
            "minimum_feature_lag was not provided; semantic look-ahead risk requires strategy review"
        )


def _check_conflicts(signals: PreparedSignals, errors: list[str]) -> None:
    pairs = (
        ("long_entries", "long_exits"),
        ("short_entries", "short_exits"),
        ("long_entries", "short_entries"),
    )
    for left_name, right_name in pairs:
        left = getattr(signals, left_name)
        right = getattr(signals, right_name)
        if not isinstance(left, pd.Series) or not isinstance(right, pd.Series):
            continue
        if left.index.equals(right.index) and (left.fillna(False).astype(bool) & right.fillna(False).astype(bool)).any():
            errors.append(f"{left_name} and {right_name} conflict on at least one bar")
