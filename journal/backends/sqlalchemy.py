"""SQLAlchemy ORM backend for the trade journal service."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, case, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class JournalBase(DeclarativeBase):
    pass


class TradeModel(JournalBase):
    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_trades_strategy", "strategy"),
        Index("idx_trades_token", "token"),
        Index("idx_trades_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_date: Mapped[str] = mapped_column(String(40), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    size_sol: Mapped[float] = mapped_column(Float, nullable=False)
    size_usd: Mapped[float | None] = mapped_column(Float)
    strategy: Mapped[str] = mapped_column(String(128), nullable=False)
    setup_quality: Mapped[int | None] = mapped_column(Integer)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    exit_date: Mapped[str | None] = mapped_column(String(40))
    exit_price: Mapped[float | None] = mapped_column(Float)
    pnl_sol: Mapped[float | None] = mapped_column(Float)
    pnl_pct: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str | None] = mapped_column(String(16))
    hold_time_minutes: Mapped[int | None] = mapped_column(Integer)
    emotional_state: Mapped[str | None] = mapped_column(String(128))
    lessons: Mapped[str | None] = mapped_column(Text)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    stop_price: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)
    risk_reward: Mapped[float | None] = mapped_column(Float)
    fees_sol: Mapped[float | None] = mapped_column(Float)
    slippage_bps: Mapped[float | None] = mapped_column(Float)
    expected_profit: Mapped[float | None] = mapped_column(Float)
    actual_profit: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TradeEventModel(JournalBase):
    __tablename__ = "trade_events"
    __table_args__ = (Index("idx_trade_events_trade_id", "trade_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("trades.id"), nullable=True)
    event_time: Mapped[str] = mapped_column(String(40), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    price: Mapped[float | None] = mapped_column(Float)
    size_sol: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class SQLAlchemyJournalBackend:
    """SQLAlchemy storage adapter for local or production journal databases."""

    def __init__(self, path: str | Path = "db/trade_journal.sqlite", *, echo: bool = False) -> None:
        self.database_url = _database_url(path)
        self.engine = create_engine(self.database_url, echo=echo, future=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        JournalBase.metadata.create_all(self.engine)

    def upsert_trade(self, payload: dict[str, Any]) -> None:
        with self._session() as session:
            record = session.get(TradeModel, str(payload["id"]))
            if record is None:
                session.add(TradeModel(**payload))
                return
            for key, value in payload.items():
                setattr(record, key, value)

    def insert_event(self, payload: dict[str, Any]) -> int:
        with self._session() as session:
            event = TradeEventModel(**payload)
            session.add(event)
            session.flush()
            return int(event.id)

    def update_trade_status(self, trade_id: str, *, status: str, updated_at: str) -> None:
        with self._session() as session:
            record = session.get(TradeModel, trade_id)
            if record is not None:
                record.status = status
                record.updated_at = updated_at

    def update_trade_exit(self, trade_id: str, payload: dict[str, Any]) -> None:
        with self._session() as session:
            record = session.get(TradeModel, trade_id)
            if record is None:
                return
            for key, value in payload.items():
                if key == "lessons" and value is None:
                    continue
                setattr(record, key, value)

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            record = session.get(TradeModel, trade_id)
            return _trade_to_dict(record) if record is not None else None

    def list_trades(self, *, status: str | None = None, strategy: str | None = None) -> list[dict[str, Any]]:
        statement = select(TradeModel)
        if status is not None:
            statement = statement.where(TradeModel.status == status)
        if strategy is not None:
            statement = statement.where(TradeModel.strategy == strategy)
        statement = statement.order_by(TradeModel.entry_date, TradeModel.id)
        with self._session() as session:
            return [_trade_to_dict(record) for record in session.execute(statement).scalars()]

    def list_events(self, trade_id: str | None = None) -> list[dict[str, Any]]:
        statement = select(TradeEventModel)
        if trade_id is not None:
            statement = statement.where(TradeEventModel.trade_id == trade_id)
        statement = statement.order_by(TradeEventModel.event_time, TradeEventModel.id)
        with self._session() as session:
            return [_event_to_dict(record) for record in session.execute(statement).scalars()]

    def summary_by_strategy(self) -> list[dict[str, Any]]:
        statement = (
            select(
                TradeModel.strategy.label("strategy"),
                func.count(TradeModel.id).label("trade_count"),
                func.sum(case((TradeModel.outcome == "win", 1), else_=0)).label("wins"),
                func.sum(case((TradeModel.outcome == "loss", 1), else_=0)).label("losses"),
                func.sum(func.coalesce(TradeModel.pnl_sol, 0)).label("pnl_sol"),
            )
            .group_by(TradeModel.strategy)
            .order_by(TradeModel.strategy)
        )
        with self._session() as session:
            return [dict(row._mapping) for row in session.execute(statement)]

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


def _database_url(path_or_url: str | Path) -> str:
    value = str(path_or_url)
    if "://" in value:
        return value
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def _trade_to_dict(record: TradeModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "token": record.token,
        "direction": record.direction,
        "entry_date": record.entry_date,
        "entry_price": record.entry_price,
        "size_sol": record.size_sol,
        "size_usd": record.size_usd,
        "strategy": record.strategy,
        "setup_quality": record.setup_quality,
        "rationale": record.rationale,
        "exit_date": record.exit_date,
        "exit_price": record.exit_price,
        "pnl_sol": record.pnl_sol,
        "pnl_pct": record.pnl_pct,
        "outcome": record.outcome,
        "hold_time_minutes": record.hold_time_minutes,
        "emotional_state": record.emotional_state,
        "lessons": record.lessons,
        "tags_json": record.tags_json,
        "stop_price": record.stop_price,
        "target_price": record.target_price,
        "risk_reward": record.risk_reward,
        "fees_sol": record.fees_sol,
        "slippage_bps": record.slippage_bps,
        "expected_profit": record.expected_profit,
        "actual_profit": record.actual_profit,
        "status": record.status,
        "mode": record.mode,
        "source": record.source,
        "metadata_json": record.metadata_json,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _event_to_dict(record: TradeEventModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "trade_id": record.trade_id,
        "event_time": record.event_time,
        "event_type": record.event_type,
        "token": record.token,
        "strategy": record.strategy,
        "direction": record.direction,
        "price": record.price,
        "size_sol": record.size_sol,
        "status": record.status,
        "message": record.message,
        "metadata_json": record.metadata_json,
    }
