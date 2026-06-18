import unittest

import numpy as np
import pandas as pd

from strategies.BollingerBand.core import (
    BUY,
    SELL,
    AdaptiveRegimeConfig,
    ExitPlan,
    add_entry_filters,
    add_macd,
    backtest_entries_with_exits,
    backtest_signals,
    calculate_bollinger_bands,
    generate_bbma_signals,
    generate_adaptive_bollinger_signals,
    generate_mean_reversion_signals,
    optimize_bollinger_parameters,
)


class BollingerBandsStrategyTests(unittest.TestCase):
    def test_bollinger_bands_use_population_standard_deviation(self) -> None:
        data = pd.DataFrame({"close": [1.0, 2.0, 3.0]})

        result = calculate_bollinger_bands(data, window=3, num_std=2)
        population_std = float(np.std([1.0, 2.0, 3.0], ddof=0))
        middle = result["bb_middle"].to_numpy(dtype=float)
        upper = result["bb_upper"].to_numpy(dtype=float)
        lower = result["bb_lower"].to_numpy(dtype=float)

        self.assertAlmostEqual(middle[2], 2.0)
        self.assertAlmostEqual(upper[2], 2.0 + 2.0 * population_std)
        self.assertAlmostEqual(lower[2], 2.0 - 2.0 * population_std)

    def test_mean_reversion_signals_match_requested_cross_rules(self) -> None:
        data = pd.DataFrame(
            {
                "close": [9.0, 11.0, 21.0, 19.0],
                "bb_middle": [15.0, 15.0, 15.0, 15.0],
                "bb_lower": [10.0, 10.0, 10.0, 10.0],
                "bb_upper": [20.0, 20.0, 20.0, 20.0],
            }
        )

        result = generate_mean_reversion_signals(data)

        self.assertEqual(result.loc[1, "signal"], BUY)
        self.assertEqual(result.loc[3, "signal"], SELL)

    def test_bbma_crosses_middle_band(self) -> None:
        data = pd.DataFrame(
            {
                "close": [10.0, 12.0, 14.0, 16.0],
                "bb_middle": [11.0, 11.0, 11.0, 11.0],
            }
        )

        result = generate_bbma_signals(data, ema_span=2)

        self.assertTrue((result["signal"] == BUY).any())

    def test_macd_columns_are_added(self) -> None:
        data = pd.DataFrame({"close": [100.0, 101.0, 102.0, 101.0, 103.0, 105.0]})

        result = add_macd(data, fast=2, slow=4, signal=2)

        self.assertIn("macd_2_4_2", result.columns)
        self.assertIn("macd_signal_2_4_2", result.columns)
        self.assertIn("macd_hist_2_4_2", result.columns)

    def test_adaptive_strategy_detects_squeeze_breakout_with_macd_confirmation(self) -> None:
        close = [100.0] * 10 + [105.0]
        data = pd.DataFrame(
            {
                "open": close,
                "high": [price + 0.5 for price in close],
                "low": [price - 0.5 for price in close],
                "close": close,
                "volume": [100.0] * len(close),
            }
        )
        config = AdaptiveRegimeConfig(
            bb_window=3,
            bb_num_std=1.0,
            rsi_window=3,
            macd_fast=2,
            macd_slow=4,
            macd_signal=2,
            bandwidth_lookback=5,
            squeeze_quantile=0.5,
            wide_quantile=0.0,
            squeeze_release_bars=5,
        )

        result = generate_adaptive_bollinger_signals(data, config=config)

        self.assertTrue(bool(result.loc[10, "long_entry"]))
        self.assertEqual(result.loc[10, "regime"], "breakout")

    def test_adaptive_regime_mode_can_disable_breakout_entries(self) -> None:
        close = [100.0] * 10 + [105.0]
        data = pd.DataFrame(
            {
                "open": close,
                "high": [price + 0.5 for price in close],
                "low": [price - 0.5 for price in close],
                "close": close,
                "volume": [100.0] * len(close),
            }
        )
        config = AdaptiveRegimeConfig(
            regime_mode="mean_reversion",
            bb_window=3,
            bb_num_std=1.0,
            rsi_window=3,
            macd_fast=2,
            macd_slow=4,
            macd_signal=2,
            bandwidth_lookback=5,
            squeeze_quantile=0.5,
            wide_quantile=0.0,
            squeeze_release_bars=5,
        )

        result = generate_adaptive_bollinger_signals(data, config=config)

        self.assertTrue(bool(result.loc[10, "breakout_long_raw"]))
        self.assertFalse(bool(result.loc[10, "breakout_long"]))
        self.assertFalse(bool(result.loc[10, "long_entry"]))

    def test_entry_filters_gate_spread_and_session(self) -> None:
        data = pd.DataFrame(
            {"spread": [1.0, 5.0, 1.0]},
            index=pd.to_datetime(["2024-01-01 08:00", "2024-01-01 09:00", "2024-01-01 20:00"]),
        )

        result = add_entry_filters(
            data,
            AdaptiveRegimeConfig(max_spread=2.0, session_start="07:00", session_end="17:00"),
        )

        self.assertEqual(result["spread_filter_pass"].tolist(), [True, False, True])
        self.assertEqual(result["session_filter_pass"].tolist(), [True, True, False])
        self.assertEqual(result["entry_filter_pass"].tolist(), [True, False, False])

    def test_backtest_ignores_consecutive_same_side_actions(self) -> None:
        data = pd.DataFrame(
            {
                "close": [100.0, 110.0, 100.0, 90.0],
                "signal": [BUY, BUY, SELL, SELL],
            }
        )

        result = backtest_signals(data)

        self.assertEqual(result.data["accepted_signal"].tolist(), [BUY, 0, SELL, 0])
        self.assertEqual(result.metrics["trade_count"], 2)

    def test_explicit_exit_backtest_stops_long_trade(self) -> None:
        data = _entry_exit_frame(close=[100.0, 100.0, 100.0, 95.0], high=[101.0, 101.0, 101.0, 96.0], low=[99.0, 99.0, 99.0, 94.0])
        data.loc[2, "long_entry"] = True

        result = backtest_entries_with_exits(data, exit_plan=ExitPlan(atr_length=2, max_hold_bars=10))

        self.assertEqual(result.trades["action"].tolist(), ["ENTER_LONG", "EXIT_LONG"])
        self.assertEqual(result.trades["reason"].tolist(), ["entry", "stop_loss"])
        self.assertEqual(result.metrics["stop_exits"], 1)

    def test_explicit_exit_backtest_takes_profit_on_long_trade(self) -> None:
        data = _entry_exit_frame(close=[100.0, 100.0, 100.0, 109.0], high=[101.0, 101.0, 101.0, 110.0], low=[99.0, 99.0, 99.0, 108.0])
        data.loc[2, "long_entry"] = True

        result = backtest_entries_with_exits(data, exit_plan=ExitPlan(atr_length=2, take_profit_rr=2.0, max_hold_bars=10))

        self.assertEqual(result.trades["action"].tolist(), ["ENTER_LONG", "EXIT_LONG"])
        self.assertEqual(result.trades["reason"].tolist(), ["entry", "take_profit"])
        self.assertEqual(result.metrics["take_profit_exits"], 1)

    def test_explicit_exit_backtest_time_stops_dead_trade(self) -> None:
        data = _entry_exit_frame(close=[100.0, 100.0, 100.0, 100.0], high=[101.0, 101.0, 101.0, 101.0], low=[99.0, 99.0, 99.0, 99.0])
        data.loc[2, "long_entry"] = True

        result = backtest_entries_with_exits(data, exit_plan=ExitPlan(atr_length=2, max_hold_bars=1))

        self.assertEqual(result.trades["action"].tolist(), ["ENTER_LONG", "EXIT_LONG"])
        self.assertEqual(result.trades["reason"].tolist(), ["entry", "time_stop"])
        self.assertEqual(result.metrics["time_exits"], 1)

    def test_optimizer_returns_sorted_parameter_table(self) -> None:
        close = [100.0, 98.0, 96.0, 94.0, 97.0, 100.0, 103.0, 105.0, 102.0, 99.0] * 3
        data = pd.DataFrame(
            {
                "open": close,
                "high": [price + 1.0 for price in close],
                "low": [price - 1.0 for price in close],
                "close": close,
                "volume": [100.0] * len(close),
            }
        )

        result = optimize_bollinger_parameters(
            data,
            windows=(3, 4),
            num_stds=(1.5,),
            atr_stop_multipliers=(1.5,),
            take_profit_rrs=(1.5,),
        )

        self.assertEqual(len(result), 2)
        self.assertIn("relative_roi", result.columns)


def _entry_exit_frame(close: list[float], high: list[float], low: list[float]) -> pd.DataFrame:
    size = len(close)
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": [100.0] * size,
            "long_entry": [False] * size,
            "short_entry": [False] * size,
            "long_exit": [False] * size,
            "short_exit": [False] * size,
        }
    )


if __name__ == "__main__":
    unittest.main()
