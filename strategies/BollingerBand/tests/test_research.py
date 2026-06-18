import tempfile
import unittest
from pathlib import Path

import pandas as pd

from strategies.BollingerBand.research.datasets import load_market_csv
from strategies.BollingerBand.research.walk_forward import WalkForwardConfig, split_walk_forward


class ResearchUtilityTests(unittest.TestCase):
    def test_load_market_csv_normalizes_metatrader_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "GBPUSD_PERIOD_D1.csv"
            path.write_text(
                '"Open","High","Low","Close","Volume","Ticker","Date"\n'
                "1.10,1.20,1.00,1.15,100,GBPUSD,2024.01.02\n"
                "1.15,1.25,1.05,1.20,110,GBPUSD,2024.01.03\n",
                encoding="utf-8",
            )

            data = load_market_csv(path)

        self.assertEqual(data.columns.tolist(), ["open", "high", "low", "close", "volume"])
        self.assertEqual(str(data.attrs["symbol"]), "GBPUSD")
        self.assertEqual(str(data.index[-1].date()), "2024-01-03")
        self.assertTrue(data.index.is_monotonic_increasing)

    def test_load_market_csv_normalizes_investing_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "EUR_USD Historical Data3.csv"
            path.write_text(
                "Date,Price,Open,High,Low,Vol.,Change %\n"
                "03-01-2024,1.10,1.08,1.11,1.07,1.2K,0.10%\n"
                "02-01-2024,1.08,1.07,1.09,1.06,,0.20%\n",
                encoding="utf-8",
            )

            data = load_market_csv(path)

        self.assertEqual(float(data["close"].iloc[-1]), 1.10)
        self.assertEqual(float(data["volume"].iloc[-1]), 1200.0)
        self.assertTrue(data.index.is_monotonic_increasing)

    def test_walk_forward_split_uses_purge_and_embargo(self) -> None:
        data = pd.DataFrame(
            {"close": range(30)},
            index=pd.date_range("2024-01-01", periods=30, freq="D"),
        )

        folds = split_walk_forward(
            data,
            WalkForwardConfig(train_size=10, test_size=5, step_size=5, purge_size=2, embargo_size=1),
        )

        self.assertEqual(len(folds), 3)
        self.assertEqual(folds[0].train_indices.tolist(), list(range(8)))
        self.assertEqual(folds[0].test_indices.tolist(), list(range(11, 16)))


if __name__ == "__main__":
    unittest.main()
