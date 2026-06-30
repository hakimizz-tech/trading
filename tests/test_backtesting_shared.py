import unittest
from importlib.util import find_spec

import pandas as pd

from backtesting import (
    BrokerProfile,
    EventBacktestConfig,
    EventDrivenBacktester,
    ExecutionModel,
    IntrabarCollisionPolicy,
    PreparedSignals,
    SignalValidationError,
    SimulatedOrderStatus,
    SimulatedOrderType,
    VectorBTConfig,
    run_vectorbt,
)


class PreparedSignalsValidationTests(unittest.TestCase):
    def test_accepts_aligned_boolean_signals(self) -> None:
        signals = _signals()

        report = signals.validate()

        self.assertTrue(report.valid)
        self.assertEqual(report.errors, ())

    def test_rejects_misaligned_non_boolean_and_conflicting_signals(self) -> None:
        signals = _signals()
        bad = PreparedSignals(
            data=signals.data,
            close=signals.close,
            long_entries=pd.Series([1, 0, 0], index=signals.data.index),
            long_exits=pd.Series([True, False, False], index=signals.data.index),
            short_entries=signals.short_entries,
            short_exits=signals.short_exits,
        )

        with self.assertRaises(SignalValidationError) as context:
            bad.validate()

        self.assertIn("long_entries must have boolean dtype", context.exception.errors)
        self.assertIn(
            "long_entries and long_exits conflict on at least one bar",
            context.exception.errors,
        )

    def test_warns_about_obvious_future_columns(self) -> None:
        signals = _signals()
        data = signals.data.assign(future_return=[0.1, 0.2, 0.3])
        candidate = PreparedSignals(
            data=data,
            close=signals.close,
            long_entries=signals.long_entries,
            long_exits=signals.long_exits,
            short_entries=signals.short_entries,
            short_exits=signals.short_exits,
        )

        report = candidate.validate()

        self.assertEqual(len(report.warnings), 1)
        self.assertIn("future_return", report.warnings[0])

    def test_provenance_rejects_label_columns_used_as_features(self) -> None:
        signals = _signals()
        data = signals.data.assign(rsi=[40.0, 45.0, 50.0], next_return=[0.1, -0.2, 0.3])
        candidate = PreparedSignals(
            data=data,
            close=signals.close,
            long_entries=signals.long_entries,
            long_exits=signals.long_exits,
            short_entries=signals.short_entries,
            short_exits=signals.short_exits,
            feature_columns=("rsi", "next_return"),
            label_columns=("next_return",),
            signal_columns=("long_entry",),
            minimum_feature_lag=0,
        )

        with self.assertRaises(SignalValidationError) as context:
            candidate.validate(require_provenance=True)

        self.assertIn("label_columns must not overlap feature_columns", context.exception.errors)
        self.assertIn(
            "signal_columns reference columns missing from data: long_entry",
            context.exception.errors,
        )
        self.assertIn(
            "minimum_feature_lag must be at least 1 when provenance is required",
            context.exception.errors,
        )


