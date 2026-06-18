"""SQLite trade journal for strategy signals, order attempts, and exits."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TradeJournalError(RuntimeError):
    """Raised when a trade journal record is invalid."""


TRADE_STATUSES: tuple[str, ...] = (
    "signal",
    "blocked",
    "submitted",
    "filled",
    "partially_filled",
    "closed",
    "rejected",
    "error",
)


@dataclass(frozen=True)
class JournalTrade:
    """A structured journal record for a planned, open, or closed trade."""

    token: str
    direction: str
    entry_date: str
    entry_price: float
    size_sol: float
    strategy: str
    rationale: str
    id: str | None = None
    size_usd: float | None = None
    setup_quality: int | None = None
    exit_date: str | None = None
    exit_price: float | None = None
    pnl_sol: float | None = None
    pnl_pct: float | None = None
    outcome: str | None = None
    hold_time_minutes: int | None = None
    emotional_state: str | None = None
    lessons: str | None = None
    tags: list[str] = field(default_factory=list)
    stop_price: float | None = None
    target_price: float | None = None
    risk_reward: float | None = None
    fees_sol: float | None = None
    slippage_bps: float | None = None
    status: str = "signal"
    mode: str = "dry_run"
    source: str = "strategy"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JournalEvent:
    """A lifecycle event attached to a trade or standalone signal."""

    event_type: str
    event_time: str
    token: str
    strategy: str
    trade_id: str | None = None
    direction: str | None = None
    price: float | None = None
    size_sol: float | None = None
    status: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SQLiteTradeJournal:
    """Persistent journal for all strategies using stdlib SQLite only."""

    def __init__(self, path: str | Path = "trade_results/trade_journal.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def record_trade(self, trade: JournalTrade) -> str:
        """Insert or replace a trade record and return its trade id."""
        self._validate_trade(trade)
        trade_id = trade.id or self.next_trade_id(trade.entry_date)
        now = utc_now()
        payload = _trade_payload(trade, trade_id=trade_id, now=now)
        columns = list(payload)
        placeholders = ", ".join("?" for _ in columns)
        update_columns = [column for column in columns if column not in {"id", "created_at"}]
        assignments = ", ".join(f"{column} = excluded.{column}" for column in update_columns)

        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO trades ({", ".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET {assignments}
                """,
                [payload[column] for column in columns],
            )
        return trade_id

    def record_event(self, event: JournalEvent) -> int:
        """Append a lifecycle event and return the SQLite row id."""
        if not event.event_type.strip():
            raise TradeJournalError("event_type is required")
        if event.status is not None and event.status not in TRADE_STATUSES:
            raise TradeJournalError(f"status must be one of: {', '.join(TRADE_STATUSES)}")
        payload = {
            "trade_id": event.trade_id,
            "event_time": event.event_time,
            "event_type": event.event_type,
            "token": event.token,
            "strategy": event.strategy,
            "direction": event.direction,
            "price": event.price,
            "size_sol": event.size_sol,
            "status": event.status,
            "message": event.message,
            "metadata_json": _json_dumps(event.metadata),
        }
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_events (
                    trade_id, event_time, event_type, token, strategy, direction,
                    price, size_sol, status, message, metadata_json
                )
                VALUES (
                    :trade_id, :event_time, :event_type, :token, :strategy, :direction,
                    :price, :size_sol, :status, :message, :metadata_json
                )
                """,
                payload,
            )
            if event.trade_id is not None and event.status is not None:
                conn.execute(
                    "UPDATE trades SET status = ?, updated_at = ? WHERE id = ?",
                    (event.status, utc_now(), event.trade_id),
                )
            return int(cursor.lastrowid)

    def update_exit(
        self,
        trade_id: str,
        *,
        exit_date: str,
        exit_price: float,
        pnl_sol: float,
        pnl_pct: float,
        outcome: str,
        lessons: str | None = None,
        status: str = "closed",
    ) -> None:
        """Update a trade with realized exit information."""
        if outcome not in {"win", "loss", "breakeven"}:
            raise TradeJournalError("outcome must be one of: win, loss, breakeven")
        existing = self.get_trade(trade_id)
        if existing is None:
            raise TradeJournalError(f"Unknown trade id: {trade_id}")
        hold_minutes = _hold_minutes(existing["entry_date"], exit_date)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit_date = ?, exit_price = ?, pnl_sol = ?, pnl_pct = ?,
                    outcome = ?, hold_time_minutes = ?, lessons = COALESCE(?, lessons),
                    status = ?, updated_at = ?
                WHERE id = ?
                """,
                (exit_date, exit_price, pnl_sol, pnl_pct, outcome, hold_minutes, lessons, status, utc_now(), trade_id),
            )
        self.record_event(
            JournalEvent(
                trade_id=trade_id,
                event_time=exit_date,
                event_type="exit",
                token=str(existing["token"]),
                strategy=str(existing["strategy"]),
                direction=str(existing["direction"]),
                price=exit_price,
                status=status,
                metadata={"pnl_sol": pnl_sol, "pnl_pct": pnl_pct, "outcome": outcome},
            )
        )

    def record_signal_trade(
        self,
        *,
        token: str,
        direction: str,
        entry_price: float,
        size_sol: float,
        strategy: str,
        rationale: str,
        status: str,
        mode: str,
        source: str,
        stop_price: float | None = None,
        target_price: float | None = None,
        risk_reward: float | None = None,
        metadata: dict[str, Any] | None = None,
        entry_date: str | None = None,
    ) -> str:
        """Convenience method for journaling an executable strategy signal."""
        now = entry_date or utc_now()
        trade = JournalTrade(
            token=token,
            direction=direction,
            entry_date=now,
            entry_price=entry_price,
            size_sol=size_sol,
            strategy=strategy,
            rationale=rationale,
            stop_price=stop_price,
            target_price=target_price,
            risk_reward=risk_reward,
            status=status,
            mode=mode,
            source=source,
            metadata=metadata or {},
        )
        trade_id = self.record_trade(trade)
        self.record_event(
            JournalEvent(
                trade_id=trade_id,
                event_time=now,
                event_type="signal",
                token=token,
                strategy=strategy,
                direction=direction,
                price=entry_price,
                size_sol=size_sol,
                status=status,
                message=rationale,
                metadata=metadata or {},
            )
        )
        return trade_id

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return _row_to_dict(row) if row is not None else None

    def list_trades(self, *, status: str | None = None, strategy: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if strategy is not None:
            clauses.append("strategy = ?")
            params.append(strategy)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM trades {where} ORDER BY entry_date, id", params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_events(self, trade_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM trade_events"
        params: tuple[Any, ...] = ()
        if trade_id is not None:
            query += " WHERE trade_id = ?"
            params = (trade_id,)
        query += " ORDER BY event_time, id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def summary_by_strategy(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    strategy,
                    COUNT(*) AS trade_count,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
                    SUM(COALESCE(pnl_sol, 0)) AS pnl_sol
                FROM trades
                GROUP BY strategy
                ORDER BY strategy
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def next_trade_id(self, timestamp: str | None = None) -> str:
        date_part = _parse_datetime(timestamp or utc_now()).strftime("%Y%m%d")
        prefix = f"T-{date_part}-"
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM trades WHERE id LIKE ? ORDER BY id DESC LIMIT 1", (f"{prefix}%",)).fetchone()
        next_number = 1
        if row is not None:
            try:
                next_number = int(str(row["id"]).rsplit("-", 1)[1]) + 1
            except (IndexError, ValueError):
                next_number = 1
        return f"{prefix}{next_number:03d}"

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    token TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_date TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    size_sol REAL NOT NULL,
                    size_usd REAL,
                    strategy TEXT NOT NULL,
                    setup_quality INTEGER,
                    rationale TEXT NOT NULL,
                    exit_date TEXT,
                    exit_price REAL,
                    pnl_sol REAL,
                    pnl_pct REAL,
                    outcome TEXT,
                    hold_time_minutes INTEGER,
                    emotional_state TEXT,
                    lessons TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    stop_price REAL,
                    target_price REAL,
                    risk_reward REAL,
                    fees_sol REAL,
                    slippage_bps REAL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    source TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT,
                    event_time TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    token TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    direction TEXT,
                    price REAL,
                    size_sol REAL,
                    status TEXT,
                    message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(trade_id) REFERENCES trades(id)
                );

                CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
                CREATE INDEX IF NOT EXISTS idx_trades_token ON trades(token);
                CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
                CREATE INDEX IF NOT EXISTS idx_trade_events_trade_id ON trade_events(trade_id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _validate_trade(trade: JournalTrade) -> None:
        if not trade.token.strip():
            raise TradeJournalError("token is required")
        if trade.direction not in {"long", "short"}:
            raise TradeJournalError("direction must be 'long' or 'short'")
        if trade.entry_price <= 0:
            raise TradeJournalError("entry_price must be positive")
        if trade.size_sol <= 0:
            raise TradeJournalError("size_sol must be positive")
        if not trade.strategy.strip():
            raise TradeJournalError("strategy is required")
        if not trade.rationale.strip():
            raise TradeJournalError("rationale is required")
        if trade.outcome is not None and trade.outcome not in {"win", "loss", "breakeven"}:
            raise TradeJournalError("outcome must be one of: win, loss, breakeven")
        if trade.status not in TRADE_STATUSES:
            raise TradeJournalError(f"status must be one of: {', '.join(TRADE_STATUSES)}")
        if trade.setup_quality is not None and not 1 <= trade.setup_quality <= 10:
            raise TradeJournalError("setup_quality must be in the range 1-10")


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _trade_payload(trade: JournalTrade, *, trade_id: str, now: str) -> dict[str, Any]:
    payload = asdict(trade)
    payload["id"] = trade_id
    payload["tags_json"] = _json_dumps(payload.pop("tags"))
    payload["metadata_json"] = _json_dumps(payload.pop("metadata"))
    payload["created_at"] = now
    payload["updated_at"] = now
    return payload


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    if "tags_json" in result:
        result["tags"] = json.loads(result.pop("tags_json") or "[]")
    if "metadata_json" in result:
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    return result


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hold_minutes(entry_date: str, exit_date: str) -> int:
    return int((_parse_datetime(exit_date) - _parse_datetime(entry_date)).total_seconds() // 60)
