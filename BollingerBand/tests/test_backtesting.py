import importlib.util
import unittest

import pandas as pd

from BollingerBand.backtesting.signals import prepare_bollinger_signals
from BollingerBand.backtesting.vectorbt_engine import VectorBTBacktestConfig, run_bollinger_vectorbt
from BollingerBand.core import AdaptiveRegimeConfig, ExitPlan


class BacktestingSignalsTests(unittest.TestCase):
    def test_prepare_bollinger_signals_normalizes_strategy_columns(self) -> None:
        data = _sample_ohlcv()

        prepared = prepare_bollinger_signals(
            data,
            adaptive_config=AdaptiveRegimeConfig(
                bb_window=3,
                bb_num_std=1.0,
                rsi_window=3,
                macd_fast=2,
                macd_slow=4,
                macd_signal=2,
                bandwidth_lookback=5,
            ),
            exit_plan=ExitPlan(atr_length=3),
        )

        self.assertEqual(len(prepared.close), len(data))
        self.assertEqual(prepared.long_entries.dtype, bool)
        self.assertEqual(prepared.short_entries.dtype, bool)
        self.assertIsNotNone(prepared.stop_loss)
        self.assertIsNotNone(prepared.take_profit)
        self.assertIn("regime", prepared.data.columns)

    def test_vectorbt_config_defaults_are_research_safe(self) -> None:
        config = VectorBTBacktestConfig()

        self.assertGreater(config.init_cash, 0)
        self.assertGreaterEqual(config.fees, 0)
        self.assertGreaterEqual(config.slippage, 0)
        self.assertTrue(config.use_stops)

    @unittest.skipIf(importlib.util.find_spec("vectorbt") is not None, "vectorbt is installed")
    def test_vectorbt_runner_has_clear_missing_dependency_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "vectorbt is not installed"):
            run_bollinger_vectorbt(_sample_ohlcv())


def _sample_ohlcv() -> pd.DataFrame:
    close = [100.0] * 10 + [105.0, 103.0, 101.0, 99.0, 102.0]
    return pd.DataFrame(
        {
            "open": close,
            "high": [price + 1.0 for price in close],
            "low": [price - 1.0 for price in close],
            "close": close,
            "volume": [100.0] * len(close),
        },
        index=pd.date_range("2024-01-01", periods=len(close), freq="h"),
    )


if __name__ == "__main__":
    unittest.main()
