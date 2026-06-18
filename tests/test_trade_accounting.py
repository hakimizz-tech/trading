import tempfile
import unittest
from pathlib import Path

from accounting import AccountingError, LedgerPosting, LedgerTransaction, SQLiteLedger


class SQLiteLedgerTests(unittest.TestCase):
    def test_funding_and_trade_lifecycle_stays_balanced(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = SQLiteLedger(Path(tmpdir) / "ledger.sqlite", base_currency="SOL")

            ledger.record_funding(amount=10.0, occurred_at="2026-06-17T09:00:00Z")
            ledger.record_buy_fill(
                symbol="BONK",
                cost_basis=2.0,
                fee=0.01,
                occurred_at="2026-06-17T10:00:00Z",
                strategy="momentum-breakout",
                external_id="T-20260617-001",
            )
            ledger.record_sell_fill(
                symbol="BONK",
                proceeds=2.5,
                cost_basis=2.0,
                fee=0.01,
                occurred_at="2026-06-17T11:00:00Z",
                strategy="momentum-breakout",
                external_id="T-20260617-001",
            )

            trial_balance = ledger.trial_balance()
            pnl = ledger.profit_and_loss()
            balance_sheet = ledger.balance_sheet()

        self.assertEqual(trial_balance["difference"], 0.0)
        self.assertAlmostEqual(pnl["total_income"], 0.5)
        self.assertAlmostEqual(pnl["total_expenses"], 0.02)
        self.assertAlmostEqual(pnl["net_income"], 0.48)
        self.assertEqual(balance_sheet["balance_check"], 0.0)

    def test_unbalanced_manual_transaction_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = SQLiteLedger(Path(tmpdir) / "ledger.sqlite")

            with self.assertRaisesRegex(AccountingError, "Unbalanced transaction"):
                ledger.record_transaction(
                    LedgerTransaction(
                        occurred_at="2026-06-17T10:00:00Z",
                        description="bad transaction",
                        postings=[
                            LedgerPosting("1010", debit=1.0),
                            LedgerPosting("5010", credit=0.5),
                        ],
                    )
                )

    def test_realized_loss_debits_realized_gain_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = SQLiteLedger(Path(tmpdir) / "ledger.sqlite")

            tx_id = ledger.record_sell_fill(
                symbol="SOL",
                proceeds=0.8,
                cost_basis=1.0,
                fee=0.0,
                occurred_at="2026-06-17T10:00:00Z",
                strategy="range-fade",
            )
            postings = ledger.list_postings(tx_id)

        realized_loss_posting = [posting for posting in postings if posting["account_code"] == "3010"][0]
        self.assertAlmostEqual(realized_loss_posting["debit"], 0.2)
        self.assertAlmostEqual(realized_loss_posting["credit"], 0.0)

    def test_position_close_posts_profit_commission_and_swap_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = SQLiteLedger(Path(tmpdir) / "ledger.sqlite")

            first_id = ledger.record_position_close(
                symbol="XAUUSD",
                realized_pnl=120.0,
                commission=3.5,
                swap=-1.25,
                occurred_at="2026-06-17T10:00:00Z",
                strategy="bollinger-breakout",
                external_id="DEAL-100",
                direction="long",
                volume=0.1,
                entry_price=2400.0,
                exit_price=2412.0,
            )
            second_id = ledger.record_position_close(
                symbol="XAUUSD",
                realized_pnl=120.0,
                commission=3.5,
                swap=-1.25,
                occurred_at="2026-06-17T10:00:00Z",
                strategy="bollinger-breakout",
                external_id="DEAL-100",
            )
            transactions = ledger.list_transactions()
            pnl = ledger.profit_and_loss()

        self.assertEqual(first_id, second_id)
        self.assertEqual(len(transactions), 1)
        self.assertAlmostEqual(pnl["total_income"], 120.0)
        self.assertAlmostEqual(pnl["total_expenses"], 4.75)
        self.assertAlmostEqual(pnl["net_income"], 115.25)

    def test_position_close_posts_short_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = SQLiteLedger(Path(tmpdir) / "ledger.sqlite")

            tx_id = ledger.record_position_close(
                symbol="GBPUSD",
                realized_pnl=-45.0,
                commission=0.0,
                swap=0.0,
                occurred_at="2026-06-17T10:00:00Z",
                strategy="bollinger-mean-reversion",
                external_id="DEAL-101",
                direction="short",
                volume=0.2,
            )
            postings = ledger.list_postings(tx_id)

        realized_loss = [posting for posting in postings if posting["account_code"] == "3010"][0]
        cash = [posting for posting in postings if posting["account_code"] == "1010"][0]
        self.assertAlmostEqual(realized_loss["debit"], 45.0)
        self.assertAlmostEqual(cash["credit"], 45.0)


if __name__ == "__main__":
    unittest.main()
