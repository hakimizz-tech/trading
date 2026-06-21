import unittest

import pandas as pd

from News import (
    NewsFeatureConfig,
    NewsSignalConfig,
    build_news_feature_matrix,
    build_news_signals,
    create_forward_return_labels,
    decision_from_score,
    extract_events_from_text,
    merge_news_features_and_labels,
    merge_news_features,
    score_text_sentiment,
    score_text_sentiment_components,
)


class NewsSignalModuleTests(unittest.TestCase):
    def test_extracts_positive_and_negative_financial_events(self) -> None:
        positive = extract_events_from_text(
            "AAPL earnings beat expectations and price target raised by analysts",
            symbol="aapl",
            timestamp="2026-06-21",
        )
        negative = extract_events_from_text(
            "MSFT cuts guidance after revenue miss and a regulatory probe",
            symbol="msft",
            timestamp="2026-06-21",
        )

        self.assertTrue(any(event.event_name == "profit_up" for event in positive))
        self.assertTrue(any(event.impact > 0 for event in positive))
        self.assertTrue(any(event.event_name == "guidance_down" for event in negative))
        self.assertTrue(any(event.impact < 0 for event in negative))

    def test_scores_keyword_sentiment(self) -> None:
        self.assertGreater(score_text_sentiment("strong bullish profit growth"), 0.0)
        self.assertLess(score_text_sentiment("weak bearish loss warning"), 0.0)
        self.assertEqual(score_text_sentiment("plain procedural update"), 0.0)

    def test_scores_title_body_and_probability_features(self) -> None:
        breakdown = score_text_sentiment_components("strong bullish growth")
        self.assertGreater(breakdown.positive_probability, breakdown.negative_probability)
        self.assertGreater(breakdown.sentiment_score, 0.0)

        news = pd.DataFrame(
            [
                {
                    "timestamp": "2026-06-20 09:00:00",
                    "symbol": "EURUSD",
                    "title": "EURUSD bullish after CPI cooled",
                    "body": "Analysts remain cautious after weak growth and recession risk.",
                }
            ]
        )
        result = build_news_signals(news, symbols=["EURUSD"])
        row = result.features.xs("EURUSD", level="symbol").iloc[0]

        self.assertIn("title_sentiment_score", result.features.columns)
        self.assertIn("body_sentiment_no_neutral", result.features.columns)
        self.assertIn("positive_probability", result.features.columns)
        self.assertGreater(float(row["title_sentiment_score"]), 0.0)
        self.assertLess(float(row["body_sentiment_score"]), 0.0)
        self.assertGreaterEqual(float(row["positive_probability"]), 0.0)

    def test_builds_news_signals_by_symbol_and_date(self) -> None:
        news = pd.DataFrame(
            [
                {
                    "timestamp": "2026-06-20 12:00:00",
                    "symbol": "AAPL",
                    "headline": "AAPL earnings beat expectations and price target raised",
                    "source": "demo",
                },
                {
                    "timestamp": "2026-06-20 14:00:00",
                    "symbol": "MSFT",
                    "headline": "MSFT cuts guidance after revenue miss",
                    "source": "demo",
                },
            ]
        )

        result = build_news_signals(news, symbols=["AAPL", "MSFT"])

        aapl = result.features.xs("AAPL", level="symbol").iloc[0]
        msft = result.features.xs("MSFT", level="symbol").iloc[0]
        self.assertEqual(aapl["news_signal"], "BUY")
        self.assertEqual(msft["news_signal"], "SELL")
        self.assertGreater(float(aapl["news_score"]), 0.0)
        self.assertLess(float(msft["news_score"]), 0.0)
        self.assertFalse(result.events.empty)

    def test_macro_event_taxonomy_and_news_count_gate(self) -> None:
        news = pd.DataFrame(
            [
                {
                    "timestamp": "2026-06-20 09:00:00",
                    "symbol": "EURUSD",
                    "headline": "CPI hotter than expected as inflation accelerated",
                }
            ]
        )
        config = NewsSignalConfig(min_news_count=2)
        result = build_news_signals(news, symbols=["EURUSD"], config=config)
        row = result.features.xs("EURUSD", level="symbol").iloc[0]

        self.assertTrue(any(event.event_name == "inflation_hot" for event in result.events.itertuples()))
        self.assertEqual(float(row["news_count"]), 1.0)
        self.assertFalse(bool(row["has_enough_news"]))

    def test_aligns_to_market_index_without_lookahead_backfill(self) -> None:
        index = pd.date_range("2026-06-19", periods=3, freq="D")
        news = pd.DataFrame(
            [
                {
                    "timestamp": "2026-06-20 08:00:00",
                    "symbol": "SPY",
                    "headline": "SPY downgraded as outlook lowered",
                }
            ]
        )

        result = build_news_signals(news, symbols=["SPY"], index=index)
        aligned = result.features.xs("SPY", level="symbol")

        self.assertEqual(float(aligned.loc[pd.Timestamp("2026-06-19"), "news_score"]), 0.0)
        self.assertLess(float(aligned.loc[pd.Timestamp("2026-06-20"), "news_score"]), 0.0)
        self.assertEqual(float(aligned.loc[pd.Timestamp("2026-06-21"), "news_score"]), 0.0)

    def test_merges_news_features_into_strategy_frame(self) -> None:
        market = pd.DataFrame(
            {"close": [100.0, 101.0]},
            index=pd.date_range("2026-06-20", periods=2, freq="D"),
        )
        news = pd.DataFrame(
            [{"timestamp": "2026-06-20", "symbol": "SPY", "headline": "SPY upgraded after revenue beat"}]
        )
        signals = build_news_signals(news, symbols=["SPY"], index=market.index)

        merged = merge_news_features(market, signals.features, symbol="SPY")

        self.assertIn("news_score", merged.columns)
        self.assertTrue(bool(merged.loc[pd.Timestamp("2026-06-20"), "news_buy"]))
        self.assertEqual(float(merged.loc[pd.Timestamp("2026-06-21"), "news_score"]), 0.0)

    def test_decision_thresholds_are_configurable(self) -> None:
        config = NewsSignalConfig(bullish_threshold=0.4, bearish_threshold=-0.4)

        self.assertEqual(decision_from_score(0.2, config), "HOLD")
        self.assertEqual(decision_from_score(0.5, config), "BUY")
        self.assertEqual(decision_from_score(-0.5, config), "SELL")

    def test_builds_timeframe_features_and_forward_labels(self) -> None:
        market = pd.DataFrame(
            {"close": [100.0, 101.0, 99.0, 103.0]},
            index=pd.date_range("2026-06-20 09:00:00", periods=4, freq="h"),
        )
        news = pd.DataFrame(
            [
                {
                    "timestamp": "2026-06-20 09:30:00",
                    "symbol": "SPY",
                    "headline": "SPY upgraded after strong growth",
                }
            ]
        )
        matrices = build_news_feature_matrix(news, symbols=["SPY"], index=market.index, frequencies=("1h", "1D"))
        labels = create_forward_return_labels(market, config=NewsFeatureConfig(horizons=(1, 2)))
        merged = merge_news_features_and_labels(
            market,
            matrices["1h"],
            symbol="SPY",
            config=NewsFeatureConfig(horizons=(1,), return_threshold=0.0),
        )

        self.assertIn("1h", matrices)
        self.assertIn("1D", matrices)
        self.assertIn("forward_return_1", labels.columns)
        self.assertTrue(pd.isna(labels.iloc[-1]["forward_return_1"]))
        self.assertIn("target_direction_1", merged.columns)
        self.assertIn("news_score", merged.columns)


if __name__ == "__main__":
    unittest.main()
