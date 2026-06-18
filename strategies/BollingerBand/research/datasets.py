"""Dataset loading helpers for local OHLCV research files."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from market_data.ohlcv import load_ohlcv_csv


@dataclass(frozen=True)
class DatasetInfo:
    path: Path
    symbol: str
    rows: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    timeframe: str | None = None


def discover_ohlcv_csvs(root: str | Path = "datasets") -> list[Path]:
    """Find local market CSV files under a dataset root."""
    return sorted(Path(root).glob("**/*.csv"))


def load_market_csv(path: str | Path) -> pd.DataFrame:
    """Load known local market CSV formats into lowercase OHLCV columns.

    Supported shapes include:
    - MetaTrader-style CSVs with ``Date`` and optional ``Time`` columns.
    - Investing-style CSVs with ``Price`` as close and ``Vol.`` volume.
    - Semicolon-delimited XAUUSD files with combined ``Date`` timestamps.
    """
    return load_ohlcv_csv(path)


def describe_dataset(path: str | Path) -> DatasetInfo:
    """Return normalized metadata for a local market CSV."""
    data = load_market_csv(path)
    return DatasetInfo(
        path=Path(path),
        symbol=str(data.attrs.get("symbol", Path(path).stem)),
        rows=len(data),
        start=data.index.min() if len(data) else None,
        end=data.index.max() if len(data) else None,
        timeframe=data.attrs.get("timeframe"),
    )


def _normalize_column(column: object) -> str:
    return str(column).strip().strip('"').strip("'").lower()


def _parse_timestamp(data: pd.DataFrame) -> pd.Series:
    if "date" not in data.columns:
        raise ValueError("CSV must contain a Date/date column")
    date_values = data["date"].astype(str).str.strip()
    if "time" in data.columns:
        date_values = date_values + " " + data["time"].astype(str).str.strip()
    year_first = date_values.str.match(r"^\d{4}[./-]").fillna(False)
    parsed = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns]")
    if year_first.any():
        parsed.loc[year_first] = pd.to_datetime(date_values.loc[year_first], errors="coerce", yearfirst=True)
    if (~year_first).any():
        parsed.loc[~year_first] = pd.to_datetime(date_values.loc[~year_first], errors="coerce", dayfirst=True)
    return parsed


def _parse_number_series(values: pd.Series) -> pd.Series:
    normalized = values.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(normalized, errors="coerce")


def _parse_volume_series(values: pd.Series) -> pd.Series:
    normalized = values.astype(str).str.replace(",", "", regex=False).str.strip()
    multipliers = pd.Series(1.0, index=values.index)

    suffix = normalized.str.extract(r"([KkMmBb])$", expand=False)
    multipliers.loc[suffix.str.lower() == "k"] = 1_000.0
    multipliers.loc[suffix.str.lower() == "m"] = 1_000_000.0
    multipliers.loc[suffix.str.lower() == "b"] = 1_000_000_000.0

    numeric = normalized.str.replace(r"[KkMmBb]$", "", regex=True)
    return pd.to_numeric(numeric, errors="coerce").fillna(0.0) * multipliers


def _infer_symbol(path: Path, data: pd.DataFrame) -> str:
    if "ticker" in data.columns and data["ticker"].notna().any():
        return str(data["ticker"].dropna().iloc[0]).upper()
    parent = path.parent.name
    return parent.upper() if parent != "." else path.stem.upper()


def _infer_timeframe(path: Path) -> str | None:
    stem = path.stem.upper()
    for marker in ("PERIOD_", "XAU_"):
        if marker in stem:
            return stem.split(marker, maxsplit=1)[1].replace("_DATA", "")
    return None
