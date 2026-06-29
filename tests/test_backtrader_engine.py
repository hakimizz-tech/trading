import unittest
from importlib.util import find_spec

import pandas as pd

from backtesting import (
    BacktraderConfig,
    PreparedSignals,
    SignalValidationError,
    SimulatedOrderType,
    run_backtrader,
)


@unittest.skipUnless(find_spec("backtrader"), "backtrader is not installed")
class BacktraderEngineTests(unittest.TestCase):
    def test_runs_long_entry_and_exit_on_following_bars(self) -> None:
        data = _ohlc([100, 101, 102, 103, 104, 105, 104, 103])
        signals = _signals(data, long_entry=0, long_exit=5)

        result = run_backtrader(
            signals,
            config=BacktraderConfig(
                initial_cash=10_000.0,
                commission=0.001,
                size=10.0,
                annualization_factor=252.0,
            ),
        )

        self.assertEqual(result.metrics["trade_count"], 1)
        self.assertEqual(result.trades.iloc[0]["direction"], "long")
        self.assertEqual(result.trades.iloc[0]["size"], 10.0)
        self.assertAlmostEqual(float(result.trades.iloc[0]["entry_price"]), 101.0)
        self.assertAlmostEqual(float(result.trades.iloc[0]["net_pnl"]), 27.95)
        self.assertIn("completed", set(result.orders["status"]))

    def test_runs_short_entry_and_exit(self) -> None:
        data = _ohlc([100, 99, 98, 97, 96, 95])
        signals = _signals(data, short_entry=0, short_exit=3)

        result = run_backtrader(
            signals,
            config=BacktraderConfig(initial_cash=10_000.0, size=5.0),
        )

        self.assertEqual(result.metrics["trade_count"], 1)
        self.assertEqual(result.trades.iloc[0]["direction"], "short")
        self.assertGreater(float(result.trades.iloc[0]["net_pnl"]), 0.0)

    def test_attached_stop_loss_closes_position(self) -> None:
        data = _ohlc([100, 100, 94, 94, 94])
        data.loc[data.index[2], "high"] = 101.0
        signals = _signals(data, long_entry=0, stop=0.05, target=0.10)

        result = run_backtrader(
            signals,
            config=BacktraderConfig(initial_cash=10_000.0, size=1.0, use_stops=True),
        )

        completed = result.orders[result.orders["status"] == "completed"]
        self.assertIn("stop_loss", set(completed["role"]))
        self.assertEqual(result.metrics["trade_count"], 1)
        self.assertLess(float(result.trades.iloc[0]["net_pnl"]), 0.0)

    def test_limit_entry_uses_configured_offset(self) -> None:
        data = _ohlc([100, 100, 90, 92, 94])
        data.loc[data.index[1], "low"] = 95.0
        data.loc[data.index[2], "low"] = 89.0
        signals = _signals(data, long_entry=0, long_exit=3)

        result = run_backtrader(
            signals,
            config=BacktraderConfig(
                initial_cash=10_000.0,
                size=1.0,
                entry_order_type=SimulatedOrderType.LIMIT,
                limit_offset=0.10,
            ),
        )

        entry = result.orders[
            (result.orders["role"] == "entry") & (result.orders["status"] == "completed")
        ].iloc[0]
        self.assertAlmostEqual(float(entry["executed_price"]), 90.0)

    def test_rejects_invalid_prepared_signals_before_cerebro(self) -> None:
        data = _ohlc([100, 101, 102])
        signals = _signals(data, long_entry=0)
        invalid = PreparedSignals(
            data=signals.data,
            close=signals.close,
            long_entries=signals.long_entries.astype(int),
            long_exits=signals.long_exits,
            short_entries=signals.short_entries,
            short_exits=signals.short_exits,
        )

        with self.assertRaises(SignalValidationError):
            run_backtrader(invalid)


def _ohlc(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(closes), freq="D", tz="UTC")
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        }
    )


def _signals(
    data: pd.DataFrame,
    *,
    long_entry: int | None = None,
    long_exit: int | None = None,
    short_entry: int | None = None,
    short_exit: int | None = None,
    stop: float | None = None,
    target: float | None = None,
) -> PreparedSignals:
    fields = {
        "long_entries": pd.Series(False, index=data.index, dtype=bool),
        "long_exits": pd.Series(False, index=data.index, dtype=bool),
        "short_entries": pd.Series(False, index=data.index, dtype=bool),
        "short_exits": pd.Series(False, index=data.index, dtype=bool),
    }
    for name, position in (
        ("long_entries", long_entry),
        ("long_exits", long_exit),
        ("short_entries", short_entry),
        ("short_exits", short_exit),
    ):
        if position is not None:
            fields[name].iloc[position] = True
    return PreparedSignals(
        data=data,
        close=data["close"],
        **fields,
        stop_loss=pd.Series(stop, index=data.index, dtype=float) if stop is not None else None,
        take_profit=pd.Series(target, index=data.index, dtype=float) if target is not None else None,
    )


if __name__ == "__main__":
    unittest.main()
