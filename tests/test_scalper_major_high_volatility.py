import unittest

import pandas as pd

from strategies.ScalperMajorHighVolatility import (
    RecoveryConfig,
    ScalperMajorConfig,
    backtest_scalper_major,
    backtest_scalper_major_recovery,
    compute_scalper_major_indicators,
    generate_scalper_major_signals,
    generate_scalper_major_report,
    progressive_lot_size,
    recovery_lot_sequence,
    resample_ohlcv_timeframes,
)
from strategies.ScalperMajorHighVolatility.research.walk_forward import (
    ScalperMajorWalkForwardConfig,
    run_scalper_major_walk_forward,
    split_walk_forward,
)


class ScalperMajorHighVolatilityTests(unittest.TestCase):
    def test_recovery_lot_sequence_uses_paired_martingale_pattern(self) -> None:
        self.assertEqual(recovery_lot_sequence(0.01, max_positions=6), [0.01, 0.01, 0.02, 0.02, 0.04, 0.04])

    def test_progressive_lot_size_matches_paper_equation(self) -> None:
        self.assertEqual(progressive_lot_size(999.0), 0.0)
        self.assertEqual(progressive_lot_size(1_000.0), 0.01)
        self.assertEqual(progressive_lot_size(2_500.0), 0.02)
        self.assertEqual(progressive_lot_size(10_000.0), 0.05)

    def test_generates_paper_style_long_and_short_signals(self) -> None:
        data = synthetic_ohlcv(periods=80)
        config = ScalperMajorConfig(min_sma_distance_atr=0.0, min_body_to_range=0.60, max_wick_to_range=0.25)

        signals = generate_scalper_major_signals(data, config)

        self.assertTrue(bool(signals["long_entry"].any()))
        self.assertTrue(bool(signals["short_entry"].any()))

    def test_talib_backend_is_used_when_available(self) -> None:
        data = synthetic_ohlcv(periods=80)
        config = ScalperMajorConfig(min_sma_distance_atr=0.0)

        class FakeTalib:
            @staticmethod
            def SMA(close, timeperiod):
                return pd.Series(close).rolling(timeperiod).mean().to_numpy()

            @staticmethod
            def RSI(close, timeperiod):
                return pd.Series([50.0] * len(close)).to_numpy()

            @staticmethod
            def ATR(high, low, close, timeperiod):
                return pd.Series(high - low).rolling(timeperiod).mean().to_numpy()

            @staticmethod
            def CDLMARUBOZU(open_, high, low, close):
                values = pd.Series([0] * len(close))
                values.iloc[30] = -100
                values.iloc[70] = 100
                return values.to_numpy()

        from strategies.ScalperMajorHighVolatility import core

        original = core._optional_talib
        core._optional_talib = lambda: FakeTalib()
        try:
            indicators = compute_scalper_major_indicators(data, config)
        finally:
            core._optional_talib = original

        self.assertEqual(indicators["indicator_backend"].iloc[-1], "ta-lib")
        self.assertTrue(bool(indicators["bearish_marubozu"].iloc[30]))
        self.assertTrue(bool(indicators["bullish_marubozu"].iloc[70]))

    def test_resamples_intraday_data_across_requested_timeframes(self) -> None:
        data = synthetic_ohlcv(periods=120, freq="min")

        frames = resample_ohlcv_timeframes(data, timeframes=("m1", "m5", "h1"))

        self.assertEqual(len(frames["m1"]), 120)
        self.assertEqual(len(frames["m5"]), 24)
        self.assertEqual(len(frames["h1"]), 2)
        self.assertIn("close", frames["m5"].columns)

    def test_backtest_returns_metrics_and_trade_table(self) -> None:
        data = synthetic_ohlcv(periods=120)
        config = ScalperMajorConfig(min_sma_distance_atr=0.0, min_body_to_range=0.60, max_wick_to_range=0.25, max_holding_bars=4)

        result = backtest_scalper_major(data, config)

        self.assertIn("sharpe_ratio", result.metrics)
        self.assertIn("profit_factor", result.metrics)
        self.assertEqual(len(result.equity), len(data))
        self.assertGreaterEqual(int(result.metrics["trade_count"] or 0), 1)

    def test_recovery_backtest_runs_basket_mode(self) -> None:
        data = synthetic_ohlcv(periods=160)
        strategy_config = ScalperMajorConfig(min_sma_distance_atr=0.0, min_body_to_range=0.60, max_wick_to_range=0.25)
        recovery_config = RecoveryConfig(max_positions_per_direction=4, grid_atr_multiple=0.5)

        result = backtest_scalper_major_recovery(data, strategy_config, recovery_config)

        self.assertEqual(result.metrics["mode"], "basket_recovery")
        self.assertIn("trade_count", result.metrics)
        self.assertEqual(len(result.equity), len(data))

    def test_scalper_major_report_exports_tables_without_charts(self) -> None:
        from tempfile import TemporaryDirectory

        data = synthetic_ohlcv(periods=120)
        config = ScalperMajorConfig(min_sma_distance_atr=0.0, min_body_to_range=0.60, max_wick_to_range=0.25, max_holding_bars=4)
        result = backtest_scalper_major(data, config)

        with TemporaryDirectory() as tmp:
            report = generate_scalper_major_report(result, output_dir=tmp, render_charts=False)

        self.assertIn("data", report.paths)
        self.assertIn("trades", report.paths)
        self.assertIn("metrics", report.paths)

    def test_walk_forward_splits_and_runs_oos_folds(self) -> None:
        data = synthetic_ohlcv(periods=180)
        walk_config = ScalperMajorWalkForwardConfig(train_size=80, test_size=30, step_size=30, embargo_size=2)
        strategy_config = ScalperMajorConfig(min_sma_distance_atr=0.0, min_body_to_range=0.60, max_wick_to_range=0.25)

        folds = split_walk_forward(data, walk_config)
        results, summary = run_scalper_major_walk_forward(data, walk_config=walk_config, strategy_config=strategy_config)

        self.assertGreaterEqual(len(folds), 2)
        self.assertEqual(summary["folds"], len(results))
        self.assertIn("oos_trades_total", summary)


