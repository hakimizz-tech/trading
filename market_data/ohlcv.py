"""Canonical OHLCV processing shared by research and live adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
OHLCV_RESAMPLE_RULES = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


@dataclass(frozen=True)
class OhlcvReport:
    """Data-quality report for one normalized OHLCV dataset."""

    source: str
    symbol: str | None
    timeframe: str | None
    rows: int
    start: str | None
    end: str | None
    missing_values: int
    duplicate_timestamps: int
    impossible_candles: int
    negative_prices: int
    negative_volume: int
    zero_volume_bars: int
    anomaly_spikes: int
    anomaly_any: int
    filled_bars: int
    completeness_pct: float
    price_only: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "rows": self.rows,
            "start": self.start,
            "end": self.end,
            "missing_values": self.missing_values,
            "duplicate_timestamps": self.duplicate_timestamps,
            "impossible_candles": self.impossible_candles,
            "negative_prices": self.negative_prices,
            "negative_volume": self.negative_volume,
            "zero_volume_bars": self.zero_volume_bars,
            "anomaly_spikes": self.anomaly_spikes,
            "anomaly_any": self.anomaly_any,
            "filled_bars": self.filled_bars,
            "completeness_pct": self.completeness_pct,
            "price_only": self.price_only,
        }


def load_ohlcv_csv(path: str | Path, *, symbol: str | None = None) -> pd.DataFrame:
    """Load known local CSV formats into canonical UTC OHLCV.

    Supported shapes include MT5 exports, Investing-style CSVs, semicolon XAU
    files, Yahoo-style stock OHLCV, and adjusted-close-only stock files.
    Price-only files are converted to flat OHLC candles with zero volume.
    """
    csv_path = Path(path)
    raw = pd.read_csv(csv_path, sep=_detect_separator(csv_path))
    if raw.empty:
        raise ValueError(f"{csv_path} is empty")

    normalized = raw.copy()
    normalized.columns = [_normalize_column(column) for column in normalized.columns]
    normalized = normalized.rename(columns=_rename_columns(normalized.columns))
    timestamp = _parse_timestamp(normalized, csv_path)
    normalized = normalized.assign(timestamp=timestamp)
    normalized = normalized.dropna(subset=["timestamp"]).set_index("timestamp")

    frame, price_only = _extract_ohlcv(normalized, csv_path)
    frame = to_ohlcv_frame(frame, source=str(csv_path), symbol=symbol or _infer_symbol(csv_path, normalized))
    frame.attrs["timeframe"] = _infer_timeframe(csv_path)
    frame.attrs["price_only"] = price_only
    return frame


def to_ohlcv_frame(
    data: Any,
    *,
    source: str | None = None,
    symbol: str | None = None,
    preserve_extra: bool = True,
) -> pd.DataFrame:
    """Convert a DataFrame-like object into canonical OHLCV format."""
    frame = pd.DataFrame(data).copy()
    frame.columns = [_normalize_column(column) for column in frame.columns]
    frame = frame.rename(columns=_rename_columns(frame.columns))
    if "time" in frame.columns and not isinstance(frame.index, pd.DatetimeIndex):
        parsed_time = _parse_time_column(frame["time"])
        if parsed_time.notna().any():
            frame = frame.assign(timestamp=parsed_time).set_index("timestamp")

    missing = [column for column in ("open", "high", "low", "close") if column not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV data missing required columns: {missing}")
    if "volume" not in frame.columns:
        frame["volume"] = 0.0

    keep = OHLCV_COLUMNS.copy()
    if preserve_extra:
        keep.extend(column for column in ("spread", "tick_volume", "real_volume") if column in frame.columns)
    frame = frame[keep].copy()
    for column in frame.columns:
        frame[column] = _parse_number_series(frame[column])
    frame = validate_ohlcv(frame)
    frame.attrs["source_path"] = source
    frame.attrs["symbol"] = symbol
    frame.attrs.setdefault("price_only", False)
    return frame


def process_ohlcv(
    data: pd.DataFrame,
    *,
    expected_freq: str | None = None,
    fill_gaps: bool = False,
    max_gap: int = 5,
    flag_quality: bool = True,
) -> pd.DataFrame:
    """Run the canonical OHLCV processing pipeline."""
    processed = validate_ohlcv(data)
    if fill_gaps and expected_freq:
        processed = handle_gaps(processed, freq=expected_freq, max_gap=max_gap)
    if flag_quality:
        processed = flag_anomalies(processed)
    return processed


def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Validate shape, numeric types, UTC timestamps, order, and duplicates."""
    if df.empty:
        raise ValueError("OHLCV data must not be empty")
    missing = set(OHLCV_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"OHLCV data missing required columns: {sorted(missing)}")

    result = df.copy()
    result.index = _coerce_datetime_index(result.index)
    result = result.sort_index()
    result = result[~result.index.duplicated(keep="last")]
    result.index.name = "timestamp"
    for column in OHLCV_COLUMNS:
        result[column] = _parse_number_series(result[column])
    return result


