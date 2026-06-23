import unittest
from io import StringIO
from typing import get_args

import pandas as pd

from strategies.DirectionalForexML import (
    DirectionalForexMLConfig,
    DirectionalForexMLWalkForwardConfig,
    ModelName,
    USD_BASE_TO_PAPER_SYMBOL,
    apply_ml_probability_gate,
    backtest_directional_forex_ml,
    bootstrap_confidence_interval,
    build_ml_gate_for_signals,
    build_directional_labels,
    compute_directional_features,
    cost_spec_for_symbol,
    invert_usd_base_quote,
    load_treasury_macro_csv,
    madl_score,
    paired_return_tests,
    run_cost_sensitivity,
    run_regime_period_validation,
    run_var_backtests,
    run_directional_forex_ml_walk_forward,
    train_directional_forex_model,
)
from strategies.ScalperMajorHighVolatility import (
    ScalperMajorConfig,
    generate_scalper_major_ml_filtered_signals,
)


class DirectionalForexMLTests(unittest.TestCase):
    def test_feature_and_label_alignment_uses_future_close_vs_current_open(self) -> None:
        data = synthetic_fx_ohlcv(80)

        features = compute_directional_features(data)
        labels, forward_returns = build_directional_labels(data, horizon=1)

        self.assertIn("daily_return", features.columns)
        self.assertIn("high_low_range", features.columns)
        self.assertIn("opening_gap", features.columns)
        self.assertTrue(pd.isna(features["daily_return"].iloc[1]))
        self.assertFalse(pd.isna(features["opening_gap"].iloc[1]))
        expected = int(data["close"].iloc[1] > data["open"].iloc[0])
        self.assertEqual(int(labels.iloc[0]), expected)
        self.assertAlmostEqual(float(forward_returns.iloc[0]), data["close"].iloc[1] / data["open"].iloc[0] - 1.0)

    def test_paper_feature_set_is_exact_three_feature_baseline(self) -> None:
        data = synthetic_fx_ohlcv(80)

        features = compute_directional_features(data, feature_set="paper_technical")
        extended = compute_directional_features(data, feature_set="extended")

        self.assertEqual(list(features.columns), ["daily_return", "high_low_range", "opening_gap"])
        self.assertIn("rolling_vol_20", extended.columns)

    def test_xgboost_is_declared_as_paper_model_option(self) -> None:
        self.assertIn("xgboost", get_args(ModelName))

    def test_dynamic_cost_matches_paper_formula(self) -> None:
        cost = cost_spec_for_symbol("EURUSD")

        self.assertAlmostEqual(cost.one_way_pct(1.2), (1.2 * 0.0001) / 1.2)
        self.assertAlmostEqual(cost.round_trip_pct(1.2), 2.0 * (1.2 * 0.0001) / 1.2)
        self.assertEqual(USD_BASE_TO_PAPER_SYMBOL["USDCHF"], "CHFUSD")

    def test_invert_usd_base_quote_preserves_ohlc_constraints(self) -> None:
        data = synthetic_fx_ohlcv(20) * 100.0
        data["volume"] = 1_000.0

        inverted = invert_usd_base_quote(data)

        self.assertTrue((inverted["high"] >= inverted["low"]).all())
        self.assertAlmostEqual(float(inverted["open"].iloc[0]), 1.0 / float(data["open"].iloc[0]))
        self.assertAlmostEqual(float(inverted["high"].iloc[0]), 1.0 / float(data["low"].iloc[0]))

    def test_madl_rewards_profitable_directional_predictions(self) -> None:
        returns = pd.Series([0.01, -0.02, 0.03])
        y_true = pd.Series([1, 0, 1])

        good = madl_score(y_true, [1, 0, 1], returns)
        bad = madl_score(y_true, [0, 1, 0], returns)

        self.assertGreater(good, bad)

    def test_probability_gate_filters_base_entries_by_side_and_cost(self) -> None:
        index = pd.date_range("2024-01-01", periods=3, freq="D")
        gate = apply_ml_probability_gate(
            pd.Series([True, True, False], index=index),
            pd.Series([False, False, True], index=index),
            pd.Series([0.60, 0.51, 0.35], index=index),
            pd.Series([0.003, 0.003, 0.003], index=index),
            pd.Series([0.001, 0.001, 0.001], index=index),
            threshold=0.55,
        )

        self.assertTrue(bool(gate["ml_long_approved"].iloc[0]))
        self.assertFalse(bool(gate["ml_long_approved"].iloc[1]))
        self.assertTrue(bool(gate["ml_short_approved"].iloc[2]))

    def test_backtest_trains_logistic_madl_and_returns_metrics(self) -> None:
        data = synthetic_fx_ohlcv(180)
        config = DirectionalForexMLConfig(probability_threshold=0.50, expected_move_window=5, cv_splits=3)

        result = backtest_directional_forex_ml(data, symbol="EURUSD", config=config)

        self.assertIn("sharpe_ratio", result.metrics)
        self.assertIn("total_return", result.metrics)
        self.assertEqual(result.artifact.model_name, "logistic_madl")
        self.assertEqual(len(result.equity), len(result.returns))

    def test_build_ml_gate_for_base_signal_table(self) -> None:
        data = synthetic_fx_ohlcv(180)
        config = DirectionalForexMLConfig(probability_threshold=0.50, expected_move_window=5, cv_splits=3)
        artifact = train_directional_forex_model(data.iloc[:120], symbol="EURUSD", config=config)
        base_signals = pd.DataFrame(False, index=data.index, columns=["long_entry", "short_entry"])
        base_signals.iloc[130, base_signals.columns.get_loc("long_entry")] = True

        gate = build_ml_gate_for_signals(data, base_signals, artifact, threshold=0.50)

        self.assertIn("ml_long_approved", gate.columns)
        self.assertIn("ml_probability_up", gate.columns)
        self.assertEqual(len(gate), len(data))

    def test_walk_forward_runs_multiple_oos_folds(self) -> None:
        data = synthetic_fx_ohlcv(220)
        config = DirectionalForexMLConfig(probability_threshold=0.50, expected_move_window=5, cv_splits=3)
        walk_config = DirectionalForexMLWalkForwardConfig(train_size=100, test_size=40, step_size=40)

        folds, summary = run_directional_forex_ml_walk_forward(
            data,
            symbol="EURUSD",
            walk_config=walk_config,
            strategy_config=config,
        )

        self.assertGreaterEqual(len(folds), 1)
        self.assertEqual(summary["folds"], len(folds))
        self.assertIn("oos_trades_total", summary)

    def test_macro_loader_creates_paper_treasury_features(self) -> None:
        macro = load_treasury_macro_csv(
            StringIO(
                "date,rate_5y,rate_13w\n"
                "2020-01-01,1.5,1.2\n"
                "2020-01-02,1.6,1.1\n"
            )
        )

        self.assertIn("rate_5y", macro.columns)
        self.assertIn("yield_slope", macro.columns)
        self.assertAlmostEqual(float(macro["yield_slope"].iloc[0]), 0.3)

    def test_regime_and_cost_sensitivity_helpers_return_tables(self) -> None:
        data = synthetic_fx_ohlcv(320)
        config = DirectionalForexMLConfig(
            probability_threshold=0.50,
            expected_move_window=5,
            cv_splits=3,
            enable_hyperparameter_search=False,
        )

        regimes = run_regime_period_validation(
            data,
            symbol="EURUSD",
            config=config,
            periods={"sample": ("2020-01-01", "2020-12-31")},
        )
        sensitivity = run_cost_sensitivity(data, symbol="EURUSD", config=config, multipliers=(0.5, 1.0))

        self.assertEqual(len(regimes), 1)
        self.assertEqual(len(sensitivity), 2)
        self.assertIn("cost_multiplier", sensitivity.columns)

    def test_statistical_and_var_backtests_return_diagnostics(self) -> None:
        index = pd.date_range("2020-01-01", periods=320, freq="D", tz="UTC")
        returns = pd.Series([0.001, -0.002, 0.003, -0.001] * 80, index=index)
        benchmark = pd.Series([0.0] * len(returns), index=index)

        tests = paired_return_tests(returns, benchmark)
        ci = bootstrap_confidence_interval(returns, samples=50)
        var = run_var_backtests(returns, window=50)

        self.assertIn("paired_t", tests)
        self.assertIsNotNone(ci[0])
        self.assertEqual(set(var["var_model"]), {"historical", "parametric", "ewma"})

    def test_scalper_major_can_use_directional_ml_gate(self) -> None:
        data = synthetic_fx_ohlcv(180)
        config = DirectionalForexMLConfig(probability_threshold=0.50, expected_move_window=5, cv_splits=3)
        artifact = train_directional_forex_model(data.iloc[:120], symbol="EURUSD", config=config)

        signals = generate_scalper_major_ml_filtered_signals(
            data,
            artifact,
            ScalperMajorConfig(min_sma_distance_atr=0.0, min_body_to_range=0.50, max_wick_to_range=0.50),
            threshold=0.50,
        )

        self.assertIn("base_long_entry", signals.columns)
        self.assertIn("ml_probability_up", signals.columns)


def synthetic_fx_ohlcv(periods: int = 160) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=periods, freq="D", tz="UTC")
    price = 1.10
    closes = []
    for i in range(periods):
        seasonal = 0.001 if (i // 5) % 2 == 0 else -0.0008
        price = max(0.8, price + seasonal + (0.0002 if i % 7 == 0 else 0.0))
        closes.append(price)
    frame = pd.DataFrame(index=index)
    frame["close"] = closes
    frame["open"] = frame["close"].shift(1).fillna(frame["close"].iloc[0]) * 0.9998
    frame["high"] = frame[["open", "close"]].max(axis=1) + 0.001
    frame["low"] = frame[["open", "close"]].min(axis=1) - 0.001
    frame["volume"] = 1_000.0
    return frame[["open", "high", "low", "close", "volume"]]


if __name__ == "__main__":
    unittest.main()
