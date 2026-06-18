#!/usr/bin/env python3
"""Download Yahoo Finance history into strategy-ready OHLCV datasets.

The script saves both raw Yahoo output and normalized OHLCV files. It is built
for RisingAssest by default, but accepts any stock/ETF ticker list.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_data.ohlcv import load_ohlcv_csv, process_ohlcv, quality_report, to_ohlcv_frame
from strategies.RisingAssest.core import RISING_ASSETS_UNIVERSE


def main() -> int:
    args = _parse_args()
    tickers = _resolve_tickers(args)
    yf = _import_yfinance()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    raw = yf.download(
        tickers=tickers,
        start=args.start,
        end=args.end,
        period=args.period,
        interval=args.interval,
        auto_adjust=args.auto_adjust,
        actions=args.actions,
        repair=args.repair,
        threads=args.threads,
        group_by="column",
        multi_level_index=True,
        progress=args.progress,
    )
    if raw is None or raw.empty:
        raise RuntimeError("No yfinance data returned. Check tickers, date range, interval, or network access.")

    manifest: dict[str, Any] = {
        "collector": "yfinance",
        "data_date": datetime.now(tz=UTC).date().isoformat(),
        "source": "Yahoo Finance via yfinance",
        "ticker_source": args.ticker_source,
        "parameters": {
            "tickers": tickers,
            "start": args.start,
            "end": args.end,
            "period": args.period,
            "interval": args.interval,
            "auto_adjust": args.auto_adjust,
            "actions": args.actions,
            "repair": args.repair,
        },
        "outputs": {},
        "metadata": {
            "_source_note": "Yahoo Finance data can be delayed, revised, incomplete, or unavailable for some exchanges.",
            "_adjustment_note": "auto_adjust=True writes adjusted OHLC suitable for total-return research; raw data is also saved for audit.",
            "_missing_policy": "Missing fields are recorded as null or error strings; no fallback values are substituted.",
        },
    }

    for ticker in tickers:
        try:
            ticker_raw = _extract_ticker_history(raw, ticker, multi_ticker=len(tickers) > 1)
            if ticker_raw.empty:
                raise RuntimeError("ticker returned no rows")
            raw_path = _write_raw_history(ticker_raw, ticker=ticker, args=args)
            ohlcv = _normalize_yfinance_history(ticker_raw, ticker=ticker)
            processed = process_ohlcv(
                ohlcv,
                expected_freq=args.expected_freq,
                fill_gaps=args.fill_gaps,
                flag_quality=args.with_flags,
            )
            output_path = _write_normalized_history(processed, ticker=ticker, args=args)
            report = quality_report(
                processed,
                source=str(output_path),
                symbol=ticker,
                timeframe=args.interval,
                include_anomalies=args.deep_quality,
            ).as_dict()
            manifest["outputs"][ticker] = {
                "status": "ok",
                "raw_path": str(raw_path),
                "normalized_path": str(output_path),
                "quality": report,
                "_source": "yfinance.download",
            }
        except Exception as exc:  # noqa: BLE001 - collect every ticker result.
            manifest["outputs"][ticker] = {
                "status": "error",
                "raw_path": None,
                "normalized_path": None,
                "quality": None,
                "error": str(exc),
                "_source": "missing",
            }

    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    ok_count = sum(1 for item in manifest["outputs"].values() if item["status"] == "ok")
    print(f"Downloaded and normalized {ok_count}/{len(tickers)} tickers")
    print(f"Wrote normalized datasets under {args.output_dir}")
    print(f"Wrote raw Yahoo data under {args.raw_dir}")
    print(f"Wrote manifest to {args.manifest}")
    return 0 if ok_count == len(tickers) else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download yfinance stock/ETF history into datasets/.")
    parser.add_argument("--tickers", nargs="+", default=None, help="Ticker list, e.g. SPY QQQ GLD TLT")
    parser.add_argument("--tickers-file", type=Path, default=None, help="Text/CSV file containing ticker symbols")
    parser.add_argument("--rising-assets-universe", action="store_true", help="Use the RisingAssest default ETF universe")
    parser.add_argument("--start", default="2000-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--period", default=None, help="Alternative to start/end, e.g. 10y or max")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--auto-adjust", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--actions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--repair", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--threads", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--progress", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--output-dir", type=Path, default=Path("datasets"))
    parser.add_argument("--raw-dir", type=Path, default=Path("datasets/_raw_yfinance"))
    parser.add_argument("--manifest", type=Path, default=Path("datasets/yfinance_manifest.json"))
    parser.add_argument("--expected-freq", default=None, help="Optional pandas frequency for gap filling, e.g. 1D")
    parser.add_argument("--fill-gaps", action="store_true")
    parser.add_argument("--with-flags", action="store_true", help="Include anomaly/is_filled columns in normalized CSVs")
    parser.add_argument("--deep-quality", action="store_true", help="Run slower rolling spike scans in quality reports")
    args = parser.parse_args()
    if args.period and (args.start or args.end):
        args.start = None
        args.end = None
    return args


def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    tickers: list[str] = []
    source = "custom"
    if args.rising_assets_universe:
        tickers.extend(RISING_ASSETS_UNIVERSE)
        source = "RisingAssest.RISING_ASSETS_UNIVERSE"
    if args.tickers_file:
        tickers.extend(_read_tickers_file(args.tickers_file))
        source = str(args.tickers_file)
    if args.tickers:
        tickers.extend(args.tickers)
        source = "cli"
    normalized = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))
    if not normalized:
        normalized = list(RISING_ASSETS_UNIVERSE)
        source = "RisingAssest.RISING_ASSETS_UNIVERSE"
    args.ticker_source = source
    return normalized


def _read_tickers_file(path: Path) -> list[str]:
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        values.extend(part.strip() for part in clean.split(",") if part.strip())
    return values


def _import_yfinance():
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on optional market-data extras.
        raise RuntimeError(
            "yfinance is not installed. Install market-data dependencies with "
            "`python -m pip install -r requirements-market-data.txt`."
        ) from exc
    return yf


def _extract_ticker_history(raw: pd.DataFrame, ticker: str, *, multi_ticker: bool) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        if ticker in raw.columns.get_level_values(-1):
            return raw.xs(ticker, axis=1, level=-1, drop_level=True).dropna(how="all")
        if ticker in raw.columns.get_level_values(0):
            return raw.xs(ticker, axis=1, level=0, drop_level=True).dropna(how="all")
        raise KeyError(f"{ticker} not present in yfinance response")
    if multi_ticker:
        raise KeyError(f"{ticker} not present in flattened yfinance response")
    return raw.dropna(how="all")


def _write_raw_history(data: pd.DataFrame, *, ticker: str, args: argparse.Namespace) -> Path:
    output = args.raw_dir / ticker / f"{ticker}_{args.interval}_raw_yfinance.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = data.copy()
    raw.index.name = "timestamp"
    raw.to_csv(output)
    return output


def _normalize_yfinance_history(data: pd.DataFrame, *, ticker: str) -> pd.DataFrame:
    renamed = data.copy()
    renamed.columns = [str(column).strip() for column in renamed.columns]
    if "Adj Close" in renamed.columns and "Close" not in renamed.columns:
        renamed["Close"] = renamed["Adj Close"]
    ohlcv = to_ohlcv_frame(renamed, source=f"yfinance:{ticker}", symbol=ticker)
    ohlcv.attrs["timeframe"] = None
    return ohlcv


def _write_normalized_history(data: pd.DataFrame, *, ticker: str, args: argparse.Namespace) -> Path:
    output = args.output_dir / ticker / f"{ticker}_{args.interval}_yfinance.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output)
    return output


if __name__ == "__main__":
    raise SystemExit(main())
