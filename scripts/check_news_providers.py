#!/usr/bin/env python3
"""Smoke-test non-OKX news providers for live news availability.

This script intentionally does not include OKX because that provider needs a
configured OKX CLI/profile. It checks the public/optional providers and prints
row counts plus sample headlines so you can see which feeds are returning data.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from News.providers.forex_factory import fetch_forex_factory_weekly_export
from News.providers.google_news import fetch_google_news_rss
from News.providers.official_macro import DEFAULT_OFFICIAL_MACRO_FEEDS, fetch_official_macro_feed
from News.providers.yfinance_news import fetch_yfinance_news


ProviderRunner = Callable[[argparse.Namespace], pd.DataFrame]


@dataclass(frozen=True)
class ProviderCheckResult:
    provider: str
    status: str
    rows: int
    sample_titles: list[str]
    error: str | None = None


def main() -> int:
    args = parse_args()
    providers = resolve_provider_names(args)
    runners = selected_runners(providers)
    results = [run_provider_check(name, runner, args) for name, runner in runners.items()]
    print_summary(results, sample_size=args.sample_size)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps([asdict(result) for result in results], indent=2), encoding="utf-8")
        print(f"\nWrote provider check results to {args.output}")

    if args.fail_on_empty:
        return 1 if any(result.status != "ok" or result.rows == 0 for result in results) else 0
    return 1 if any(result.status == "error" for result in results) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether non-OKX News providers return live rows.")
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=("yfinance", "google_news", "official_macro", "forex_factory", "all"),
        default=("yfinance", "google_news", "official_macro"),
        help="Providers to check. Defaults to yfinance, google_news, and official_macro.",
    )
    parser.add_argument("--tickers", nargs="+", default=("SPY", "QQQ", "AAPL"), help="Tickers for yfinance news.")
    parser.add_argument("--yfinance-limit", type=int, default=10, help="Max yfinance news items per ticker.")
    parser.add_argument("--google-query", default="Federal Reserve OR FOMC OR inflation OR stocks", help="Google News RSS search query.")
    parser.add_argument("--google-symbol", default="USD", help="Symbol assigned to Google News RSS rows.")
    parser.add_argument("--timeout-seconds", type=int, default=10, help="Network timeout for RSS/provider requests.")
    parser.add_argument("--include-forex-factory", action="store_true", help="Include ForexFactory even when --providers all is not used.")
    parser.add_argument("--sample-size", type=int, default=3, help="Number of sample titles to print per provider.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--fail-on-empty", action="store_true", help="Exit 1 when any selected provider returns zero rows.")
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.yfinance_limit <= 0:
        parser.error("--yfinance-limit must be positive")
    if args.sample_size < 0:
        parser.error("--sample-size must be non-negative")
    return args


def resolve_provider_names(args: argparse.Namespace) -> tuple[str, ...]:
    if "all" in args.providers:
        return ("yfinance", "google_news", "official_macro", "forex_factory")
    providers = list(args.providers)
    if args.include_forex_factory and "forex_factory" not in providers:
        providers.append("forex_factory")
    return tuple(providers)


def selected_runners(providers: list[str] | tuple[str, ...]) -> dict[str, ProviderRunner]:
    all_runners: dict[str, ProviderRunner] = {
        "yfinance": run_yfinance,
        "google_news": run_google_news,
        "official_macro": run_official_macro,
        "forex_factory": run_forex_factory,
    }
    if "all" in providers:
        return all_runners
    return {name: all_runners[name] for name in providers}


def run_provider_check(name: str, runner: ProviderRunner, args: argparse.Namespace) -> ProviderCheckResult:
    try:
        frame = runner(args)
    except Exception as exc:  # noqa: BLE001 - this is a smoke-test runner.
        return ProviderCheckResult(provider=name, status="error", rows=0, sample_titles=[], error=str(exc))
    sample_titles = sample_frame_titles(frame, limit=args.sample_size)
    provider_errors = frame.attrs.get("provider_errors", [])
    if provider_errors and len(frame) > 0:
        return ProviderCheckResult(provider=name, status="partial", rows=len(frame), sample_titles=sample_titles, error="; ".join(provider_errors))
    status = "ok" if len(frame) > 0 else "empty"
    error = "; ".join(provider_errors) if provider_errors else None
    return ProviderCheckResult(provider=name, status=status, rows=len(frame), sample_titles=sample_titles, error=error)


def run_yfinance(args: argparse.Namespace) -> pd.DataFrame:
    return fetch_yfinance_news(args.tickers, limit=args.yfinance_limit)


def run_google_news(args: argparse.Namespace) -> pd.DataFrame:
    return fetch_google_news_rss(
        args.google_query,
        symbol=args.google_symbol,
        asset_class="macro",
        timeout_seconds=args.timeout_seconds,
    )


def run_official_macro(args: argparse.Namespace) -> pd.DataFrame:
    frames = []
    errors = []
    for feed in DEFAULT_OFFICIAL_MACRO_FEEDS:
        try:
            frame = fetch_official_macro_feed(feed, timeout_seconds=args.timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - continue checking the remaining official feeds.
            errors.append(f"{feed.name}: {exc}")
            continue
        if not frame.empty:
            frames.append(frame)
    result = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True) if frames else pd.DataFrame()
    result.attrs["provider_errors"] = errors
    return result


def run_forex_factory(args: argparse.Namespace) -> pd.DataFrame:
    return fetch_forex_factory_weekly_export(format="json", timeout_seconds=args.timeout_seconds)


def sample_frame_titles(frame: pd.DataFrame, *, limit: int) -> list[str]:
    if frame.empty or limit == 0 or "title" not in frame.columns:
        return []
    titles = frame["title"].dropna().astype(str)
    return titles.head(limit).tolist()


def print_summary(results: list[ProviderCheckResult], *, sample_size: int) -> None:
    print("News provider smoke test\n")
    for result in results:
        print(f"{result.provider}: {result.status} ({result.rows} rows)")
        if result.error:
            print(f"  error: {result.error}")
        for title in result.sample_titles[:sample_size]:
            print(f"  - {title}")
        if result.provider == "forex_factory":
            print("  note: ForexFactory is intended for internal/research use, not the production default.")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
