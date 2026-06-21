import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from scripts import check_news_providers as script


def provider_frame(title: str, *, timestamp: str = "2026-06-21") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp(timestamp),
                "symbol": "USD",
                "source": "fixture",
                "title": title,
                "body": "fixture body",
                "url": "https://example.test/news",
                "provider": "fixture",
                "asset_class": "macro",
                "event_type": "headline",
                "country": "United States",
                "currency": "USD",
                "importance": "high",
                "text": title,
            }
        ]
    )


class CheckNewsProvidersScriptTests(unittest.TestCase):
    def test_resolves_provider_names_with_forex_factory_flag(self) -> None:
        args = SimpleNamespace(providers=("yfinance",), include_forex_factory=True)

        providers = script.resolve_provider_names(args)

        self.assertEqual(providers, ("yfinance", "forex_factory"))

    def test_all_provider_selection_expands_every_runner(self) -> None:
        args = SimpleNamespace(providers=("all",), include_forex_factory=False)

        providers = script.resolve_provider_names(args)

        self.assertEqual(providers, ("yfinance", "google_news", "official_macro", "forex_factory"))

    def test_run_provider_check_returns_error_without_raising(self) -> None:
        args = SimpleNamespace(sample_size=2)

        result = script.run_provider_check("broken", lambda _: (_ for _ in ()).throw(RuntimeError("network down")), args)

        self.assertEqual(result.status, "error")
        self.assertEqual(result.rows, 0)
        self.assertIn("network down", result.error or "")

    def test_run_provider_check_marks_partial_when_frame_has_provider_errors(self) -> None:
        args = SimpleNamespace(sample_size=1)
        frame = provider_frame("Fed minutes released")
        frame.attrs["provider_errors"] = ["rba_media: 403"]

        result = script.run_provider_check("official_macro", lambda _: frame, args)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.rows, 1)
        self.assertEqual(result.sample_titles, ["Fed minutes released"])
        self.assertIn("rba_media", result.error or "")

    def test_run_official_macro_continues_after_one_feed_fails(self) -> None:
        feeds = [
            SimpleNamespace(name="fed_test"),
            SimpleNamespace(name="rba_test"),
        ]

        def fake_fetch(feed, *, timeout_seconds):
            if feed.name == "rba_test":
                raise RuntimeError("403")
            return provider_frame("Fed statement")

        args = SimpleNamespace(timeout_seconds=3)
        with patch.object(script, "DEFAULT_OFFICIAL_MACRO_FEEDS", feeds), patch.object(script, "fetch_official_macro_feed", side_effect=fake_fetch):
            frame = script.run_official_macro(args)

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame["title"].iloc[0], "Fed statement")
        self.assertEqual(frame.attrs["provider_errors"], ["rba_test: 403"])

    def test_main_writes_json_output_from_mocked_provider(self) -> None:
        output = Path("news_provider_check.json")
        argv = [
            "check_news_providers.py",
            "--providers",
            "google_news",
            "--sample-size",
            "1",
            "--output",
            str(output),
        ]
        with (
            patch("sys.argv", argv),
            patch.object(script, "fetch_google_news_rss", return_value=provider_frame("Inflation cools")),
            patch.object(Path, "mkdir"),
            patch.object(Path, "write_text") as write_text,
            patch("builtins.print"),
        ):
            exit_code = script.main()

        payload = json.loads(write_text.call_args.args[0])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload[0]["provider"], "google_news")
        self.assertEqual(payload[0]["status"], "ok")
        self.assertEqual(payload[0]["sample_titles"], ["Inflation cools"])

    def test_main_fail_on_empty_returns_nonzero(self) -> None:
        argv = ["check_news_providers.py", "--providers", "google_news", "--fail-on-empty"]
        with patch("sys.argv", argv), patch.object(script, "fetch_google_news_rss", return_value=pd.DataFrame()), patch("builtins.print"):
            exit_code = script.main()

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
