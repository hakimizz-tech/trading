import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from scripts import download_yfinance_history as script


class YFinanceHistoryScriptTests(unittest.TestCase):
    def test_extracts_multi_ticker_history_and_writes_normalized_dataset(self) -> None:
        index = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
        raw = pd.DataFrame(
            {
                ("Open", "SPY"): [100.0, 101.0, 102.0],
                ("High", "SPY"): [101.0, 102.0, 103.0],
                ("Low", "SPY"): [99.0, 100.0, 101.0],
                ("Close", "SPY"): [100.5, 101.5, 102.5],
                ("Volume", "SPY"): [10, 11, 12],
                ("Open", "QQQ"): [200.0, 201.0, 202.0],
                ("High", "QQQ"): [201.0, 202.0, 203.0],
                ("Low", "QQQ"): [199.0, 200.0, 201.0],
                ("Close", "QQQ"): [200.5, 201.5, 202.5],
                ("Volume", "QQQ"): [20, 21, 22],
            },
            index=index,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fake_yf = SimpleNamespace(download=lambda **_: raw)
            args = [
                "--tickers",
                "SPY",
                "QQQ",
                "--output-dir",
                str(root / "datasets"),
                "--raw-dir",
                str(root / "raw"),
                "--manifest",
                str(root / "manifest.json"),
            ]
            with patch.object(script, "_import_yfinance", return_value=fake_yf), patch("sys.argv", ["download_yfinance_history.py", *args]):
                exit_code = script.main()

            self.assertEqual(exit_code, 0)
            spy_path = root / "datasets" / "SPY" / "SPY_1d_yfinance.csv"
            qqq_path = root / "datasets" / "QQQ" / "QQQ_1d_yfinance.csv"
            self.assertTrue(spy_path.exists())
            self.assertTrue(qqq_path.exists())
            spy = pd.read_csv(spy_path)
            self.assertEqual(["timestamp", "open", "high", "low", "close", "volume"], spy.columns.tolist())
            self.assertTrue((root / "manifest.json").exists())

    def test_default_tickers_are_rising_assets_universe(self) -> None:
        args = SimpleNamespace(rising_assets_universe=False, tickers_file=None, tickers=None)

        tickers = script._resolve_tickers(args)

        self.assertIn("SPY", tickers)
        self.assertIn("AGG", tickers)
        self.assertEqual(args.ticker_source, "RisingAssest.RISING_ASSETS_UNIVERSE")


if __name__ == "__main__":
    unittest.main()
