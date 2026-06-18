import tempfile
import unittest
import importlib.util
from pathlib import Path

import pandas as pd

from strategies.RisingAssest import (
    RisingAssetsConfig,
    backtest_rising_assets,
    compute_momentum_scores,
    generate_live_rebalance_orders,
    load_price_csv,
    load_price_universe,
    validate_live_readiness,
)
from strategies.RisingAssest.backtesting import prepare_rising_assets_signals, run_rising_assets_vectorbt
from strategies.RisingAssest.reporting import generate_rising_assets_report

HAS_VECTORBT = importlib.util.find_spec("vectorbt") is not None


class RisingAssetsStrategyTests(unittest.TestCase):
    def test_momentum_score_averages_trailing_returns(self) -> None:
        prices = pd.DataFrame(
            {"AAA": [100.0, 110.0, 121.0, 133.1]},
            index=pd.date_range("2024-01-01", periods=4, freq="D"),
        )

        momentum = compute_momentum_scores(prices, lookbacks=(1, 2))

        expected = ((133.1 / 121.0 - 1.0) + (133.1 / 110.0 - 1.0)) / 2.0
        self.assertAlmostEqual(float(momentum["AAA"].iloc[-1]), expected)

    def test_monthly_weights_select_top_assets_and_sum_to_one(self) -> None:
        prices = _sample_prices()
        config = RisingAssetsConfig(momentum_lookbacks=(5, 10), volatility_window=5, top_n=3, min_history=10)

        prepared = prepare_rising_assets_signals(prices, config=config)
        last_weights = prepared.target_weights.iloc[-1]

        self.assertEqual(int((last_weights > 0).sum()), 3)
        self.assertAlmostEqual(float(last_weights.sum()), 1.0)
        self.assertEqual(prepared.execution_weights.iloc[0].sum(), 0.0)
        self.assertLessEqual(float(prepared.target_weights.sum(axis=1).max()), 1.0000001)

    def test_backtest_returns_equity_trades_and_metrics(self) -> None:
        result = backtest_rising_assets(
            _sample_prices(),
            RisingAssetsConfig(momentum_lookbacks=(5, 10), volatility_window=5, top_n=3, min_history=10),
        )

        self.assertEqual(len(result.equity), len(result.prices))
        self.assertIn("total_return", result.metrics)
        self.assertIn("sharpe_ratio", result.metrics)
        self.assertFalse(result.trades.empty)
        self.assertTrue((result.weights.iloc[0] == 0.0).all())

    def test_report_exports_portfolio_artifacts_without_charts(self) -> None:
        result = backtest_rising_assets(
            _sample_prices(),
            RisingAssetsConfig(momentum_lookbacks=(5, 10), volatility_window=5, top_n=3, min_history=10),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_rising_assets_report(result, output_dir=Path(tmpdir), render_charts=False)

            self.assertTrue(report.paths["data"].exists())
            self.assertTrue(report.paths["trades"].exists())
            self.assertTrue(report.paths["target_weights"].exists())
            self.assertTrue(report.paths["momentum"].exists())

    def test_report_exports_rising_assets_visualizations(self) -> None:
        result = backtest_rising_assets(
            _sample_prices(),
            RisingAssetsConfig(momentum_lookbacks=(5, 10), volatility_window=5, top_n=3, min_history=10),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_rising_assets_report(result, output_dir=Path(tmpdir), render_charts=True)

            self.assertTrue(report.paths["allocation_chart"].exists())
            self.assertTrue(report.paths["asset_growth_chart"].exists())
            self.assertTrue(report.paths["return_distribution"].exists())
            self.assertTrue(report.paths["asset_correlation"].exists())

    def test_loads_updated_stock_csv_shapes(self) -> None:
        prices = load_price_universe(
            {
                "SPY": "datasets/SPY/SPYdata.csv",
                "QQQ": "datasets/QQQ/Invesco QQQ 5  Years price Data.csv",
            }
        )

        self.assertEqual(prices.columns.tolist(), ["SPY", "QQQ"])
        self.assertGreater(len(prices), 250)
        self.assertTrue(prices.index.is_monotonic_increasing)
        self.assertGreater(float(prices["SPY"].iloc[-1]), 0.0)
        self.assertGreater(float(prices["QQQ"].iloc[-1]), 0.0)

    def test_single_price_csv_infers_symbol_from_simple_two_column_file(self) -> None:
        series = load_price_csv("datasets/SPY/SPYdata.csv")

        self.assertEqual(series.name, "SPY")
        self.assertTrue(series.index.is_monotonic_increasing)

    def test_live_readiness_reports_missing_full_universe_and_symbol_map(self) -> None:
        prices = load_price_universe(
            {
                "SPY": "datasets/SPY/SPYdata.csv",
                "QQQ": "datasets/QQQ/Invesco QQQ 5  Years price Data.csv",
            }
        )

        readiness = validate_live_readiness(prices, broker_symbol_map={"SPY": "SPY", "QQQ": "QQQ"})

        self.assertFalse(readiness["ready"])
        self.assertIn("missing_data", readiness)
        self.assertIn("AGG", readiness["missing_data"])
        self.assertIn("AGG", readiness["missing_broker_symbols"])

    def test_generates_broker_agnostic_rebalance_orders(self) -> None:
        orders = generate_live_rebalance_orders(
            current_weights=pd.Series({"SPY": 0.25, "QQQ": 0.75}),
            target_weights=pd.Series({"SPY": 0.60, "QQQ": 0.40}),
            portfolio_value=10_000.0,
            prices=pd.Series({"SPY": 500.0, "QQQ": 400.0}),
            min_weight_change=0.01,
        )

        self.assertEqual(orders["action"].tolist(), ["BUY", "SELL"])
        self.assertAlmostEqual(float(orders.loc[orders["symbol"] == "SPY", "target_value_delta"].iloc[0]), 3500.0)

    @unittest.skipUnless(HAS_VECTORBT, "vectorbt is not installed")
    def test_vectorbt_adapter_runs_on_updated_stock_data(self) -> None:
        prices = load_price_universe(
            {
                "SPY": "datasets/SPY/SPYdata.csv",
                "QQQ": "datasets/QQQ/Invesco QQQ 5  Years price Data.csv",
            }
        )
        result = run_rising_assets_vectorbt(
            prices,
            strategy_config=RisingAssetsConfig(top_n=5, trading_cost=0.0005),
        )

        self.assertEqual(len(result.equity), len(prices))
        self.assertIn("total_return", result.metrics)
        self.assertFalse(result.target_orders.dropna(how="all").empty)
        self.assertLessEqual(float(result.pandas_result.target_weights.sum(axis=1).max()), 1.0000001)


def _sample_prices() -> pd.DataFrame:
    index = pd.bdate_range("2023-01-02", periods=90)
    drifts = {
        "AAA": 0.0018,
        "BBB": 0.0012,
        "CCC": 0.0008,
        "DDD": 0.0002,
        "EEE": -0.0001,
        "FFF": -0.0004,
    }
    rows = {}
    for offset, (symbol, drift) in enumerate(drifts.items()):
        values = []
        price = 100.0 + offset
        for i, _ in enumerate(index):
            noise = 0.001 * ((i + offset) % 3 - 1)
            price *= 1.0 + drift + noise
            values.append(price)
        rows[symbol] = values
    return pd.DataFrame(rows, index=index)


if __name__ == "__main__":
    unittest.main()
