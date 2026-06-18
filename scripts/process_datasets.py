#!/usr/bin/env python3
"""Normalize local datasets and write OHLCV quality reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_data.ohlcv import load_ohlcv_csv, process_ohlcv, quality_report


def main() -> None:
    args = _parse_args()
    csvs = sorted(args.input_dir.glob(args.include))
    for pattern in args.exclude:
        excluded = set(args.input_dir.glob(pattern))
        csvs = [path for path in csvs if path not in excluded]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    reports: list[dict[str, object]] = []
    summary_path = args.report_dir / "ohlcv_dataset_quality.csv"
    json_path = args.report_dir / "ohlcv_dataset_quality.json"
    for index, csv_path in enumerate(csvs, start=1):
        rel = csv_path.relative_to(args.input_dir)
        output_path = args.output_dir / rel.with_suffix(".csv")
        print(f"[{index}/{len(csvs)}] {csv_path}", flush=True)
        try:
            if args.skip_existing and output_path.exists():
                existing = load_ohlcv_csv(output_path)
                report = quality_report(
                    existing,
                    source=str(csv_path),
                    symbol=existing.attrs.get("symbol"),
                    timeframe=existing.attrs.get("timeframe"),
                    include_anomalies=args.deep_quality,
                ).as_dict()
                report["processed_path"] = str(output_path)
                report["status"] = "existing"
                reports.append(report)
                _write_reports(reports, summary_path, json_path)
                continue
            normalized = load_ohlcv_csv(csv_path)
            processed = process_ohlcv(normalized, flag_quality=args.with_flags)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            processed.to_csv(output_path)
            report = quality_report(
                processed,
                source=str(csv_path),
                symbol=processed.attrs.get("symbol"),
                timeframe=processed.attrs.get("timeframe"),
                include_anomalies=args.deep_quality,
            ).as_dict()
            report["processed_path"] = str(output_path)
            report["status"] = "processed"
            reports.append(report)
        except Exception as exc:  # noqa: BLE001 - CLI should report all files, not stop at first bad CSV.
            reports.append(
                {
                    "source": str(csv_path),
                    "status": "error",
                    "error": str(exc),
                }
            )
        _write_reports(reports, summary_path, json_path)

    report_frame = _write_reports(reports, summary_path, json_path)
    print(f"Processed {int((report_frame['status'] == 'processed').sum()) if not report_frame.empty else 0}/{len(csvs)} CSV files")
    print(f"Wrote normalized data to {args.output_dir}")
    print(f"Wrote quality summary to {summary_path}")
    print(f"Wrote quality JSON to {json_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process local CSV datasets into canonical OHLCV.")
    parser.add_argument("--input-dir", type=Path, default=Path("datasets"))
    parser.add_argument("--include", default="**/*.csv", help="Glob under input-dir to include.")
    parser.add_argument("--exclude", action="append", default=[], help="Glob under input-dir to exclude; repeatable.")
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/processed_datasets"))
    parser.add_argument("--report-dir", type=Path, default=Path("trade_results/data_quality"))
    parser.add_argument("--with-flags", action="store_true", help="Include anomaly/is_filled columns in processed CSVs.")
    parser.add_argument("--deep-quality", action="store_true", help="Run slower rolling spike/anomaly quality scans.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip normalized files that already exist.")
    return parser.parse_args()


def _write_reports(reports: list[dict[str, object]], summary_path: Path, json_path: Path) -> pd.DataFrame:
    report_frame = pd.DataFrame(reports)
    report_frame.to_csv(summary_path, index=False)
    json_path.write_text(json.dumps(reports, indent=2, sort_keys=True), encoding="utf-8")
    return report_frame


if __name__ == "__main__":
    main()
