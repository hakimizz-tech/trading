import importlib.util
import unittest
import warnings

import pandas as pd

from strategies.BollingerBand.backtesting.signals import prepare_bollinger_signals
from strategies.BollingerBand.backtesting.vectorbt_engine import (
    VectorBTBacktestConfig,
    optimize_bollinger_vectorbt,
    run_bollinger_vectorbt,
    run_bollinger_vectorbt_train_test,
)
from strategies.BollingerBand.core import AdaptiveRegimeConfig, ExitPlan

HAS_VECTORBT = importlib.util.find_spec("vectorbt") is not None


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

    def test_prepare_bollinger_signals_supports_adaptive_sub_regimes(self) -> None:
        data = _sample_ohlcv(80)

        prepared = prepare_bollinger_signals(
            data,
            strategy="adaptive_breakout",
            adaptive_config=_fast_config(),
        )

        self.assertIn("breakout_long_raw", prepared.data.columns)
        self.assertEqual(prepared.data["mean_reversion_long"].sum(), 0)
        self.assertEqual(prepared.data["mean_reversion_short"].sum(), 0)

    @unittest.skipIf(importlib.util.find_spec("vectorbt") is not None, "vectorbt is installed")
    def test_vectorbt_runner_has_clear_missing_dependency_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "vectorbt is not installed"):
            run_bollinger_vectorbt(_sample_ohlcv())

    @unittest.skipUnless(HAS_VECTORBT, "vectorbt is not installed")
    def test_vectorbt_runner_returns_research_artifacts(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run_bollinger_vectorbt(
                _sample_ohlcv(80),
                adaptive_config=_fast_config(),
                exit_plan=ExitPlan(atr_length=3),
                config=VectorBTBacktestConfig(freq="1h"),
            )

        direction_warnings = [warning for warning in caught if "direction has no effect" in str(warning.message)]
        self.assertEqual(direction_warnings, [])
        self.assertEqual(len(result.equity), 80)
        self.assertEqual(len(result.returns), 80)
        self.assertEqual(len(result.drawdown), 80)
        self.assertIn("total_return", result.metrics)
        self.assertIn("trade_count", result.metrics)
        self.assertIsInstance(result.trades, pd.DataFrame)

    @unittest.skipUnless(HAS_VECTORBT, "vectorbt is not installed")
    def test_vectorbt_optimizer_returns_ranked_metrics(self) -> None:
        ranked = optimize_bollinger_vectorbt(
            _sample_ohlcv(80),
            {"bb_window": [3, 4], "bb_num_std": [1.0]},
            base_adaptive_config=_fast_config(),
            exit_plan=ExitPlan(atr_length=3),
            config=VectorBTBacktestConfig(freq="1h"),
            sort_by="total_return",
        )

        self.assertEqual(len(ranked), 2)
        self.assertIn("bb_window", ranked.columns)
        self.assertIn("total_return", ranked.columns)

    @unittest.skipUnless(HAS_VECTORBT, "vectorbt is not installed")
    def test_vectorbt_train_test_returns_chronological_splits(self) -> None:
        split_metrics = run_bollinger_vectorbt_train_test(
            _sample_ohlcv(80),
            train_fraction=0.6,
            adaptive_config=_fast_config(),
            exit_plan=ExitPlan(atr_length=3),
            config=VectorBTBacktestConfig(freq="1h"),
        )

        self.assertEqual(split_metrics["split"].tolist(), ["train", "test"])
        self.assertEqual(split_metrics["rows"].tolist(), [48, 32])


def _fast_config() -> AdaptiveRegimeConfig:
    return AdaptiveRegimeConfig(
        bb_window=3,
        bb_num_std=1.0,
        rsi_window=3,
        macd_fast=2,
        macd_slow=4,
        macd_signal=2,
        bandwidth_lookback=5,
        squeeze_release_bars=2,
        volume_window=3,
    )


def _sample_ohlcv(length: int = 15) -> pd.DataFrame:
    pattern = [100.0, 98.0, 96.0, 99.0, 103.0, 106.0, 102.0, 99.0, 95.0, 97.0]
    close = [pattern[i % len(pattern)] for i in range(length)]
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
