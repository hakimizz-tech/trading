"""Macro feature loading for the Directional Forex ML paper workflow."""

from __future__ import annotations

from pathlib import Path
from typing import IO

import pandas as pd


def load_treasury_macro_csv(
    path: str | Path | IO[str],
    *,
    date_column: str = "date",
    rate_5y_column: str = "rate_5y",
    rate_13w_column: str = "rate_13w",
) -> pd.DataFrame:
    """Load 5-year and 13-week Treasury data into the paper macro schema."""
    raw = pd.read_csv(path)
    if date_column not in raw.columns:
        raise ValueError(f"macro CSV must include {date_column!r}")
    if rate_5y_column not in raw.columns or rate_13w_column not in raw.columns:
        raise ValueError("macro CSV must include 5-year and 13-week Treasury rate columns")
    index = pd.to_datetime(raw[date_column], utc=True)
    macro = pd.DataFrame(index=index)
    macro["rate_5y"] = pd.to_numeric(raw[rate_5y_column], errors="coerce").to_numpy()
    macro["rate_13w"] = pd.to_numeric(raw[rate_13w_column], errors="coerce").to_numpy()
    macro = macro.sort_index()
    macro["yield_slope"] = macro["rate_5y"] - macro["rate_13w"]
    macro["rate_5y_change"] = macro["rate_5y"].diff()
    macro["rate_13w_change"] = macro["rate_13w"].diff()
    macro["yield_slope_change"] = macro["yield_slope"].diff()
    return macro
