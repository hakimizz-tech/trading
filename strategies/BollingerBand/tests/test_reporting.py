import tempfile
import unittest
from types import SimpleNamespace

import pandas as pd

from strategies.BollingerBand.reporting import (
    build_bollinger_report_frame,
    generate_bollinger_strategy_report,
    normalize_bollinger_report_trades,
    summarize_bollinger_trades,
)


class BollingerReportingTests(unittest.TestCase):
    def test_normalize_vectorbt_trades_creates_entry_and_exit_rows(self) -> None:
        trades = pd.DataFrame(
            {
                "Exit Trade Id": [7],
                "Size": [1.5],
                "Entry Timestamp": [pd.Timestamp("2024-01-01 10:00")],
                "Avg Entry Price": [100.0],
                "Exit Timestamp": [pd.Timestamp("2024-01-01 12:00")],
                "Avg Exit Price": [106.0],
                "PnL": [9.0],
                "Return": [0.06],
                "Direction": ["Long"],
                "Status": ["Closed"],
            }
        )

        normalized = normalize_bollinger_report_trades(trades)

        self.assertEqual(normalized["action"].tolist(), ["ENTER_LONG", "EXIT_LONG"])
        self.assertEqual(normalized["side"].tolist(), ["long", "long"])
        self.assertEqual(float(normalized["return_pct"].iloc[1]), 6.0)

    def test_summarize_trades_uses_closed_exit_rows(self) -> None:
        trades = pd.DataFrame(
            {
                "trade_id": [1, 1, 2, 2],
                "timestamp": pd.date_range("2024-01-01", periods=4, freq="h"),
                "action": ["ENTER_LONG", "EXIT_LONG", "ENTER_SHORT", "EXIT_SHORT"],
                "price": [100.0, 104.0, 103.0, 108.0],
                "side": ["long", "long", "short", "short"],
                "size": [1.0, 1.0, 1.0, 1.0],
                "pnl": [pd.NA, 4.0, pd.NA, -5.0],
                "return_pct": [pd.NA, 4.0, pd.NA, -4.85],
                "status": ["", "Closed", "", "Closed"],
                "reason": ["entry", "exit", "entry", "exit"],
            }
        )

        summary = summarize_bollinger_trades(trades)

        self.assertEqual(int(summary["closed_trades"].iloc[0]), 2)
        self.assertEqual(int(summary["wins"].iloc[0]), 1)
        self.assertAlmostEqual(float(summary["win_rate"].iloc[0]), 0.5)
        self.assertAlmostEqual(float(summary["total_pnl"].iloc[0]), -1.0)

    def test_generate_report_exports_standard_files_without_charts(self) -> None:
        result = _sample_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_bollinger_strategy_report(
                result,
                name="GBPUSD M15 adaptive",
                output_dir=tmpdir,
                render_charts=False,
            )

            self.assertTrue(report.paths["data"].exists())
            self.assertTrue(report.paths["trades"].exists())
            self.assertTrue(report.paths["trade_summary"].exists())
            self.assertTrue(report.paths["metrics"].exists())
            self.assertTrue(report.paths["markdown"].exists())
            self.assertEqual(report.name, "GBPUSD_M15_adaptive")

    def test_build_report_frame_adds_bands_equity_drawdown_and_position(self) -> None:
        frame = build_bollinger_report_frame(_sample_result())

        self.assertIn("bb_upper", frame.columns)
        self.assertIn("equity", frame.columns)
        self.assertIn("drawdown", frame.columns)
        self.assertIn("position", frame.columns)
        self.assertEqual(len(frame), 30)


def _sample_result() -> SimpleNamespace:
    index = pd.date_range("2024-01-01", periods=30, freq="h")
    close = pd.Series([100 + (idx % 5) for idx in range(30)], index=index, dtype=float)
    data = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 100.0,
            "long_entry": [False, True, *([False] * 28)],
            "long_exit": [False, False, False, True, *([False] * 26)],
            "short_entry": False,
            "short_exit": False,
        },
        index=index,
    )
    trades = pd.DataFrame(
        {
            "Exit Trade Id": [0],
            "Size": [1.0],
            "Entry Timestamp": [index[1]],
            "Avg Entry Price": [101.0],
            "Exit Timestamp": [index[3]],
            "Avg Exit Price": [103.0],
            "PnL": [2.0],
            "Return": [0.0198],
            "Direction": ["Long"],
            "Status": ["Closed"],
        }
    )
    return SimpleNamespace(
        signals=SimpleNamespace(data=data),
        trades=trades,
        equity=pd.Series([10_000 + idx * 10 for idx in range(30)], index=index, dtype=float),
        drawdown=pd.Series([0.0] * 30, index=index, dtype=float),
        metrics={"total_return": 0.03, "trade_count": 1},
    )


if __name__ == "__main__":
    unittest.main()
