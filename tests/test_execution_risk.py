import unittest

from execution import (
    AccountSnapshot,
    BrokerSnapshot,
    OpenPosition,
    SymbolContract,
    calculate_risk_position_size,
    evaluate_live_execution_gate,
)


class ExecutionRiskTests(unittest.TestCase):
    def test_broker_snapshot_filters_open_positions(self) -> None:
        snapshot = BrokerSnapshot(
            account=AccountSnapshot(equity=10_000.0, balance=10_100.0, free_margin=9_000.0, currency="USD"),
            contract=_contract(),
            current_spread=12.0,
            open_positions=(
                OpenPosition(ticket="1", symbol="EURUSD", direction="long", volume=0.1, entry_price=1.1, strategy="bb"),
                OpenPosition(ticket="2", symbol="GBPUSD", direction="short", volume=0.2, entry_price=1.25, strategy="bb"),
            ),
        )

        positions = snapshot.positions_for(symbol="EURUSD", strategy="bb")

        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].ticket, "1")

    def test_position_sizing_rounds_down_to_lot_step(self) -> None:
        result = calculate_risk_position_size(
            equity=10_000.0,
            risk_per_trade=0.01,
            entry_price=1.1000,
            stop_price=1.0950,
            contract=_contract(),
        )

        self.assertTrue(result.accepted)
        self.assertAlmostEqual(result.risk_amount, 100.0)
        self.assertAlmostEqual(result.stop_distance_pips, 50.0)
        self.assertAlmostEqual(result.volume, 0.2)

    def test_position_sizing_caps_at_max_lot(self) -> None:
        result = calculate_risk_position_size(
            equity=100_000.0,
            risk_per_trade=0.05,
            entry_price=1.1000,
            stop_price=1.0999,
            contract=_contract(max_lot=1.0),
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.volume, 1.0)

    def test_position_sizing_rejects_below_min_lot_for_huge_stop(self) -> None:
        result = calculate_risk_position_size(
            equity=1_000.0,
            risk_per_trade=0.005,
            entry_price=1.1000,
            stop_price=1.0000,
            contract=_contract(min_lot=0.01),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "calculated volume is below minimum volume")

    def test_position_sizing_rejects_equal_entry_and_stop(self) -> None:
        result = calculate_risk_position_size(
            equity=10_000.0,
            risk_per_trade=0.01,
            entry_price=1.1000,
            stop_price=1.1000,
            contract=_contract(),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "entry_price and stop_price must differ")

    def test_contract_rejects_invalid_tick_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "tick_value must be positive"):
            _contract(tick_value=0.0)

    def test_live_gate_applies_risk_sizing(self) -> None:
        snapshot = BrokerSnapshot(
            account=AccountSnapshot(equity=10_000.0, balance=10_000.0, free_margin=9_000.0, currency="USD"),
            contract=_contract(),
            current_spread=12.0,
        )

        gate = evaluate_live_execution_gate(
            trade_parameters={"entry_price": 1.1, "stop_loss_price": 1.095},
            snapshot=snapshot,
            strategy="bb",
            symbol="EURUSD",
            max_spread=30.0,
            max_open_positions=1,
            max_daily_loss_pct=0.02,
            max_daily_loss_amount=None,
            daily_net_pnl=0.0,
            use_risk_sizing=True,
            fixed_volume=0.01,
            risk_per_trade=0.01,
            min_volume=0.01,
            max_volume=100.0,
            volume_step=0.01,
        )

        self.assertTrue(gate.allowed)
        self.assertEqual(gate.volume, 0.2)
        self.assertAlmostEqual(float(gate.metadata["risk_amount"]), 100.0)

    def test_live_gate_blocks_spread_open_positions_and_daily_loss(self) -> None:
        snapshot = BrokerSnapshot(
            account=AccountSnapshot(equity=10_000.0, balance=10_000.0, free_margin=9_000.0, currency="USD"),
            contract=_contract(),
            current_spread=35.0,
            open_positions=(OpenPosition(ticket="1", symbol="EURUSD", direction="long", volume=0.1, entry_price=1.1, strategy="bb"),),
        )

        spread_gate = _gate(snapshot, max_spread=30.0)
        position_gate = _gate(snapshot, max_spread=40.0)
        loss_gate = _gate(
            BrokerSnapshot(account=snapshot.account, contract=snapshot.contract, current_spread=10.0),
            max_spread=30.0,
            daily_net_pnl=-250.0,
        )

        self.assertFalse(spread_gate.allowed)
        self.assertEqual(spread_gate.reason, "current spread exceeds max_spread")
        self.assertFalse(position_gate.allowed)
        self.assertEqual(position_gate.reason, "max open positions reached")
        self.assertFalse(loss_gate.allowed)
        self.assertEqual(loss_gate.reason, "max daily loss reached")


def _contract(
    *,
    tick_value: float = 10.0,
    min_lot: float = 0.01,
    max_lot: float = 100.0,
) -> SymbolContract:
    return SymbolContract(
        symbol="EURUSD",
        point=0.00001,
        pip_size=0.0001,
        tick_value=tick_value,
        min_lot=min_lot,
        max_lot=max_lot,
        lot_step=0.01,
    )


def _gate(snapshot: BrokerSnapshot, *, max_spread: float, daily_net_pnl: float = 0.0):
    return evaluate_live_execution_gate(
        trade_parameters={"entry_price": 1.1, "stop_loss_price": 1.095},
        snapshot=snapshot,
        strategy="bb",
        symbol="EURUSD",
        max_spread=max_spread,
        max_open_positions=1,
        max_daily_loss_pct=0.02,
        max_daily_loss_amount=None,
        daily_net_pnl=daily_net_pnl,
        use_risk_sizing=False,
        fixed_volume=0.1,
        risk_per_trade=0.01,
        min_volume=0.01,
        max_volume=100.0,
        volume_step=0.01,
    )


if __name__ == "__main__":
    unittest.main()
