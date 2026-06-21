import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from strategies.ConnorsResearchDynamicTreasuries import (
    DynamicTreasuriesConfig,
    backtest_dynamic_treasuries,
    build_rebalance_events,
    compute_duration_exposure,
    compute_positive_signal_counts,
    generate_dynamic_treasuries_target_weights,
    generate_live_rebalance_orders,
    load_dynamic_treasuries_prices,
    validate_live_readiness,
    summarize_rebalances,
)
from strategies.ConnorsResearchDynamicTreasuries.backtesting import run_dynamic_treasuries_vectorbt
from strategies.ConnorsResearchDynamicTreasuries.reporting import generate_dynamic_treasuries_report
from strategies.ConnorsResearchDynamicTreasuries.research import (
    DynamicTreasuriesWalkForwardConfig,
    run_dynamic_treasuries_walk_forward,
)

HAS_VECTORBT = importlib.util.find_spec("vectorbt") is not None
RUN_VECTORBT_TESTS = os.getenv("RUN_VECTORBT_TESTS") == "1"


class DynamicTreasuriesTests(unittest.TestCase):
    def test_counts_positive_momentum_lookbacks(self) -> None:
        prices = _sample_treasury_prices()
        config = _fast_config()

        counts = compute_positive_signal_counts(prices, config)

        self.assertEqual(counts.columns.tolist(), ["IEF", "TLH", "TLT"])
        self.assertGreaterEqual(int(counts["IEF"].iloc[-1]), 0)
        self.assertLessEqual(int(counts["TLT"].iloc[-1]), len(config.momentum_lookbacks))

    def test_weekly_weights_allocate_residual_to_iei(self) -> None:
        prices = _sample_treasury_prices()
        config = _fast_config()

        target, trades = generate_dynamic_treasuries_target_weights(prices, config)

        self.assertAlmostEqual(float(target.sum(axis=1).iloc[-1]), 1.0)
        self.assertTrue((target["IEI"] >= 0.25).all())
        self.assertFalse(trades.empty)

    def test_backtest_returns_metrics_duration_and_asset_performance(self) -> None:
        prices = _sample_treasury_prices()
        result = backtest_dynamic_treasuries(prices, _fast_config())

        self.assertEqual(len(result.equity), len(prices))
        self.assertIn("sharpe_ratio", result.metrics)
        self.assertIn("rebalance_count", result.metrics)
        self.assertFalse(result.asset_performance.empty)
        self.assertGreater(float(result.duration_exposure.max()), 0.0)

    def test_rebalance_events_report_turnover_and_duration_changes(self) -> None:
        result = backtest_dynamic_treasuries(_sample_treasury_prices(), _fast_config())

        events = build_rebalance_events(result)
        summary = summarize_rebalances(events)

        self.assertFalse(events.empty)
        self.assertIn("turnover", events.columns)
        self.assertIn("duration_before", events.columns)
        self.assertIn("duration_after", events.columns)
        self.assertGreater(int(summary["rebalances"].iloc[0]), 0)

    def test_duration_exposure_uses_weighted_durations(self) -> None:
        weights = pd.DataFrame(
            {"IEI": [1.0, 0.25], "IEF": [0.0, 0.25], "TLH": [0.0, 0.25], "TLT": [0.0, 0.25]},
            index=pd.date_range("2024-01-01", periods=2),
        )

        duration = compute_duration_exposure(weights)

        self.assertAlmostEqual(float(duration.iloc[0]), 4.5)
        self.assertAlmostEqual(float(duration.iloc[1]), (4.5 + 7.5 + 11.5 + 17.4) / 4)

    def test_generates_broker_agnostic_rebalance_orders(self) -> None:
        orders = generate_live_rebalance_orders(
            current_weights=pd.Series({"IEI": 1.0, "IEF": 0.0}),
            target_weights=pd.Series({"IEI": 0.75, "IEF": 0.25}),
            portfolio_value=10_000.0,
            prices=pd.Series({"IEI": 115.0, "IEF": 95.0}),
            min_weight_change=0.01,
        )

        self.assertEqual(orders["action"].tolist(), ["SELL", "BUY"])
        self.assertAlmostEqual(float(orders.loc[orders["symbol"] == "IEF", "target_value_delta"].iloc[0]), 2500.0)

    def test_report_exports_dynamic_treasury_artifacts_without_charts(self) -> None:
        result = backtest_dynamic_treasuries(_sample_treasury_prices(), _fast_config())
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_dynamic_treasuries_report(result, output_dir=Path(tmpdir), render_charts=False)

            self.assertTrue(report.paths["data"].exists())
            self.assertTrue(report.paths["target_weights"].exists())
            self.assertTrue(report.paths["duration_exposure"].exists())
            self.assertTrue(report.paths["asset_performance"].exists())
            self.assertTrue(report.paths["rebalance_events"].exists())
            self.assertTrue(report.paths["rebalance_summary"].exists())

    def test_walk_forward_returns_oos_fold_metrics(self) -> None:
        prices = _sample_treasury_prices(periods=180)

        folds, assets, summary = run_dynamic_treasuries_walk_forward(
            prices,
            walk_config=DynamicTreasuriesWalkForwardConfig(train_size=80, test_size=30, step_size=30, embargo_size=2),
            strategy_config=_fast_config(),
        )

        self.assertFalse(folds.empty)
        self.assertFalse(assets.empty)
        self.assertIn("test_sharpe_ratio", folds.columns)
        self.assertIn("mean_oos_duration", summary)

    def test_loads_local_treasury_yfinance_files_when_present(self) -> None:
        required = {
            "IEI": Path("datasets/IEI/IEI_1d_yfinance.csv"),
            "IEF": Path("datasets/IEF/IEF_1d_yfinance.csv"),
            "TLH": Path("datasets/TLH/TLH_1d_yfinance.csv"),
            "TLT": Path("datasets/TLT/TLT_1d_yfinance.csv"),
        }
        if not all(path.exists() for path in required.values()):
            self.skipTest("local Dynamic Treasuries yfinance datasets are not present")

        prices = load_dynamic_treasuries_prices(required)
        readiness = validate_live_readiness(
            prices,
            DynamicTreasuriesConfig(),
            broker_symbol_map={symbol: symbol for symbol in required},
        )

        self.assertEqual(prices.columns.tolist(), list(required))
        self.assertGreater(len(prices), 500)
        self.assertTrue(readiness["ready"])

    @unittest.skipUnless(HAS_VECTORBT and RUN_VECTORBT_TESTS, "set RUN_VECTORBT_TESTS=1 to run optional vectorbt test")
    def test_vectorbt_adapter_runs_on_sample_data(self) -> None:
        result = run_dynamic_treasuries_vectorbt(_sample_treasury_prices(), strategy_config=_fast_config())

        self.assertEqual(len(result.equity), len(result.pandas_result.prices))
        self.assertIn("total_return", result.metrics)
        self.assertFalse(result.target_orders.dropna(how="all").empty)


def _fast_config() -> DynamicTreasuriesConfig:
    return DynamicTreasuriesConfig(
        momentum_lookbacks=(5, 10, 15, 20, 25),
        initial_cash=10_000.0,
        trading_cost=0.0005,
    )


def _sample_treasury_prices(*, periods: int = 120) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-01", periods=periods)
    rows = {}
    specs = {
        "IEI": (100.0, 0.00008),
        "IEF": (100.0, 0.00015),
        "TLH": (100.0, 0.0002),
        "TLT": (100.0, 0.00024),
    }
    for offset, (symbol, (start, drift)) in enumerate(specs.items()):
        price = start + offset
        values = []
        for i, _ in enumerate(index):
            cycle = 0.0015 * ((i + offset) % 11 - 5) / 5.0
            if 45 <= i <= 65:
                cycle -= 0.002 * (offset + 1)
            if i > 70:
                cycle += 0.0015 * (offset + 1)
            price *= 1.0 + drift + cycle
            values.append(price)
        rows[symbol] = values
    return pd.DataFrame(rows, index=index)


if __name__ == "__main__":
    unittest.main()
