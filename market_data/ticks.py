"""Canonical tick processing shared by live adapters and execution gates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

TICK_COLUMNS = ["bid", "ask", "last", "volume"]
TICK_EXTRA_COLUMNS = ["flags", "volume_real", "time_msc", "index", "mid", "spread"]


def to_tick_frame(
    data: Any,
    *,
    source: str | None = None,
    symbol: str | None = None,
    preserve_extra: bool = True,
) -> pd.DataFrame:
    """Convert DataFrame-like, MT5 tick rates, or aiomql Ticks into canonical ticks."""
    frame = _coerce_tick_input(data)
    if frame.empty:
        raise ValueError("Tick data must not be empty")
    frame.columns = [_normalize_column(column) for column in frame.columns]
    frame = frame.rename(columns=_rename_columns(frame.columns))
    frame = _apply_tick_time_index(frame)

    missing = [column for column in ("bid", "ask") if column not in frame.columns]
    if missing:
        raise ValueError(f"Tick data missing required columns: {missing}")
    if "last" not in frame.columns:
        frame["last"] = 0.0
    if "volume" not in frame.columns:
        frame["volume"] = 0.0

    keep = TICK_COLUMNS.copy()
    if preserve_extra:
        keep.extend(column for column in TICK_EXTRA_COLUMNS if column in frame.columns)
    frame = frame[keep].copy()
    for column in frame.columns:
        frame[column] = _parse_number_series(frame[column])
    frame = validate_tick_frame(frame)
    if "mid" not in frame.columns:
        frame["mid"] = (frame["bid"] + frame["ask"]) / 2.0
    if "spread" not in frame.columns:
        frame["spread"] = frame["ask"] - frame["bid"]
    frame.attrs["source_path"] = source
    frame.attrs["symbol"] = symbol
    return frame


def validate_tick_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Validate tick shape, numeric types, UTC timestamps, ordering, and duplicates."""
    if df.empty:
        raise ValueError("Tick data must not be empty")
    missing = set(("bid", "ask")) - set(df.columns)
    if missing:
        raise ValueError(f"Tick data missing required columns: {sorted(missing)}")
    result = df.copy()
    result.index = _coerce_datetime_index(result.index)
    result = result.sort_index()
    result = result[~result.index.duplicated(keep="last")]
    result.index.name = "timestamp"
    for column in result.columns:
        result[column] = _parse_number_series(result[column])
    return result


def latest_tick(data: Any, *, symbol: str | None = None) -> dict[str, Any]:
    """Return the latest normalized tick as a plain dictionary."""
    frame = to_tick_frame(data, symbol=symbol)
    row = frame.iloc[-1].to_dict()
    row["timestamp"] = frame.index[-1].isoformat()
    if symbol is not None:
        row["symbol"] = symbol
    return row


def _coerce_tick_input(data: Any) -> pd.DataFrame:
    ticks_data = getattr(data, "data", None)
    if ticks_data is not None:
        return pd.DataFrame(ticks_data).copy()
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if isinstance(data, Mapping):
        return pd.DataFrame(data).copy()
    if isinstance(data, Iterable) and not isinstance(data, (str, bytes)):
        items = list(data)
        if items and _looks_like_tick(items[0]):
            return pd.DataFrame([_tick_to_mapping(item) for item in items]).copy()
        return pd.DataFrame(items).copy()
    return pd.DataFrame(data).copy()


def _looks_like_tick(value: Any) -> bool:
    if isinstance(value, Mapping):
        return False
    tick_attrs = ("time", "bid", "ask")
    return all(hasattr(value, attr) for attr in tick_attrs) or hasattr(value, "dict")


def _tick_to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dict_attr = getattr(value, "dict", None)
    if callable(dict_attr):
        mapped = dict_attr()
        if isinstance(mapped, Mapping):
            return dict(mapped)
    if isinstance(dict_attr, Mapping):
        return dict(dict_attr)
    asdict = getattr(value, "_asdict", None)
    if callable(asdict):
        mapped = asdict()
        if isinstance(mapped, Mapping):
            return dict(mapped)
    fields = ("time", "bid", "ask", "last", "volume", "flags", "volume_real", "time_msc", "Index")
    return {field: getattr(value, field) for field in fields if hasattr(value, field)}


def _apply_tick_time_index(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.index, pd.DatetimeIndex):
        return frame
    time_column = "time_msc" if "time_msc" in frame.columns else "time"
    if time_column not in frame.columns:
        return frame
    parsed_time = _parse_time_column(frame[time_column], milliseconds=time_column == "time_msc")
    if parsed_time.notna().any():
        return frame.assign(timestamp=parsed_time).set_index("timestamp")
    return frame


def _parse_time_column(values: pd.Series, *, milliseconds: bool = False) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().any():
        unit = "ms" if milliseconds or numeric.dropna().median() > 10_000_000_000 else "s"
        return pd.to_datetime(numeric, unit=unit, errors="coerce", utc=True)
    return pd.to_datetime(values, errors="coerce", utc=True)


def _coerce_datetime_index(index: pd.Index) -> pd.DatetimeIndex:
    dt_index = pd.DatetimeIndex(pd.to_datetime(index, errors="coerce", utc=True))
    if dt_index.hasnans:
        raise ValueError("Tick index contains invalid timestamps")
    return dt_index


def _normalize_column(column: object) -> str:
    return str(column).strip().strip('"').strip("'").lower().replace("_", " ")


def _rename_columns(columns: pd.Index | list[str]) -> dict[str, str]:
    aliases = {
        "time msc": "time_msc",
        "volume real": "volume_real",
        "index": "index",
        "bid": "bid",
        "ask": "ask",
        "last": "last",
        "volume": "volume",
        "flags": "flags",
    }
    return {column: aliases.get(str(column), str(column)) for column in columns}


def _parse_number_series(values: pd.Series) -> pd.Series:
    normalized = values.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(normalized, errors="coerce")
