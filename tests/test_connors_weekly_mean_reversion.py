import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from strategies.ConnorsResearchWeeklyMeanReversion import (
    ConnorsWeeklyMeanReversionConfig,
    backtest_connors_weekly_mean_reversion,
    compute_asset_performance,
    compute_average_dollar_volume,
    compute_regime_filter,
    compute_weekly_rsi,
    generate_connors_target_weights,
    generate_live_rebalance_orders,
    load_connors_ohlcv_universe,
    validate_live_readiness,
)
from strategies.ConnorsResearchWeeklyMeanReversion.backtesting import run_connors_vectorbt
from strategies.ConnorsResearchWeeklyMeanReversion.research import ConnorsWalkForwardConfig, run_connors_walk_forward
from strategies.ConnorsResearchWeeklyMeanReversion.reporting import generate_connors_report

HAS_VECTORBT = importlib.util.find_spec("vectorbt") is not None
RUN_VECTORBT_TESTS = os.getenv("RUN_VECTORBT_TESTS") == "1"


class ConnorsWeeklyMeanReversionTests(unittest.TestCase):
    def test_indicators_compute_rsi_regime_and_liquidity(self) -> None:
        prices, volumes = _sample_connors_data()
        config = _fast_config()

        rsi = compute_weekly_rsi(prices, period=config.weekly_rsi_period)
        regime = compute_regime_filter(prices, regime_symbol="SPY", lookback=config.regime_lookback)
        dollar_volume = compute_average_dollar_volume(prices, volumes, lookback=config.liquidity_lookback)

        self.assertEqual(rsi.shape, prices.shape)
        self.assertTrue(regime.iloc[-1])
        self.assertGreater(float(dollar_volume["AAA"].dropna().iloc[-1]), 0.0)

    def test_target_weights_enter_stocks_and_allocate_idle_to_shy(self) -> None:
        prices, volumes = _sample_connors_data()
        config = _fast_config(max_positions=2)

        target_weights, trades = generate_connors_target_weights(prices, volumes, config)

        self.assertFalse(trades.empty)
        self.assertIn("BUY", trades["action"].tolist())
        self.assertLessEqual(float(target_weights.drop(columns=["SHY"]).sum(axis=1).max()), 1.0)
        self.assertAlmostEqual(float(target_weights.sum(axis=1).max()), 1.0)
        self.assertTrue((target_weights["SHY"] >= 0.0).all())

    def test_daily_stop_loss_exits_position(self) -> None:
        prices, volumes = _sample_connors_data(with_stop=True)
        config = _fast_config(max_positions=1)

        _, trades = generate_connors_target_weights(prices, volumes, config)

        self.assertIn("daily_stop_loss", trades["reason"].tolist())
        stop_trade = trades.loc[trades["reason"] == "daily_stop_loss"].iloc[0]
        self.assertEqual(stop_trade["action"], "SELL")

    def test_backtest_returns_equity_trades_and_metrics(self) -> None:
        prices, volumes = _sample_connors_data()
        result = backtest_connors_weekly_mean_reversion(prices, volumes, _fast_config(max_positions=2))

        self.assertEqual(len(result.equity), len(prices))
        self.assertIn("total_return", result.metrics)
        self.assertIn("sharpe_ratio", result.metrics)
        self.assertFalse(result.trades.empty)
        self.assertTrue((result.weights.iloc[0] == 0.0).all())

    def test_asset_performance_reports_symbol_contribution(self) -> None:
        prices, volumes = _sample_connors_data()
        result = backtest_connors_weekly_mean_reversion(prices, volumes, _fast_config(max_positions=2))

        asset_performance = compute_asset_performance(result)

        self.assertIn("symbol", asset_performance.columns)
        self.assertIn("contribution_sharpe", asset_performance.columns)
        self.assertIn("contribution_max_drawdown", asset_performance.columns)
        self.assertGreaterEqual(set(asset_performance["symbol"]), set(prices.columns))

    def test_walk_forward_returns_oos_fold_and_asset_metrics(self) -> None:
        prices, volumes = _sample_connors_data(periods=180)

        folds, assets, summary = run_connors_walk_forward(
            prices,
            volumes,
            walk_config=ConnorsWalkForwardConfig(train_size=80, test_size=30, step_size=30, embargo_size=2),
            strategy_config=_fast_config(max_positions=2),
        )

        self.assertFalse(folds.empty)
        self.assertFalse(assets.empty)
        self.assertIn("test_sharpe_ratio", folds.columns)
        self.assertIn("oos_max_drawdown_worst", summary)
        self.assertEqual(summary["folds"], len(folds))

    def test_generates_broker_agnostic_rebalance_orders(self) -> None:
        orders = generate_live_rebalance_orders(
            current_weights=pd.Series({"AAA": 0.0, "SHY": 1.0}),
            target_weights=pd.Series({"AAA": 0.5, "SHY": 0.5}),
            portfolio_value=10_000.0,
            prices=pd.Series({"AAA": 100.0, "SHY": 80.0}),
            min_weight_change=0.01,
        )

        self.assertEqual(orders["action"].tolist(), ["BUY", "SELL"])
        self.assertAlmostEqual(float(orders.loc[orders["symbol"] == "AAA", "target_value_delta"].iloc[0]), 5000.0)

    def test_report_exports_connors_artifacts_without_charts(self) -> None:
        prices, volumes = _sample_connors_data()
        result = backtest_connors_weekly_mean_reversion(prices, volumes, _fast_config(max_positions=2))
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_connors_report(result, output_dir=Path(tmpdir), render_charts=False)

            self.assertTrue(report.paths["data"].exists())
            self.assertTrue(report.paths["trades"].exists())
            self.assertTrue(report.paths["target_weights"].exists())
            self.assertTrue(report.paths["weekly_rsi"].exists())
            self.assertTrue(report.paths["regime"].exists())

    def test_loads_local_yfinance_stock_universe(self) -> None:
        required = {
            "AAPL": Path("datasets/AAPL/AAPL_1d_yfinance.csv"),
            "MSFT": Path("datasets/MSFT/MSFT_1d_yfinance.csv"),
            "NVDA": Path("datasets/NVDA/NVDA_1d_yfinance.csv"),
            "SPY": Path("datasets/SPY/SPY_1d_yfinance.csv"),
            "SHY": Path("datasets/SHY/SHY_1d_yfinance.csv"),
        }
        if not all(path.exists() for path in required.values()):
            self.skipTest("local yfinance datasets are not present")

        prices, volumes = load_connors_ohlcv_universe(required)
        readiness = validate_live_readiness(
            prices,
            volumes,
            ConnorsWeeklyMeanReversionConfig(
                live_required_symbols=tuple(required),
            ),
            broker_symbol_map={symbol: symbol for symbol in required},
        )

        self.assertEqual(prices.columns.tolist(), list(required))
        self.assertGreater(len(prices), 500)
        self.assertTrue(readiness["ready"])

    @unittest.skipUnless(HAS_VECTORBT and RUN_VECTORBT_TESTS, "set RUN_VECTORBT_TESTS=1 to run optional vectorbt test")
    def test_vectorbt_adapter_runs_on_sample_data(self) -> None:
        prices, volumes = _sample_connors_data()
        result = run_connors_vectorbt(prices, volumes, strategy_config=_fast_config(max_positions=2))

        self.assertEqual(len(result.equity), len(prices))
        self.assertIn("total_return", result.metrics)
        self.assertFalse(result.target_orders.dropna(how="all").empty)


