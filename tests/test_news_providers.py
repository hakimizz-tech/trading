import unittest

import pandas as pd

from News.providers import (
    CANONICAL_NEWS_COLUMNS,
    OfficialMacroFeed,
    build_forex_factory_export_url,
    build_google_news_rss_url,
    normalize_forex_factory_export,
    normalize_google_news_rss,
    normalize_official_macro_feed,
    normalize_provider_records,
    normalize_yfinance_news,
)


class NewsProviderTests(unittest.TestCase):
    def test_shared_provider_schema_normalizes_records(self) -> None:
        frame = normalize_provider_records(
            [
                {
                    "timestamp": 1_700_000_000_000,
                    "symbol": "spy",
                    "source": "demo",
                    "title": "SPY upgraded",
                    "body": "Strong growth outlook.",
                    "provider": "fixture",
                    "asset_class": "equity_etf",
                    "event_type": "headline",
                }
            ]
        )

        self.assertEqual(frame.columns.tolist(), CANONICAL_NEWS_COLUMNS)
        self.assertEqual(frame["symbol"].iloc[0], "SPY")
        self.assertIn("Strong growth", frame["text"].iloc[0])

    def test_normalizes_yfinance_news_payload(self) -> None:
        payload = [
            {
                "providerPublishTime": 1_700_000_000,
                "title": "AAPL earnings beat expectations",
                "summary": "Analysts upgraded the stock after strong growth.",
                "link": "https://example.test/aapl",
                "publisher": "Yahoo Finance",
                "relatedTickers": ["AAPL", "QQQ"],
            }
        ]

        frame = normalize_yfinance_news(payload, symbol="AAPL")

        self.assertEqual(set(frame["symbol"]), {"AAPL", "QQQ"})
        self.assertEqual(set(frame["provider"]), {"yfinance"})
        self.assertEqual(set(frame["asset_class"]), {"equity_etf"})

    def test_builds_google_news_url_and_normalizes_rss(self) -> None:
        url = build_google_news_rss_url("Federal Reserve OR FOMC")
        payload = """
        <rss><channel>
          <item>
            <title>Fed keeps rates unchanged</title>
            <link>https://example.test/fed</link>
            <pubDate>Tue, 14 Nov 2023 22:13:20 GMT</pubDate>
            <description>Officials sounded dovish.</description>
            <source>Example Wire</source>
          </item>
        </channel></rss>
        """

        frame = normalize_google_news_rss(payload, symbol="USD", asset_class="macro")

        self.assertIn("Federal+Reserve", url)
        self.assertEqual(frame["provider"].iloc[0], "google_news")
        self.assertEqual(frame["symbol"].iloc[0], "USD")
        self.assertEqual(frame["source"].iloc[0], "Example Wire")

    def test_normalizes_official_macro_rss(self) -> None:
        feed = OfficialMacroFeed("fed_test", "https://example.test/feed.xml", "United States", "USD", "Federal Reserve")
        payload = """
        <rss><channel>
          <item>
            <title>Federal Reserve issues FOMC statement</title>
            <link>https://example.test/fomc</link>
            <pubDate>Tue, 14 Nov 2023 22:13:20 GMT</pubDate>
            <description>Policy remains restrictive.</description>
          </item>
        </channel></rss>
        """

        frame = normalize_official_macro_feed(payload, feed=feed)

        self.assertEqual(frame["provider"].iloc[0], "official_macro")
        self.assertEqual(frame["currency"].iloc[0], "USD")
        self.assertEqual(frame["importance"].iloc[0], "high")

    def test_normalizes_forex_factory_json_export(self) -> None:
        url = build_forex_factory_export_url(format="json", version="demo")
        payload = [
            {
                "title": "CPI m/m",
                "country": "United States",
                "date": "2026-06-25T08:30:00-04:00",
                "impact": "High",
                "forecast": "0.2%",
                "previous": "0.1%",
            }
        ]

        frame = normalize_forex_factory_export(payload, format="json")

        self.assertIn("version=demo", url)
        self.assertEqual(frame["provider"].iloc[0], "forex_factory")
        self.assertEqual(frame["currency"].iloc[0], "USD")
        self.assertEqual(pd.Timestamp(frame["timestamp"].iloc[0]).hour, 12)


if __name__ == "__main__":
    unittest.main()
