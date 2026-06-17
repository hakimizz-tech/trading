import importlib.util
import unittest

import pandas as pd

from visualization import extract_result_parts, normalize_trades


class VisualizationTests(unittest.TestCase):
    def test_normalize_trades_splits_entries_and_exits(self) -> None:
        trades = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=4, freq="h"),
                "action": ["ENTER_LONG", "EXIT_LONG", "ENTER_SHORT", "EXIT_SHORT"],
                "price": [100.0, 104.0, 103.0, 98.0],
                "reason": ["entry", "take_profit", "entry", "signal_exit"],
            }
        )

        markers = normalize_trades(trades)

        self.assertEqual(markers.entries["side"].tolist(), ["long", "short"])
        self.assertEqual(markers.exits["side"].tolist(), ["long", "short"])
        self.assertEqual(markers.exits["reason"].tolist(), ["take_profit", "signal_exit"])

    def test_extract_result_parts_supports_prepared_signals_shape(self) -> None:
        from types import SimpleNamespace

        index = pd.date_range("2024-01-01", periods=3, freq="h")
        signal_data = pd.DataFrame(
            {
                "close": [100.0, 102.0, 101.0],
                "long_entry": [False, True, False],
                "short_entry": [False, False, False],
                "long_exit": [False, False, True],
                "short_exit": [False, False, False],
            },
            index=index,
        )

        data, trades = extract_result_parts(SimpleNamespace(signals=SimpleNamespace(data=signal_data)))

        self.assertIn("position", data.columns)
        self.assertIn("equity", data.columns)
        self.assertEqual(trades["action"].tolist(), ["ENTER_LONG", "EXIT_LONG"])

    @unittest.skipIf(importlib.util.find_spec("matplotlib") is None, "matplotlib is not installed")
    def test_plot_backtest_report_returns_figure(self) -> None:
        from types import SimpleNamespace

        from visualization import plot_backtest_report

        index = pd.date_range("2024-01-01", periods=4, freq="h")
        data = pd.DataFrame(
            {
                "close": [100.0, 102.0, 101.0, 105.0],
                "equity": [1.0, 1.02, 1.01, 1.05],
                "position": [0, 1, 1, 0],
                "buy_hold_equity": [1.0, 1.02, 1.01, 1.05],
            },
            index=index,
        )
        trades = pd.DataFrame(
            {
                "timestamp": [index[1], index[3]],
                "action": ["ENTER_LONG", "EXIT_LONG"],
                "price": [102.0, 105.0],
                "reason": ["entry", "take_profit"],
            }
        )

        fig = plot_backtest_report(SimpleNamespace(data=data, trades=trades))

        self.assertEqual(len(fig.axes), 4)


if __name__ == "__main__":
    unittest.main()