def _fast_config(max_positions: int = 2) -> ConnorsWeeklyMeanReversionConfig:
    return ConnorsWeeklyMeanReversionConfig(
        regime_lookback=10,
        volatility_lookback=5,
        liquidity_lookback=5,
        liquid_universe_size=3,
        max_positions=max_positions,
        trading_cost=0.0005,
        live_required_symbols=("AAA", "BBB", "SPY", "SHY"),
    )


def _sample_connors_data(*, with_stop: bool = False, periods: int = 80) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.bdate_range("2024-01-01", periods=periods)
    spy = [100.0 + i * 0.25 for i in range(len(index))]
    shy = [80.0 + i * 0.01 for i in range(len(index))]
    aaa = [100.0 + i * 0.15 for i in range(len(index))]
    bbb = [95.0 + i * 0.08 for i in range(len(index))]

    for i in range(32, 42):
        aaa[i] -= (i - 31) * 2.2
        bbb[i] -= (i - 31) * 1.4
    for i in range(42, len(index)):
        aaa[i] = aaa[41] + (i - 41) * 1.8
        bbb[i] = bbb[41] + (i - 41) * 1.2

    if with_stop:
        for i in range(43, len(index)):
            aaa[i] = min(aaa[i], aaa[42] * 0.80)
            bbb[i] = min(bbb[i], bbb[42] * 0.80)

    prices = pd.DataFrame({"AAA": aaa, "BBB": bbb, "SPY": spy, "SHY": shy}, index=index)
    volumes = pd.DataFrame(
        {
            "AAA": [2_000_000.0] * len(index),
            "BBB": [1_500_000.0] * len(index),
            "SPY": [10_000_000.0] * len(index),
            "SHY": [1_000_000.0] * len(index),
        },
        index=index,
    )
    return prices, volumes


if __name__ == "__main__":
    unittest.main()
