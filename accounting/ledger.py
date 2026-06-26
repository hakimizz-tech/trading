"""SQLAlchemy double-entry ledger for trading operations.

The ledger records only confirmed economic activity: fills, exits, fees,
funding, withdrawals, and income. Strategy signals and order attempts belong in
the trade journal until the broker/exchange confirms a fill.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


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


class AccountingBase(DeclarativeBase):
    pass


class AccountModel(AccountingBase):
    __tablename__ = "accounts"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(16), nullable=False)


class LedgerTransactionModel(AccountingBase):
    __tablename__ = "ledger_transactions"
    __table_args__ = (
        Index("idx_ledger_transactions_external_id", "external_id"),
        Index("idx_ledger_transactions_strategy", "strategy"),
        Index("idx_ledger_transactions_symbol", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    strategy: Mapped[str | None] = mapped_column(String(128))
    symbol: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class LedgerPostingModel(AccountingBase):
    __tablename__ = "ledger_postings"
    __table_args__ = (Index("idx_ledger_postings_account", "account_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("ledger_transactions.id"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.code"), nullable=False)
    debit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    credit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    memo: Mapped[str] = mapped_column(Text, nullable=False, default="")


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


class TradeLedger:
    """Double-entry ledger with reports and strategy-friendly helpers."""

    def __init__(self, path: str | Path = "db/trade_accounting.sqlite", *, base_currency: str = "BASE", echo: bool = False) -> None:
        self.database_url = _database_url(path)
        self.base_currency = base_currency
        self.engine = create_engine(self.database_url, echo=echo, future=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        AccountingBase.metadata.create_all(self.engine)
        self.ensure_default_accounts()

    def ensure_default_accounts(self) -> None:
        with self._session() as session:
            for account in DEFAULT_ACCOUNTS:
                record = session.get(AccountModel, account.code)
                if record is None:
                    session.add(AccountModel(**account.__dict__))
                else:
                    record.name = account.name
                    record.category = account.category
                    record.normal_balance = account.normal_balance

    def add_account(self, account: Account) -> None:
        if account.category not in {"asset", "liability", "income", "expense", "equity"}:
            raise AccountingError("Unsupported account category")
        if account.normal_balance not in {"debit", "credit"}:
            raise AccountingError("normal_balance must be debit or credit")
        with self._session() as session:
            record = session.get(AccountModel, account.code)
            if record is None:
                session.add(AccountModel(**account.__dict__))
            else:
                record.name = account.name
                record.category = account.category
                record.normal_balance = account.normal_balance

    def record_transaction(self, transaction: LedgerTransaction) -> int:
        self._validate_transaction(transaction)
        with self._session() as session:
            record = LedgerTransactionModel(
                occurred_at=transaction.occurred_at,
                description=transaction.description,
                external_id=transaction.external_id,
                strategy=transaction.strategy,
                symbol=transaction.symbol,
                metadata_json=_json_dumps(transaction.metadata),
                created_at=utc_now(),
            )
            session.add(record)
            session.flush()
            for posting in transaction.postings:
                session.add(
                    LedgerPostingModel(
                        transaction_id=int(record.id),
                        account_code=posting.account_code,
                        debit=posting.debit,
                        credit=posting.credit,
                        memo=posting.memo,
                    )
                )
            return int(record.id)

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
        statement = (
            select(LedgerTransactionModel)
            .where(LedgerTransactionModel.external_id == external_id)
            .order_by(LedgerTransactionModel.id)
            .limit(1)
        )
        with self._session() as session:
            record = session.execute(statement).scalar_one_or_none()
            return _transaction_to_dict(record) if record is not None else None

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
        """Record a confirmed MT5/CFD position close."""
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
        """Record a broker-confirmed close/fill that has realized P&L."""
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
        statement = select(
            func.coalesce(func.sum(LedgerPostingModel.debit), 0).label("debits"),
            func.coalesce(func.sum(LedgerPostingModel.credit), 0).label("credits"),
        )
        with self._session() as session:
            row = session.execute(statement).one()
        debits = float(row.debits)
        credits = float(row.credits)
        return {"debits": debits, "credits": credits, "difference": round(debits - credits, 10)}

    def account_balances(self) -> list[dict[str, Any]]:
        statement = (
            select(
                AccountModel.code,
                AccountModel.name,
                AccountModel.category,
                AccountModel.normal_balance,
                func.coalesce(func.sum(LedgerPostingModel.debit), 0).label("debits"),
                func.coalesce(func.sum(LedgerPostingModel.credit), 0).label("credits"),
            )
            .outerjoin(LedgerPostingModel, LedgerPostingModel.account_code == AccountModel.code)
            .group_by(AccountModel.code, AccountModel.name, AccountModel.category, AccountModel.normal_balance)
            .order_by(AccountModel.code)
        )
        balances: list[dict[str, Any]] = []
        with self._session() as session:
            rows = session.execute(statement)
            for row in rows:
                debits = float(row.debits)
                credits = float(row.credits)
                normal = str(row.normal_balance)
                balance = debits - credits if normal == "debit" else credits - debits
                balances.append({**dict(row._mapping), "balance": balance})
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
        conditions = [
            LedgerTransactionModel.occurred_at >= start,
            AccountModel.category.in_(("income", "expense")),
        ]
        if strategy is not None:
            conditions.append(LedgerTransactionModel.strategy == strategy)
        if symbol is not None:
            conditions.append(LedgerTransactionModel.symbol == symbol)
        statement = (
            select(
                AccountModel.category,
                AccountModel.normal_balance,
                func.coalesce(func.sum(LedgerPostingModel.debit), 0).label("debits"),
                func.coalesce(func.sum(LedgerPostingModel.credit), 0).label("credits"),
            )
            .join(LedgerTransactionModel, LedgerTransactionModel.id == LedgerPostingModel.transaction_id)
            .join(AccountModel, AccountModel.code == LedgerPostingModel.account_code)
            .where(*conditions)
            .group_by(AccountModel.category, AccountModel.normal_balance)
        )
        income = 0.0
        expenses = 0.0
        with self._session() as session:
            rows = session.execute(statement)
            for row in rows:
                debits = float(row.debits)
                credits = float(row.credits)
                normal = str(row.normal_balance)
                balance = debits - credits if normal == "debit" else credits - debits
                if row.category == "income":
                    income += balance
                elif row.category == "expense":
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
        statement = select(LedgerTransactionModel).order_by(LedgerTransactionModel.occurred_at, LedgerTransactionModel.id)
        with self._session() as session:
            return [_transaction_to_dict(record) for record in session.execute(statement).scalars()]

    def list_postings(self, transaction_id: int | None = None) -> list[dict[str, Any]]:
        statement = select(LedgerPostingModel)
        if transaction_id is not None:
            statement = statement.where(LedgerPostingModel.transaction_id == transaction_id)
        statement = statement.order_by(LedgerPostingModel.transaction_id, LedgerPostingModel.id)
        with self._session() as session:
            return [_posting_to_dict(record) for record in session.execute(statement).scalars()]

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
        statement = select(AccountModel.code)
        with self._session() as session:
            return {str(code) for code in session.execute(statement).scalars()}

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _database_url(path_or_url: str | Path) -> str:
    value = str(path_or_url)
    if "://" in value:
        return value
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _transaction_to_dict(record: LedgerTransactionModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "occurred_at": record.occurred_at,
        "description": record.description,
        "external_id": record.external_id,
        "strategy": record.strategy,
        "symbol": record.symbol,
        "metadata": json.loads(record.metadata_json or "{}"),
        "created_at": record.created_at,
    }


def _posting_to_dict(record: LedgerPostingModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "transaction_id": record.transaction_id,
        "account_code": record.account_code,
        "debit": record.debit,
        "credit": record.credit,
        "memo": record.memo,
    }