class EventDrivenBacktesterTests(unittest.TestCase):
    def test_conservative_parent_bar_collision_uses_stop_first(self) -> None:
        index = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")
        data = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0],
                "high": [101.0, 111.0, 101.0],
                "low": [99.0, 94.0, 99.0],
                "close": [100.0, 100.0, 100.0],
                "volume": [10.0, 10.0, 10.0],
            },
            index=index,
        )
        signals = _signals(data=data, stop=0.05, target=0.10)
        engine = _engine(collision_policy=IntrabarCollisionPolicy.CONSERVATIVE)

        result = engine.run(signals)

        self.assertEqual(result.trades.iloc[0]["exit_reason"], "stop_loss")
        self.assertAlmostEqual(float(result.trades.iloc[0]["exit_price"]), 95.0)

    def test_lower_timeframe_replay_resolves_target_before_later_stop(self) -> None:
        index = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")
        data = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0],
                "high": [101.0, 111.0, 101.0],
                "low": [99.0, 94.0, 99.0],
                "close": [100.0, 100.0, 100.0],
                "volume": [10.0, 10.0, 10.0],
            },
            index=index,
        )
        lower_index = pd.date_range(index[1], periods=3, freq="20min")
        lower = pd.DataFrame(
            {
                "open": [100.0, 110.0, 96.0],
                "high": [111.0, 110.0, 97.0],
                "low": [99.0, 98.0, 94.0],
                "close": [110.0, 99.0, 95.0],
            },
            index=lower_index,
        )

        result = _engine().run(
            _signals(data=data, stop=0.05, target=0.10),
            lower_timeframe=lower,
        )

        self.assertEqual(result.trades.iloc[0]["exit_reason"], "take_profit")
        self.assertAlmostEqual(float(result.trades.iloc[0]["exit_price"]), 110.0)

    def test_dynamic_costs_and_partial_fills_are_recorded(self) -> None:
        data = _ohlc(periods=5)
        data["volume"] = [0.4] * len(data)
        data["spread"] = [2.0] * len(data)
        data["slippage_points"] = [1.0] * len(data)
        engine = EventDrivenBacktester(
            broker=_broker(min_volume=0.1, volume_step=0.1),
            execution=ExecutionModel(latency_bars=1, max_volume_participation=1.0),
            config=EventBacktestConfig(order_volume=1.0),
        )

        result = engine.run(_signals(data=data))

        entry_fills = result.fills[result.fills["reason"] == "entry"]
        self.assertGreaterEqual(len(entry_fills), 2)
        self.assertIn(
            SimulatedOrderStatus.PARTIALLY_FILLED.value,
            set(entry_fills["status"]),
        )
        self.assertTrue((entry_fills["spread_cost"] > 0).all())
        self.assertTrue((entry_fills["slippage_cost"] > 0).all())

    def test_insufficient_margin_rejects_order(self) -> None:
        engine = EventDrivenBacktester(
            broker=_broker(contract_size=100_000.0, leverage=1.0),
            config=EventBacktestConfig(initial_cash=1_000.0, order_volume=1.0),
        )

        result = engine.run(_signals(data=_ohlc()))

        self.assertIn("insufficient_margin", set(result.orders["reason"]))
        self.assertEqual(result.metrics["trade_count"], 0)

    def test_unfilled_limit_order_expires(self) -> None:
        engine = EventDrivenBacktester(
            broker=_broker(),
            execution=ExecutionModel(latency_bars=1, order_expiry_bars=1),
            config=EventBacktestConfig(
                entry_order_type=SimulatedOrderType.LIMIT,
                limit_offset_points=50.0,
            ),
        )

        result = engine.run(_signals(data=_ohlc(periods=4)))

        self.assertIn(SimulatedOrderStatus.EXPIRED.value, set(result.orders["status"]))
        self.assertTrue(result.fills.empty)

    def test_margin_stop_out_forces_position_close(self) -> None:
        data = _ohlc(periods=3)
        data.loc[data.index[1], ["low", "close"]] = [1.0, 1.0]
        engine = EventDrivenBacktester(
            broker=_broker(contract_size=1.0, leverage=1.0),
            execution=ExecutionModel(latency_bars=1),
            config=EventBacktestConfig(initial_cash=100.0, order_volume=1.0),
        )

        result = engine.run(_signals(data=data))

        self.assertEqual(result.trades.iloc[0]["exit_reason"], "margin_stop_out")

    def test_provider_outage_rejects_order(self) -> None:
        data = _ohlc()
        data["exchange_outage"] = [False, True, False]

        result = _engine().run(_signals(data=data))

        self.assertIn("market_unavailable", set(result.orders["reason"]))
        self.assertTrue(result.fills.empty)

    def test_provider_borrow_unavailable_rejects_short(self) -> None:
        data = _ohlc()
        data["borrow_available"] = [True, False, True]
        signals = _signals(data=data)
        short_entries = pd.Series(False, index=data.index, dtype=bool)
        short_entries.iloc[0] = True
        short_signals = PreparedSignals(
            data=data,
            close=signals.close,
            long_entries=signals.short_entries.copy(),
            long_exits=signals.long_exits.copy(),
            short_entries=short_entries,
            short_exits=signals.short_exits.copy(),
        )

        result = _engine().run(short_signals)

        self.assertIn("borrow_unavailable", set(result.orders["reason"]))
        self.assertTrue(result.fills.empty)

    def test_provider_stop_level_rejects_too_close_protection(self) -> None:
        data = _ohlc()
        data["min_stop_points"] = [0.0, 10.0, 0.0]

        result = _engine().run(_signals(data=data, stop=0.01))

        self.assertIn("invalid_stop_level", set(result.orders["reason"]))
        self.assertTrue(result.fills.empty)

    def test_provider_volume_cap_limits_partial_fill(self) -> None:
        data = _ohlc(periods=4)
        data["max_order_volume"] = [10.0, 0.3, 0.3, 0.3]
        engine = EventDrivenBacktester(
            broker=_broker(min_volume=0.1, volume_step=0.1),
            execution=ExecutionModel(latency_bars=1, max_volume_participation=1.0),
            config=EventBacktestConfig(order_volume=1.0),
        )

        result = engine.run(_signals(data=data))

        entry_fills = result.fills[result.fills["reason"] == "entry"]
        self.assertFalse(entry_fills.empty)
        self.assertTrue((entry_fills["volume"] <= 0.3).all())

    def test_provider_variable_leverage_affects_margin_acceptance(self) -> None:
        data = _ohlc()
        data["leverage"] = [10.0, 100.0, 100.0]
        engine = EventDrivenBacktester(
            broker=_broker(contract_size=100.0, leverage=1.0),
            config=EventBacktestConfig(initial_cash=200.0, order_volume=1.0),
        )

        result = engine.run(_signals(data=data))

        self.assertNotIn("insufficient_margin", set(result.orders["reason"]))
        self.assertFalse(result.fills.empty)

    @unittest.skipUnless(find_spec("vectorbt"), "vectorbt is not installed")
    def test_shared_vectorbt_runner_consumes_prepared_signals(self) -> None:
        result = run_vectorbt(
            _signals(data=_ohlc(periods=10)),
            config=VectorBTConfig(init_cash=1_000.0, size=0.5, freq="1h"),
        )

        self.assertEqual(result.signals.data.shape[0], 10)
        self.assertEqual(len(result.equity), 10)