def ensure_utc(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy whose DatetimeIndex is UTC."""
    result = df.copy()
    result.index = _coerce_datetime_index(result.index)
    result.index.name = "timestamp"
    return result


def find_impossible_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows that violate OHLC constraints."""
    validated = validate_ohlcv(df)
    issues = pd.DataFrame(index=validated.index)
    issues["high_lt_low"] = validated["high"] < validated["low"]
    issues["high_lt_open"] = validated["high"] < validated["open"]
    issues["high_lt_close"] = validated["high"] < validated["close"]
    issues["low_gt_open"] = validated["low"] > validated["open"]
    issues["low_gt_close"] = validated["low"] > validated["close"]
    issues["negative_price"] = (validated[["open", "high", "low", "close"]] < 0).any(axis=1)
    issues["negative_volume"] = validated["volume"] < 0
    issues["any_issue"] = issues.any(axis=1)
    return issues[issues["any_issue"]]


def detect_gaps(df: pd.DataFrame, expected_freq: str) -> pd.DatetimeIndex:
    """Find missing timestamps for a declared frequency."""
    validated = validate_ohlcv(df)
    full_index = pd.date_range(validated.index.min(), validated.index.max(), freq=expected_freq, tz="UTC")
    return full_index.difference(validated.index)


def handle_gaps(
    df: pd.DataFrame,
    *,
    freq: str,
    method: str = "ffill",
    max_gap: int = 5,
) -> pd.DataFrame:
    """Fill short OHLCV gaps and mark filled rows with ``is_filled``."""
    validated = validate_ohlcv(df)
    full_index = pd.date_range(validated.index.min(), validated.index.max(), freq=freq, tz="UTC")
    result = validated.reindex(full_index)
    result.index.name = "timestamp"
    result["is_filled"] = result["close"].isna()
    if method == "ffill":
        result[["open", "high", "low", "close"]] = result[["open", "high", "low", "close"]].ffill(limit=max_gap)
        result["volume"] = result["volume"].fillna(0.0)
    elif method == "interpolate":
        result[["open", "high", "low", "close"]] = result[["open", "high", "low", "close"]].interpolate(
            method="time", limit=max_gap
        )
        result["volume"] = result["volume"].fillna(0.0)
    else:
        raise ValueError("method must be 'ffill' or 'interpolate'")
    return result


def detect_price_spikes(df: pd.DataFrame, *, window: int = 20, threshold: float = 3.0) -> pd.Series:
    """Flag bars where absolute return exceeds threshold times rolling volatility."""
    validated = validate_ohlcv(df)
    returns = validated["close"].pct_change(fill_method=None)
    rolling_std = returns.rolling(window, min_periods=max(5, window // 4)).std()
    return (returns.abs() > threshold * rolling_std).fillna(False)


def flag_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Add anomaly columns without dropping source rows."""
    result = validate_ohlcv(df)
    result["anomaly_spike"] = detect_price_spikes(result)
    result["anomaly_zero_vol"] = result["volume"] <= 0
    result["anomaly_impossible"] = False
    impossible = find_impossible_candles(result)
    if not impossible.empty:
        result.loc[impossible.index, "anomaly_impossible"] = True
    result["anomaly_any"] = result["anomaly_spike"] | result["anomaly_zero_vol"] | result["anomaly_impossible"]
    if "is_filled" not in result.columns:
        result["is_filled"] = False
    return result


def resample_ohlcv(df: pd.DataFrame, target_freq: str) -> pd.DataFrame:
    """Resample OHLCV to a coarser timeframe."""
    validated = validate_ohlcv(df)
    resampled = validated[OHLCV_COLUMNS].resample(target_freq).agg(OHLCV_RESAMPLE_RULES)
    return resampled.dropna(subset=["close"])


def normalize_prices(df: pd.DataFrame, *, method: str = "returns") -> pd.DataFrame:
    """Add normalized price features to an OHLCV frame."""
    result = validate_ohlcv(df)
    price_cols = ["open", "high", "low", "close"]
    if method == "returns":
        for column in price_cols:
            result[f"{column}_ret"] = result[column].pct_change(fill_method=None)
    elif method == "log_returns":
        for column in price_cols:
            result[f"{column}_logret"] = np.log(result[column] / result[column].shift(1))
    elif method == "minmax":
        for column in price_cols:
            min_value = result[column].min()
            max_value = result[column].max()
            result[f"{column}_norm"] = (result[column] - min_value) / (max_value - min_value)
    elif method == "zscore":
        for column in price_cols:
            result[f"{column}_z"] = (result[column] - result[column].mean()) / result[column].std()
    else:
        raise ValueError("method must be returns, log_returns, minmax, or zscore")
    return result


def quality_report(
    df: pd.DataFrame,
    *,
    source: str = "",
    symbol: str | None = None,
    timeframe: str | None = None,
    include_anomalies: bool = True,
) -> OhlcvReport:
    """Build a quality report for processed or raw canonical OHLCV."""
    original_dupes = int(pd.Index(df.index).duplicated().sum())
    validated = validate_ohlcv(df)
    missing_values = int(validated[["open", "high", "low", "close"]].isna().sum().sum())
    impossible = find_impossible_candles(validated)
    if include_anomalies:
        spike_count = int(detect_price_spikes(validated).sum())
    else:
        spike_count = 0
    zero_volume_count = int((validated["volume"] == 0).sum())
    anomaly_any = int(len(impossible) + spike_count + zero_volume_count)
    return OhlcvReport(
        source=source or str(validated.attrs.get("source_path") or ""),
        symbol=symbol or validated.attrs.get("symbol"),
        timeframe=timeframe or validated.attrs.get("timeframe"),
        rows=int(len(validated)),
        start=validated.index.min().isoformat() if len(validated) else None,
        end=validated.index.max().isoformat() if len(validated) else None,
        missing_values=missing_values,
        duplicate_timestamps=original_dupes,
        impossible_candles=int(len(impossible)),
        negative_prices=int((validated[["open", "high", "low", "close"]] < 0).any(axis=1).sum()),
        negative_volume=int((validated["volume"] < 0).sum()),
        zero_volume_bars=zero_volume_count,
        anomaly_spikes=spike_count,
        anomaly_any=anomaly_any,
        filled_bars=int(validated.get("is_filled", pd.Series(False, index=validated.index)).sum()),
        completeness_pct=round((1.0 - validated["close"].isna().mean()) * 100.0, 2),
        price_only=bool(validated.attrs.get("price_only", False)),
    )


def _extract_ohlcv(data: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, bool]:
    columns = set(data.columns)
    price_col = _find_price_column(data)
    result = pd.DataFrame(index=data.index)
    price_only = False
    if {"open", "high", "low"}.issubset(columns) and ("close" in columns or price_col):
        result["open"] = _parse_number_series(data["open"])
        result["high"] = _parse_number_series(data["high"])
        result["low"] = _parse_number_series(data["low"])
        result["close"] = _parse_number_series(data["close"] if "close" in columns else data[price_col])
    elif price_col:
        price = _parse_number_series(data[price_col])
        result["open"] = price
        result["high"] = price
        result["low"] = price
        result["close"] = price
        price_only = True
    else:
        raise ValueError(f"{path} must include OHLC columns or a single price/adjusted-close column")

    if "volume" in data.columns:
        result["volume"] = _parse_volume_series(data["volume"])
    else:
        result["volume"] = 0.0
    if not price_only:
        flat_ohlc = result[["open", "high", "low", "close"]].nunique(axis=1).eq(1).all()
        zero_volume = result["volume"].fillna(0.0).eq(0.0).all()
        price_only = bool(flat_ohlc and zero_volume)
    if "spread" in data.columns:
        result["spread"] = _parse_number_series(data["spread"])
    return result, price_only


def _parse_timestamp(data: pd.DataFrame, path: Path) -> pd.Series:
    date_col = _first_existing(data, ("timestamp", "datetime", "date", "trade_date", "time"))
    if date_col is None:
        raise ValueError(f"{path} must include a timestamp/date column")
    values = data[date_col].astype(str).str.strip()
    if date_col != "time" and "time" in data.columns:
        values = values + " " + data["time"].astype(str).str.strip()
    year_first = values.str.match(r"^\d{4}[./-]").fillna(False)
    parsed = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns, UTC]")
    if year_first.any():
        parsed.loc[year_first] = pd.to_datetime(values.loc[year_first], errors="coerce", yearfirst=True, utc=True)
    if (~year_first).any():
        parsed.loc[~year_first] = pd.to_datetime(values.loc[~year_first], errors="coerce", dayfirst=True, utc=True)
    return parsed


def _parse_time_column(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().any() and numeric.dropna().median() > 10_000_000:
        return pd.to_datetime(numeric, unit="s", errors="coerce", utc=True)
    return pd.to_datetime(values, errors="coerce", utc=True)


def _coerce_datetime_index(index: pd.Index) -> pd.DatetimeIndex:
    dt_index = pd.DatetimeIndex(pd.to_datetime(index, errors="coerce", utc=True))
    if dt_index.isna().any():
        raise ValueError("OHLCV index contains invalid timestamps")
    return dt_index


def _normalize_column(column: object) -> str:
    return str(column).strip().strip('"').strip("'").lower().replace("_", " ")


def _rename_columns(columns: pd.Index | list[str]) -> dict[str, str]:
    aliases = {
        "adj close": "adj close",
        "adjusted close": "adj close",
        "trade date": "trade_date",
        "trade_date": "trade_date",
        "vol.": "volume",
        "vol": "volume",
        "tick volume": "volume",
        "tick_volume": "volume",
        "real volume": "volume",
        "real_volume": "volume",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
        "price": "close",
    }
    return {column: aliases.get(str(column), str(column)) for column in columns}


def _find_price_column(data: pd.DataFrame) -> str | None:
    for column in ("adj close", "close", "price"):
        if column in data.columns:
            return column
    excluded = {"date", "time", "timestamp", "datetime", "trade_date", "ticker", "change %"}
    candidates = [column for column in data.columns if column not in excluded]
    return candidates[0] if len(candidates) == 1 else None


def _first_existing(data: pd.DataFrame, columns: tuple[str, ...]) -> str | None:
    for column in columns:
        if column in data.columns:
            return column
    return None


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
    if "PERIOD_" in stem:
        return stem.split("PERIOD_", maxsplit=1)[1]
    if stem.startswith("XAU_"):
        return stem.removeprefix("XAU_").replace("_DATA", "")
    return None


def _detect_separator(path: Path) -> str:
    header = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    return ";" if header.count(";") > header.count(",") else ","
