import tempfile
import unittest
import uuid
from pathlib import Path

from journal import JournalEvent, JournalTrade, TRADE_STATUSES, TradeJournal


def assert_uuid(testcase: unittest.TestCase, value: str) -> None:
    parsed = uuid.UUID(value)
    testcase.assertEqual(str(parsed), value)


class MemoryJournalBackend:
    def __init__(self) -> None:
        self.trades: dict[str, dict] = {}
        self.events: list[dict] = []

    def upsert_trade(self, payload: dict) -> None:
        self.trades[str(payload["id"])] = dict(payload)

    def insert_event(self, payload: dict) -> int:
        row = {"id": len(self.events) + 1, **payload}
        self.events.append(row)
        return int(row["id"])

    def update_trade_status(self, trade_id: str, *, status: str, updated_at: str) -> None:
        if trade_id in self.trades:
            self.trades[trade_id]["status"] = status
            self.trades[trade_id]["updated_at"] = updated_at

    def update_trade_exit(self, trade_id: str, payload: dict) -> None:
        self.trades[trade_id].update(payload)

    def get_trade(self, trade_id: str) -> dict | None:
        trade = self.trades.get(trade_id)
        return dict(trade) if trade is not None else None

    def list_trades(self, *, status: str | None = None, strategy: str | None = None) -> list[dict]:
        rows = list(self.trades.values())
        if status is not None:
            rows = [row for row in rows if row["status"] == status]
        if strategy is not None:
            rows = [row for row in rows if row["strategy"] == strategy]
        return [dict(row) for row in rows]

    def list_events(self, trade_id: str | None = None) -> list[dict]:
        rows = self.events
        if trade_id is not None:
            rows = [row for row in rows if row["trade_id"] == trade_id]
        return [dict(row) for row in rows]

    def summary_by_strategy(self) -> list[dict]:
        return []


class TradeJournalTests(unittest.TestCase):
    def test_trade_journal_accepts_custom_backend(self) -> None:
        backend = MemoryJournalBackend()
        journal = TradeJournal(backend=backend)

        trade_id = journal.record_signal_trade(
            token="EURUSD",
            direction="long",
            entry_date="2026-06-17T10:00:00Z",
            entry_price=1.085,
            size_sol=0.01,
            strategy="backend-neutral",
            rationale="Custom backend smoke test.",
            status="signal",
            mode="dry_run",
            source="test",
        )

        assert_uuid(self, trade_id)
        self.assertEqual(journal.get_trade(trade_id)["strategy"], "backend-neutral")
        self.assertEqual(journal.list_events(trade_id)[0]["event_type"], "signal")

    def test_records_signal_trade_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = TradeJournal(Path(tmpdir) / "journal.sqlite")

            trade_id = journal.record_signal_trade(
                token="EURUSD",
                direction="long",
                entry_date="2026-06-17T10:00:00Z",
                entry_price=1.085,
                size_sol=0.01,
                strategy="bollinger-adaptive",
                rationale="Bollinger adaptive long signal with ATR-defined stop and target.",
                status="signal",
                mode="dry_run",
                source="aiomql:BollingerBands",
                stop_price=1.08,
                target_price=1.095,
                risk_reward=2.0,
                expected_profit=25.5,
                metadata={"timeframe": "M15"},
            )

            trades = journal.list_trades()
            events = journal.list_events(trade_id)

        assert_uuid(self, trade_id)
        self.assertEqual(trades[0]["token"], "EURUSD")
        self.assertEqual(trades[0]["status"], "signal")
        self.assertEqual(trades[0]["expected_profit"], 25.5)
        self.assertEqual(trades[0]["metadata"], {"timeframe": "M15"})
        self.assertEqual(events[0]["event_type"], "signal")
        self.assertEqual(events[0]["metadata"]["expected_profit"], 25.5)
        self.assertIn("filled", TRADE_STATUSES)

    def test_updates_exit_and_computes_hold_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = TradeJournal(Path(tmpdir) / "journal.sqlite")
            trade_id = journal.record_trade(
                JournalTrade(
                    token="SOL",
                    direction="short",
                    entry_date="2026-06-17T10:00:00Z",
                    entry_price=150.0,
                    size_sol=2.0,
                    strategy="range-fade",
                    rationale="Fade upper range with defined stop.",
                    expected_profit=0.4,
                )
            )

            journal.update_exit(
                trade_id,
                exit_date="2026-06-17T11:30:00Z",
                exit_price=145.0,
                pnl_sol=0.5,
                pnl_pct=3.33,
                outcome="win",
                actual_profit=0.48,
            )
            trade = journal.get_trade(trade_id)

        self.assertIsNotNone(trade)
        self.assertEqual(trade["outcome"], "win")
        self.assertEqual(trade["hold_time_minutes"], 90)
        self.assertEqual(trade["expected_profit"], 0.4)
        self.assertEqual(trade["actual_profit"], 0.48)

    def test_event_status_updates_parent_trade_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = TradeJournal(Path(tmpdir) / "journal.sqlite")
            trade_id = journal.record_signal_trade(
                token="EURUSD",
                direction="short",
                entry_date="2026-06-17T10:00:00Z",
                entry_price=1.09,
                size_sol=0.01,
                strategy="range-fade",
                rationale="Short signal with execution gate satisfied.",
                status="submitted",
                mode="live",
                source="aiomql:BollingerBands",
            )

            journal.record_event(
                JournalEvent(
                    trade_id=trade_id,
                    event_time="2026-06-17T10:00:01Z",
                    event_type="order_error",
                    token="EURUSD",
                    strategy="range-fade",
                    status="error",
                    message="broker rejected order",
                )
            )
            trade = journal.get_trade(trade_id)

        self.assertEqual(trade["status"], "error")

    def test_records_aiomql_history_deal_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = TradeJournal(Path(tmpdir) / "journal.sqlite")

            row_id = journal.record_broker_history_event(
                {
                    "deal": 987654,
                    "order": 123456,
                    "position_id": 444,
                    "symbol": "EURUSD",
                    "type": "BUY",
                    "entry": "OUT",
                    "volume": 0.01,
                    "price": 1.0875,
                    "profit": 12.5,
                    "commission": -0.07,
                    "swap": 0.0,
                    "time": "2026-06-17T10:15:00Z",
                    "magic": 20260617,
                    "comment": "bollinger-adaptive",
                },
                item_type="deal",
                strategy="bollinger-adaptive",
            )
            events = journal.list_events()

        self.assertGreater(row_id, 0)
        self.assertEqual(events[0]["event_type"], "broker_history_deal")
        self.assertEqual(events[0]["status"], "closed")
        self.assertEqual(events[0]["metadata"]["broker_external_id"], "987654")
        self.assertEqual(events[0]["metadata"]["broker_position_id"], "444")

    def test_rejects_unknown_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = TradeJournal(Path(tmpdir) / "journal.sqlite")

            with self.assertRaisesRegex(Exception, "status must be one of"):
                journal.record_signal_trade(
                    token="EURUSD",
                    direction="long",
                    entry_date="2026-06-17T10:00:00Z",
                    entry_price=1.09,
                    size_sol=0.01,
                    strategy="range-fade",
                    rationale="Signal with invalid status.",
                    status="dry_run",
                    mode="dry_run",
                    source="aiomql:BollingerBands",
                )


if __name__ == "__main__":
    unittest.main()