def _signals(
    *,
    data: pd.DataFrame | None = None,
    stop: float | None = None,
    target: float | None = None,
) -> PreparedSignals:
    frame = data if data is not None else _ohlc()
    count = len(frame)
    long_entries = pd.Series(False, index=frame.index, dtype=bool)
    long_entries.iloc[0] = True
    false = pd.Series(False, index=frame.index, dtype=bool)
    return PreparedSignals(
        data=frame,
        close=frame["close"].astype(float),
        long_entries=long_entries,
        long_exits=false.copy(),
        short_entries=false.copy(),
        short_exits=false.copy(),
        stop_loss=pd.Series(stop, index=frame.index, dtype=float) if stop is not None else None,
        take_profit=pd.Series(target, index=frame.index, dtype=float) if target is not None else None,
    )


def _ohlc(periods: int = 3) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=periods, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * periods,
            "high": [101.0] * periods,
            "low": [99.0] * periods,
            "close": [100.0] * periods,
            "volume": [10.0] * periods,
        },
        index=index,
    )


def _broker(
    *,
    contract_size: float = 1.0,
    leverage: float = 10.0,
    min_volume: float = 0.01,
    volume_step: float = 0.01,
) -> BrokerProfile:
    return BrokerProfile(
        symbol="TEST",
        contract_size=contract_size,
        leverage=leverage,
        point=1.0,
        pip_size=1.0,
        tick_value=1.0,
        min_volume=min_volume,
        max_volume=100.0,
        volume_step=volume_step,
    )


def _engine(
    *,
    collision_policy: IntrabarCollisionPolicy = IntrabarCollisionPolicy.CONSERVATIVE,
) -> EventDrivenBacktester:
    return EventDrivenBacktester(
        broker=_broker(),
        execution=ExecutionModel(latency_bars=1, collision_policy=collision_policy),
        config=EventBacktestConfig(order_volume=1.0),
    )


if __name__ == "__main__":
    unittest.main()
