import unittest

import pandas as pd

from market_data.ohlcv import load_ohlcv_csv, process_ohlcv, quality_report, resample_ohlcv, to_ohlcv_frame


class OhlcvProcessingTests(unittest.TestCase):
    def test_loads_mt5_style_csv_as_canonical_utc_ohlcv(self) -> None:
        data = load_ohlcv_csv("datasets/GBPUSD/GBPUSD_PERIOD_D1.csv")

        self.assertEqual(["open", "high", "low", "close", "volume"], data.columns.tolist())
        self.assertEqual(str(data.index.tz), "UTC")
        self.assertEqual(data.attrs["symbol"], "GBPUSD")
        self.assertEqual(data.attrs["timeframe"], "D1")
        self.assertGreater(len(data), 100)

    def test_loads_investing_style_csv(self) -> None:
        data = load_ohlcv_csv("datasets/EURUSD/EUR_USD Historical Data3.csv")

        self.assertEqual(["open", "high", "low", "close", "volume"], data.columns.tolist())
        self.assertEqual(str(data.index.tz), "UTC")
        self.assertGreater(float(data["close"].iloc[-1]), 0.0)

    def test_loads_adjusted_close_only_stock_as_flat_candles(self) -> None:
        data = load_ohlcv_csv("datasets/SPY/SPYdata.csv")

        self.assertTrue(bool(data.attrs["price_only"]))
        self.assertTrue((data["open"] == data["close"]).all())
        self.assertTrue((data["volume"] == 0.0).all())

    def test_process_adds_quality_flags(self) -> None:
        data = load_ohlcv_csv("datasets/QQQ/Invesco QQQ 5  Years price Data.csv")
        processed = process_ohlcv(data)

        self.assertIn("anomaly_any", processed.columns)
        self.assertIn("is_filled", processed.columns)

    def test_resamples_ohlcv(self) -> None:
        data = load_ohlcv_csv("datasets/xauusd/XAU_1h_data.csv").head(16)
        resampled = resample_ohlcv(data, "4h")

        self.assertEqual(["open", "high", "low", "close", "volume"], resampled.columns.tolist())
        self.assertGreaterEqual(len(resampled), 4)

    def test_aiomql_candles_convert_to_ohlcv_frame(self) -> None:
        candles = [
            {"time": "2026-01-01 00:00:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "tick_volume": 12, "spread": 2},
            {"time": "2026-01-01 00:01:00", "open": 1.05, "high": 1.2, "low": 1.0, "close": 1.1, "tick_volume": 10, "spread": 3},
        ]

        data = to_ohlcv_frame(candles, symbol="EURUSD")

        self.assertEqual(str(data.index.tz), "UTC")
        self.assertIn("spread", data.columns)
        self.assertEqual(float(data["volume"].iloc[0]), 12.0)

    def test_mt5_epoch_second_rates_convert_to_utc_index(self) -> None:
        rates = [
            {"time": 1767225600, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "tick_volume": 12},
        ]

        data = to_ohlcv_frame(rates, symbol="EURUSD")

        self.assertEqual(str(data.index.tz), "UTC")
        self.assertEqual(data.index[0].year, 2026)

    def test_quality_report_counts_impossible_candle(self) -> None:
        data = pd.DataFrame(
            {"open": [1.0], "high": [0.9], "low": [1.1], "close": [1.0], "volume": [1.0]},
            index=pd.to_datetime(["2026-01-01"], utc=True),
        )

        report = quality_report(data)

        self.assertEqual(report.impossible_candles, 1)


if __name__ == "__main__":
    unittest.main()
