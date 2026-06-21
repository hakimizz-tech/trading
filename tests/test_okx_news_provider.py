import unittest

import pandas as pd

from News.providers.okx import (
    OkxNewsProviderConfig,
    build_okx_by_coin_command,
    build_okx_coin_sentiment_command,
    build_okx_economic_calendar_command,
    normalize_okx_coin_sentiment,
    normalize_okx_coin_trend,
    normalize_okx_economic_calendar,
    normalize_okx_news,
    okx_news_to_signals,
)


class OkxNewsProviderTests(unittest.TestCase):
    def test_builds_live_profile_commands_without_calling_cli(self) -> None:
        config = OkxNewsProviderConfig(cli="okx", profile="live", lang="en-US")

        coin_command = build_okx_by_coin_command(["btc", "eth"], limit=5, config=config)
        sentiment_command = build_okx_coin_sentiment_command(["btc"], period="24h", config=config)
        calendar_command = build_okx_economic_calendar_command(
            before_ms=1_700_000_000_000,
            after_ms=1_700_086_400_000,
            region="united_states",
            importance=3,
            config=config,
        )

        self.assertEqual(coin_command[:5], ["okx", "--profile", "live", "news", "by-coin"])
        self.assertIn("--json", coin_command)
        self.assertIn("BTC,ETH", coin_command)
        self.assertEqual(sentiment_command[:5], ["okx", "--profile", "live", "news", "coin-sentiment"])
        self.assertIn("--before", calendar_command)
        self.assertIn("--after", calendar_command)

    def test_normalizes_okx_news_payload_to_articles(self) -> None:
        payload = {
            "data": [
                {
                    "id": "1",
                    "publishTime": 1_700_000_000_000,
                    "coins": ["BTC", "ETH"],
                    "platform": "CoinDesk",
                    "title": "BTC ETF approval boosts sentiment",
                    "summary": "Analysts upgraded Bitcoin outlook after strong inflows.",
                    "url": "https://example.test/news",
                    "sentiment": "bullish",
                }
            ]
        }

        frame = normalize_okx_news(payload)

        self.assertEqual(len(frame), 2)
        self.assertEqual(set(frame["symbol"]), {"BTC", "ETH"})
        self.assertIn("ETF approval", frame["text"].iloc[0])
        self.assertEqual(frame["source"].iloc[0], "CoinDesk")

    def test_okx_news_payload_flows_into_generic_signals(self) -> None:
        payload = {
            "data": [
                {
                    "publishTime": 1_700_000_000_000,
                    "coin": "BTC",
                    "title": "BTC upgraded after revenue beat style inflows",
                    "summary": "Strong bullish demand and price target raised by analysts.",
                }
            ]
        }

        result = okx_news_to_signals(payload, symbols=["BTC"])
        row = result.features.xs("BTC", level="symbol").iloc[0]

        self.assertEqual(row["news_signal"], "BUY")
        self.assertGreater(float(row["news_score"]), 0.0)

    def test_normalizes_coin_sentiment_snapshot(self) -> None:
        payload = {"data": [{"symbol": "BTC", "label": "bullish", "bullishRatio": 68, "bearishRatio": 32, "mentionCount": 1234}]}

        frame = normalize_okx_coin_sentiment(payload)

        self.assertEqual(frame["symbol"].iloc[0], "BTC")
        self.assertAlmostEqual(float(frame["okx_bullish_ratio"].iloc[0]), 0.68)
        self.assertGreater(float(frame["okx_sentiment_score"].iloc[0]), 0.0)

    def test_normalizes_coin_trend_points(self) -> None:
        payload = {
            "trendPoints": [
                {"time": 1_700_000_000_000, "bullishRatio": 40, "bearishRatio": 60, "mentionCount": 20},
                {"time": 1_700_003_600_000, "bullishRatio": 70, "bearishRatio": 30, "mentionCount": 80},
            ]
        }

        frame = normalize_okx_coin_trend(payload, fallback_symbol="SOL")

        self.assertEqual(frame["symbol"].tolist(), ["SOL", "SOL"])
        self.assertLess(float(frame["okx_sentiment_score"].iloc[0]), 0.0)
        self.assertGreater(float(frame["okx_sentiment_score"].iloc[1]), 0.0)

    def test_normalizes_economic_calendar_surprise(self) -> None:
        payload = {
            "data": [
                {
                    "eventTime": 1_700_000_000_000,
                    "event": "CPI YoY",
                    "region": "united_states",
                    "importance": 3,
                    "actual": "3.4",
                    "forecast": "3.2",
                    "previous": "3.1",
                }
            ]
        }

        frame = normalize_okx_economic_calendar(payload)

        self.assertEqual(frame["event"].iloc[0], "CPI YoY")
        self.assertTrue(bool(frame["released"].iloc[0]))
        self.assertAlmostEqual(float(frame["surprise"].iloc[0]), 0.2)


if __name__ == "__main__":
    unittest.main()