def synthetic_ohlcv(periods: int = 120, freq: str = "h") -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=periods, freq=freq)
    closes = []
    price = 100.0
    for i in range(periods):
        if 20 <= i < 35:
            price -= 1.2
        elif 35 <= i < 50:
            price += 1.0
        elif 60 <= i < 75:
            price += 1.2
        elif 75 <= i < 90:
            price -= 1.0
        else:
            price += 0.05
        closes.append(price)
    frame = pd.DataFrame(index=index)
    frame["close"] = closes
    frame["open"] = frame["close"].shift(1).fillna(frame["close"].iloc[0])
    frame["high"] = frame[["open", "close"]].max(axis=1) + 0.20
    frame["low"] = frame[["open", "close"]].min(axis=1) - 0.20
    frame["volume"] = 1_000.0

    # Force clean bearish and bullish Marubozu candles during RSI extremes.
    for bar in (30, 31, 32):
        frame.iloc[bar, frame.columns.get_loc("open")] = frame["close"].iloc[bar] + 1.0
        frame.iloc[bar, frame.columns.get_loc("high")] = frame["open"].iloc[bar] + 0.05
        frame.iloc[bar, frame.columns.get_loc("low")] = frame["close"].iloc[bar] - 0.05
    for bar in (70, 71, 72):
        frame.iloc[bar, frame.columns.get_loc("open")] = frame["close"].iloc[bar] - 1.0
        frame.iloc[bar, frame.columns.get_loc("high")] = frame["close"].iloc[bar] + 0.05
        frame.iloc[bar, frame.columns.get_loc("low")] = frame["open"].iloc[bar] - 0.05
    return frame[["open", "high", "low", "close", "volume"]]


if __name__ == "__main__":
    unittest.main()
