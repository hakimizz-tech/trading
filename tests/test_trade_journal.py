import tempfile
import unittest
from pathlib import Path

from journal import JournalEvent, JournalTrade, SQLiteTradeJournal


class SQLiteTradeJournalTests(unittest.TestCase):
    def test_records_signal_trade_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = SQLiteTradeJournal(Path(tmpdir) / "journal.sqlite")

            trade_id = journal.record_signal_trade(
                token="EURUSD",
                direction="long",
                entry_date="2026-06-17T10:00:00Z",
                entry_price=1.085,
                size_sol=0.01,
                strategy="bollinger-adaptive",
                rationale="Bollinger adaptive long signal with ATR-defined stop and target.",
                status="dry_run",
                mode="dry_run",
                source="aiomql:BollingerBands",
                stop_price=1.08,
                target_price=1.095,
                risk_reward=2.0,
                metadata={"timeframe": "M15"},
            )

            trades = journal.list_trades()
            events = journal.list_events(trade_id)

        self.assertEqual(trade_id, "T-20260617-001")
        self.assertEqual(trades[0]["token"], "EURUSD")
        self.assertEqual(trades[0]["status"], "dry_run")
        self.assertEqual(trades[0]["metadata"], {"timeframe": "M15"})
        self.assertEqual(events[0]["event_type"], "signal")

    def test_updates_exit_and_computes_hold_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = SQLiteTradeJournal(Path(tmpdir) / "journal.sqlite")
            trade_id = journal.record_trade(
                JournalTrade(
                    token="SOL",
                    direction="short",
                    entry_date="2026-06-17T10:00:00Z",
                    entry_price=150.0,
                    size_sol=2.0,
                    strategy="range-fade",
                    rationale="Fade upper range with defined stop.",
                )
            )

            journal.update_exit(
                trade_id,
                exit_date="2026-06-17T11:30:00Z",
                exit_price=145.0,
                pnl_sol=0.5,
                pnl_pct=3.33,
                outcome="win",
            )
            trade = journal.get_trade(trade_id)

        self.assertIsNotNone(trade)
        self.assertEqual(trade["outcome"], "win")
        self.assertEqual(trade["hold_time_minutes"], 90)

    def test_event_status_updates_parent_trade_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = SQLiteTradeJournal(Path(tmpdir) / "journal.sqlite")
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


if __name__ == "__main__":
    unittest.main()
