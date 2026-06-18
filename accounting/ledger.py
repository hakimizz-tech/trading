"""SQLite double-entry ledger for trading operations.

The ledger records only confirmed economic activity: fills, exits, fees,
funding, withdrawals, and income. Strategy signals and order attempts belong in
the trade journal until the broker/exchange confirms a fill.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AccountingError(RuntimeError):
    """Raised when a ledger transaction is invalid or unbalanced."""


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    category: str
    normal_balance: str


@dataclass(frozen=True)
class LedgerPosting:
    account_code: str
    debit: float = 0.0
    credit: float = 0.0
    memo: str = ""


@dataclass(frozen=True)
class LedgerTransaction:
    occurred_at: str
    description: str
    postings: list[LedgerPosting]
    external_id: str | None = None
    strategy: str | None = None
    symbol: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


DEFAULT_ACCOUNTS: tuple[Account, ...] = (
    Account("1010", "Cash - Base", "asset", "debit"),
    Account("1020", "Cash - Quote", "asset", "debit"),
    Account("1100", "Token Holdings", "asset", "debit"),
    Account("1200", "LP Positions", "asset", "debit"),
    Account("1300", "Staking Deposits", "asset", "debit"),
    Account("2010", "Margin Borrowing", "liability", "credit"),
    Account("2020", "Accrued Taxes Payable", "liability", "credit"),
    Account("3010", "Realized Trading Gains", "income", "credit"),
    Account("3020", "Staking Rewards", "income", "credit"),
    Account("3030", "Airdrop Income", "income", "credit"),
    Account("3040", "LP Fee Income", "income", "credit"),
    Account("4010", "Trading Fees", "expense", "debit"),
    Account("4020", "Gas & Priority Fees", "expense", "debit"),
    Account("4030", "Slippage Cost", "expense", "debit"),
    Account("5010", "Owner Capital", "equity", "credit"),
    Account("5020", "Retained Earnings", "equity", "credit"),
    Account("5030", "Owner Withdrawals", "equity", "debit"),
)


class SQLiteLedger:
    """Double-entry ledger with reports and strategy-friendly helpers."""

    def __init__(self, path: str | Path = "trade_results/trade_accounting.sqlite", *, base_currency: str = "BASE") -> None:
        self.path = Path(path)
        self.base_currency = base_currency
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self.ensure_default_accounts()

    def ensure_default_accounts(self) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO accounts (code, name, category, normal_balance)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    normal_balance = excluded.normal_balance
                """,
                [(account.code, account.name, account.category, account.normal_balance) for account in DEFAULT_ACCOUNTS],
            )

    def add_account(self, account: Account) -> None:
        if account.category not in {"asset", "liability", "income", "expense", "equity"}:
            raise AccountingError("Unsupported account category")
        if account.normal_balance not in {"debit", "credit"}:
            raise AccountingError("normal_balance must be debit or credit")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts (code, name, category, normal_balance)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    normal_balance = excluded.normal_balance
                """,
                (account.code, account.name, account.category, account.normal_balance),
            )

    def record_transaction(self, transaction: LedgerTransaction) -> int:
        self._validate_transaction(transaction)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ledger_transactions (
                    occurred_at, description, external_id, strategy, symbol, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction.occurred_at,
                    transaction.description,
                    transaction.external_id,
                    transaction.strategy,
                    transaction.symbol,
                    _json_dumps(transaction.metadata),
                    utc_now(),
                ),
            )
            transaction_id = int(cursor.lastrowid)
            conn.executemany(
                """
                INSERT INTO ledger_postings (transaction_id, account_code, debit, credit, memo)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (transaction_id, posting.account_code, posting.debit, posting.credit, posting.memo)
                    for posting in transaction.postings
                ],
            )
            return transaction_id

    def record_funding(
        self,
        *,
        amount: float,
        occurred_at: str | None = None,
        memo: str = "Owner capital contribution",
        external_id: str | None = None,
    ) -> int:
        return self.record_transaction(
            LedgerTransaction(
                occurred_at=occurred_at or utc_now(),
                description=memo,
                external_id=external_id,
                postings=[
                    LedgerPosting("1010", debit=amount, memo=memo),
                    LedgerPosting("5010", credit=amount, memo=memo),
                ],
            )
        )

    def record_withdrawal(
        self,
        *,
        amount: float,
        occurred_at: str | None = None,
        memo: str = "Owner withdrawal",
        external_id: str | None = None,
    ) -> int:
        return self.record_transaction(
            LedgerTransaction(
                occurred_at=occurred_at or utc_now(),
                description=memo,
                external_id=external_id,
                postings=[
                    LedgerPosting("5030", debit=amount, memo=memo),
                    LedgerPosting("1010", credit=amount, memo=memo),
                ],
            )
        )

    def record_buy_fill(
        self,
        *,
        symbol: str,
        cost_basis: float,
        fee: float = 0.0,
        occurred_at: str | None = None,
        strategy: str | None = None,
        external_id: str | None = None,
        memo: str | None = None,
    ) -> int:
        """Record a confirmed long/opening buy in base-currency value."""
        description = memo or f"Buy/open {symbol}"
        postings = [
            LedgerPosting("1100", debit=cost_basis, memo=f"{symbol} cost basis"),
            LedgerPosting("1010", credit=cost_basis + fee, memo="Cash paid"),
        ]
        if fee:
            postings.insert(1, LedgerPosting("4010", debit=fee, memo="Trading fee"))
        return self.record_transaction(
            LedgerTransaction(
                occurred_at=occurred_at or utc_now(),
                description=description,
                external_id=external_id,
                strategy=strategy,
                symbol=symbol,
                postings=postings,
                metadata={"flow": "buy_fill", "fee": fee},
            )
        )

    def record_sell_fill(
        self,
        *,
        symbol: str,
        proceeds: float,
        cost_basis: float,
        fee: float = 0.0,
        occurred_at: str | None = None,
        strategy: str | None = None,
        external_id: str | None = None,
        memo: str | None = None,
    ) -> int:
        """Record a confirmed close/sell and realized gain or loss."""
        description = memo or f"Sell/close {symbol}"
        realized = proceeds - cost_basis
        postings = [
            LedgerPosting("1010", debit=proceeds - fee, memo="Cash received"),
            LedgerPosting("1100", credit=cost_basis, memo=f"{symbol} cost basis removed"),
        ]
        if fee:
            postings.insert(1, LedgerPosting("4010", debit=fee, memo="Trading fee"))
        if realized >= 0:
            postings.append(LedgerPosting("3010", credit=realized, memo="Realized trading gain"))
        else:
            postings.append(LedgerPosting("3010", debit=abs(realized), memo="Realized trading loss"))
        return self.record_transaction(
            LedgerTransaction(
                occurred_at=occurred_at or utc_now(),
                description=description,
                external_id=external_id,
                strategy=strategy,
                symbol=symbol,
                postings=postings,
                metadata={"flow": "sell_fill", "fee": fee, "realized": realized},
            )
        )

    def transaction_by_external_id(self, external_id: str) -> dict[str, Any] | None:
        """Return an existing ledger transaction for a broker/exchange id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ledger_transactions WHERE external_id = ? ORDER BY id LIMIT 1", (external_id,)).fetchone()
        return _decode_row(row) if row is not None else None

    def record_position_close(
        self,
        *,
        symbol: str,
        realized_pnl: float,
        commission: float = 0.0,
        swap: float = 0.0,
        occurred_at: str | None = None,
        strategy: str | None = None,
        external_id: str | None = None,
        direction: str | None = None,
        volume: float | None = None,
        entry_price: float | None = None,
        exit_price: float | None = None,
        memo: str | None = None,
        idempotent: bool = True,
    ) -> int | None:
        """Record a confirmed MT5/CFD position close.

        Open fills without realized P&L should stay in the journal until there
        is confirmed economic activity. This method posts realized P&L and
        broker costs only, with margin/exposure details stored as metadata.
        """
        if external_id and idempotent:
            existing = self.transaction_by_external_id(external_id)
            if existing is not None:
                return int(existing["id"])

        postings: list[LedgerPosting] = []
        description = memo or f"Close {symbol} position"
        if realized_pnl > 0:
            postings.extend(
                [
                    LedgerPosting("1010", debit=realized_pnl, memo="Realized P&L cash received"),
                    LedgerPosting("3010", credit=realized_pnl, memo="Realized trading gain"),
                ]
            )
        elif realized_pnl < 0:
            loss = abs(realized_pnl)
            postings.extend(
                [
                    LedgerPosting("3010", debit=loss, memo="Realized trading loss"),
                    LedgerPosting("1010", credit=loss, memo="Realized P&L cash paid"),
                ]
            )

        if commission:
            commission_cost = abs(commission)
            postings.extend(
                [
                    LedgerPosting("4010", debit=commission_cost, memo="Broker commission"),
                    LedgerPosting("1010", credit=commission_cost, memo="Commission paid"),
                ]
            )

        if swap > 0:
            postings.extend(
                [
                    LedgerPosting("1010", debit=swap, memo="Swap cash received"),
                    LedgerPosting("3010", credit=swap, memo="Positive swap income"),
                ]
            )
        elif swap < 0:
            swap_cost = abs(swap)
            postings.extend(
                [
                    LedgerPosting("4010", debit=swap_cost, memo="Negative swap cost"),
                    LedgerPosting("1010", credit=swap_cost, memo="Swap paid"),
                ]
            )

        if not postings:
            return None

        return self.record_transaction(
            LedgerTransaction(
                occurred_at=occurred_at or utc_now(),
                description=description,
                external_id=external_id,
                strategy=strategy,
                symbol=symbol,
                postings=postings,
                metadata={
                    "flow": "position_close",
                    "direction": direction,
                    "volume": volume,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "realized_pnl": realized_pnl,
                    "commission": commission,
                    "swap": swap,
                },
            )
        )

    def record_broker_fill(self, **kwargs: Any) -> int | None:
        """Alias for MT5/CFD confirmed close posting."""
        return self.record_position_close(**kwargs)

    def record_fee(
        self,
        *,
        amount: float,
        fee_type: str = "trading",
        occurred_at: str | None = None,
        strategy: str | None = None,
        symbol: str | None = None,
        external_id: str | None = None,
    ) -> int:
        account = "4020" if fee_type in {"gas", "priority"} else "4010"
        return self.record_transaction(
            LedgerTransaction(
                occurred_at=occurred_at or utc_now(),
                description=f"{fee_type.title()} fee",
                external_id=external_id,
                strategy=strategy,
                symbol=symbol,
                postings=[
                    LedgerPosting(account, debit=amount, memo=f"{fee_type} fee"),
                    LedgerPosting("1010", credit=amount, memo="Cash paid"),
                ],
                metadata={"flow": "fee", "fee_type": fee_type},
            )
        )

    def record_income(
        self,
        *,
        amount: float,
        income_type: str,
        occurred_at: str | None = None,
        external_id: str | None = None,
        memo: str | None = None,
    ) -> int:
        income_accounts = {
            "staking": "3020",
            "airdrop": "3030",
            "lp_fee": "3040",
            "trading": "3010",
        }
        account = income_accounts.get(income_type)
        if account is None:
            raise AccountingError(f"Unsupported income_type: {income_type}")
        description = memo or f"{income_type.replace('_', ' ').title()} income"
        return self.record_transaction(
            LedgerTransaction(
                occurred_at=occurred_at or utc_now(),
                description=description,
                external_id=external_id,
                postings=[
                    LedgerPosting("1010", debit=amount, memo=description),
                    LedgerPosting(account, credit=amount, memo=description),
                ],
                metadata={"flow": "income", "income_type": income_type},
            )
        )

    def trial_balance(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(SUM(debit), 0) AS debits, COALESCE(SUM(credit), 0) AS credits FROM ledger_postings").fetchone()
        debits = float(row["debits"])
        credits = float(row["credits"])
        return {"debits": debits, "credits": credits, "difference": round(debits - credits, 10)}

    def account_balances(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.code,
                    a.name,
                    a.category,
                    a.normal_balance,
                    COALESCE(SUM(p.debit), 0) AS debits,
                    COALESCE(SUM(p.credit), 0) AS credits
                FROM accounts a
                LEFT JOIN ledger_postings p ON p.account_code = a.code
                GROUP BY a.code, a.name, a.category, a.normal_balance
                ORDER BY a.code
                """
            ).fetchall()
        balances: list[dict[str, Any]] = []
        for row in rows:
            debits = float(row["debits"])
            credits = float(row["credits"])
            normal = str(row["normal_balance"])
            balance = debits - credits if normal == "debit" else credits - debits
            balances.append({**dict(row), "balance": balance})
        return balances

    def profit_and_loss(self) -> dict[str, Any]:
        balances = self.account_balances()
        income = [item for item in balances if item["category"] == "income" and item["balance"] != 0]
        expenses = [item for item in balances if item["category"] == "expense" and item["balance"] != 0]
        total_income = sum(float(item["balance"]) for item in income)
        total_expenses = sum(float(item["balance"]) for item in expenses)
        return {
            "income": income,
            "expenses": expenses,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_income": total_income - total_expenses,
        }

    def net_income_since(
        self,
        start: str,
        *,
        strategy: str | None = None,
        symbol: str | None = None,
    ) -> float:
        """Return income minus expenses since an ISO timestamp."""
        clauses = ["t.occurred_at >= ?", "a.category IN ('income', 'expense')"]
        params: list[Any] = [start]
        if strategy is not None:
            clauses.append("t.strategy = ?")
            params.append(strategy)
        if symbol is not None:
            clauses.append("t.symbol = ?")
            params.append(symbol)
        query = f"""
            SELECT
                a.category,
                a.normal_balance,
                COALESCE(SUM(p.debit), 0) AS debits,
                COALESCE(SUM(p.credit), 0) AS credits
            FROM ledger_postings p
            JOIN ledger_transactions t ON t.id = p.transaction_id
            JOIN accounts a ON a.code = p.account_code
            WHERE {' AND '.join(clauses)}
            GROUP BY a.category, a.normal_balance
        """
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        income = 0.0
        expenses = 0.0
        for row in rows:
            debits = float(row["debits"])
            credits = float(row["credits"])
            normal = str(row["normal_balance"])
            balance = debits - credits if normal == "debit" else credits - debits
            if row["category"] == "income":
                income += balance
            elif row["category"] == "expense":
                expenses += balance
        return income - expenses

    def balance_sheet(self) -> dict[str, Any]:
        balances = self.account_balances()
        assets = [item for item in balances if item["category"] == "asset" and item["balance"] != 0]
        liabilities = [item for item in balances if item["category"] == "liability" and item["balance"] != 0]
        equity = [item for item in balances if item["category"] == "equity" and item["balance"] != 0]
        pnl = self.profit_and_loss()
        total_assets = sum(float(item["balance"]) for item in assets)
        total_liabilities = sum(float(item["balance"]) for item in liabilities)
        total_equity = sum(float(item["balance"]) for item in equity) + float(pnl["net_income"])
        return {
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "current_period_net_income": float(pnl["net_income"]),
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "balance_check": round(total_assets - total_liabilities - total_equity, 10),
        }

    def list_transactions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM ledger_transactions ORDER BY occurred_at, id").fetchall()
        return [_decode_row(row) for row in rows]

    def list_postings(self, transaction_id: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM ledger_postings"
        params: tuple[Any, ...] = ()
        if transaction_id is not None:
            query += " WHERE transaction_id = ?"
            params = (transaction_id,)
        query += " ORDER BY transaction_id, id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def _validate_transaction(self, transaction: LedgerTransaction) -> None:
        if len(transaction.postings) < 2:
            raise AccountingError("A transaction must have at least two postings")
        debits = sum(posting.debit for posting in transaction.postings)
        credits = sum(posting.credit for posting in transaction.postings)
        if round(debits - credits, 10) != 0:
            raise AccountingError(f"Unbalanced transaction: debits={debits}, credits={credits}")
        if debits <= 0:
            raise AccountingError("Transaction amount must be positive")
        known_accounts = self._account_codes()
        for posting in transaction.postings:
            if posting.account_code not in known_accounts:
                raise AccountingError(f"Unknown account code: {posting.account_code}")
            if posting.debit < 0 or posting.credit < 0:
                raise AccountingError("Posting debit/credit values must be non-negative")
            if posting.debit and posting.credit:
                raise AccountingError("A posting cannot have both debit and credit")

    def _account_codes(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT code FROM accounts").fetchall()
        return {str(row["code"]) for row in rows}

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    normal_balance TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ledger_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    description TEXT NOT NULL,
                    external_id TEXT,
                    strategy TEXT,
                    symbol TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ledger_postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER NOT NULL,
                    account_code TEXT NOT NULL,
                    debit REAL NOT NULL DEFAULT 0,
                    credit REAL NOT NULL DEFAULT 0,
                    memo TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(transaction_id) REFERENCES ledger_transactions(id),
                    FOREIGN KEY(account_code) REFERENCES accounts(code)
                );

                CREATE INDEX IF NOT EXISTS idx_ledger_transactions_external_id ON ledger_transactions(external_id);
                CREATE INDEX IF NOT EXISTS idx_ledger_transactions_strategy ON ledger_transactions(strategy);
                CREATE INDEX IF NOT EXISTS idx_ledger_transactions_symbol ON ledger_transactions(symbol);
                CREATE INDEX IF NOT EXISTS idx_ledger_postings_account ON ledger_postings(account_code);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    if "metadata_json" in result:
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    return result
