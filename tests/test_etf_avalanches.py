import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from strategies.ETFAvalanches import (
    ETFAvalanchesConfig,
    backtest_etf_avalanches,
    compute_historical_volatility,
    compute_rsi,
    compute_trailing_returns,
    generate_etf_avalanche_target_weights,
    generate_live_short_orders,
    load_etf_avalanche_ohlcv,
    validate_live_readiness,
)
from strategies.ETFAvalanches.backtesting import run_etf_avalanches_vectorbt
from strategies.ETFAvalanches.reporting import generate_etf_avalanches_report
from strategies.ETFAvalanches.research import (
    ETFAvalanchesWalkForwardConfig,
    run_etf_avalanches_walk_forward,
)

HAS_VECTORBT = importlib.util.find_spec("vectorbt") is not None
RUN_VECTORBT_TESTS = os.getenv("RUN_VECTORBT_TESTS") == "1"


class ETFAvalanchesTests(unittest.TestCase):
    def test_indicators_compute_rsi_returns_and_volatility(self) -> None:
        prices, _ = _sample_avalanche_prices()

        rsi = compute_rsi(prices, period=2)
        returns = compute_trailing_returns(prices, lookback=21)
        volatility = compute_historical_volatility(prices, lookback=20)

        self.assertEqual(rsi.columns.tolist(), prices.columns.tolist())
        self.assertFalse(returns.dropna(how="all").empty)
        self.assertFalse(volatility.dropna(how="all").empty)

    def test_generates_short_entries_from_bear_rally_limit_fills(self) -> None:
        prices, highs = _sample_avalanche_prices()
        config = _fast_config()

        target, trades, candidates = generate_etf_avalanche_target_weights(prices, highs, config)

        self.assertEqual(target.columns.tolist(), prices.columns.tolist())
        self.assertFalse(candidates.empty)
        self.assertTrue((target.drop(columns=["SHY"]).min().min() <= 0.0))
        self.assertIn("ENTER_SHORT", trades["action"].tolist())

    def test_backtest_returns_short_metrics_and_closed_trades(self) -> None:
        prices, highs = _sample_avalanche_prices()
        result = backtest_etf_avalanches(prices, highs, _fast_config())

        self.assertEqual(len(result.equity), len(prices))
        self.assertIn("profit_factor", result.metrics)
        self.assertFalse(result.closed_trades.empty)
        self.assertFalse(result.asset_performance.empty)

    def test_generates_broker_agnostic_short_orders(self) -> None:
        orders = generate_live_short_orders(
            current_weights=pd.Series({"SPY": 0.0, "SHY": 1.0}),
            target_weights=pd.Series({"SPY": -0.2, "SHY": 0.8}),
            portfolio_value=10_000.0,
            prices=pd.Series({"SPY": 500.0, "SHY": 82.0}),
        )

        self.assertIn("SELL_SHORT", orders["action"].tolist())
        self.assertIn("SELL", orders["action"].tolist())

    def test_report_exports_avalanche_artifacts_without_charts(self) -> None:
        result = backtest_etf_avalanches(*_sample_avalanche_prices(), config=_fast_config())
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_etf_avalanches_report(result, output_dir=Path(tmpdir), render_charts=False)

            self.assertTrue(report.paths["data"].exists())
            self.assertTrue(report.paths["closed_trades"].exists())
            self.assertTrue(report.paths["target_weights"].exists())
            self.assertTrue(report.paths["asset_performance"].exists())

    def test_walk_forward_returns_oos_fold_metrics(self) -> None:
        prices, highs = _sample_avalanche_prices(periods=220)

        folds, assets, summary = run_etf_avalanches_walk_forward(
            prices,
            highs,
            walk_config=ETFAvalanchesWalkForwardConfig(train_size=90, test_size=35, step_size=35, embargo_size=2),
            strategy_config=_fast_config(),
        )

        self.assertFalse(folds.empty)
        self.assertFalse(assets.empty)
        self.assertIn("test_sharpe_ratio", folds.columns)
        self.assertIn("oos_trade_count_total", summary)

    def test_loads_local_yfinance_files_when_present(self) -> None:
        required = {
            "SPY": Path("datasets/SPY/SPY_1d_yfinance.csv"),
            "IWM": Path("datasets/IWM/IWM_1d_yfinance.csv"),
            "EFA": Path("datasets/EFA/EFA_1d_yfinance.csv"),
            "EEM": Path("datasets/EEM/EEM_1d_yfinance.csv"),
            "VNQ": Path("datasets/VNQ/VNQ_1d_yfinance.csv"),
            "SHY": Path("datasets/SHY/SHY_1d_yfinance.csv"),
        }
        if not all(path.exists() for path in required.values()):
            self.skipTest("local ETF Avalanches yfinance datasets are not present")

        prices, highs, volumes = load_etf_avalanche_ohlcv(required)
        readiness = validate_live_readiness(
            prices,
            highs,
            ETFAvalanchesConfig(live_required_symbols=tuple(required)),
            broker_symbol_map={symbol: symbol for symbol in required},
            shortable_symbols=set(required) - {"SHY"},
        )

        self.assertEqual(prices.columns.tolist(), list(required))
        self.assertGreater(len(prices), 500)
        self.assertFalse(volumes.empty)
        self.assertTrue(readiness["ready"])

    @unittest.skipUnless(HAS_VECTORBT and RUN_VECTORBT_TESTS, "set RUN_VECTORBT_TESTS=1 to run optional vectorbt test")
    def test_vectorbt_adapter_runs_on_sample_data(self) -> None:
        prices, highs = _sample_avalanche_prices()
        result = run_etf_avalanches_vectorbt(prices, highs, strategy_config=_fast_config())

        self.assertEqual(len(result.equity), len(result.pandas_result.prices))
        self.assertIn("total_return", result.metrics)


def _fast_config() -> ETFAvalanchesConfig:
    return ETFAvalanchesConfig(
        long_lookback=40,
        intermediate_lookback=8,
        volatility_lookback=20,
        limit_entry_pct=0.01,
        initial_cash=10_000.0,
        trading_cost=0.0005,
        live_required_symbols=("SPY", "IWM", "EFA", "SHY"),
    )


def _sample_avalanche_prices(*, periods: int = 180) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.bdate_range("2024-01-01", periods=periods)
    rows = {}
    high_rows = {}
    specs = {
        "SPY": (120.0, -0.0010, 0),
        "IWM": (100.0, -0.0014, 1),
        "EFA": (90.0, -0.0012, 2),
        "SHY": (82.0, 0.00005, 3),
    }
    for symbol, (start, drift, offset) in specs.items():
        price = start
        values = []
        highs = []
        for i, _ in enumerate(index):
            rally = 0.035 if i % 17 in {8, 9} and symbol != "SHY" else 0.0
            washout = -0.028 if i % 17 in {10, 11} and symbol != "SHY" else 0.0
            cycle = 0.003 * ((i + offset) % 7 - 3) / 3.0
            price *= 1.0 + drift + cycle + rally + washout
            values.append(price)
            highs.append(price * (1.025 if rally > 0 else 1.004))
        rows[symbol] = values
        high_rows[symbol] = highs
    return pd.DataFrame(rows, index=index), pd.DataFrame(high_rows, index=index)


if __name__ == "__main__":
    unittest.main()
