"""SQLite backend for the trade journal service."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SQLiteJournalBackend:
    """Stdlib SQLite storage adapter for local research and dry-run trading."""

    def __init__(self, path: str | Path = "trade_results/trade_journal.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def upsert_trade(self, payload: dict[str, Any]) -> None:
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

    def insert_event(self, payload: dict[str, Any]) -> int:
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
            row_id = cursor.lastrowid
        if row_id is None:
            raise RuntimeError("SQLite did not return an event row id")
        return row_id

    def update_trade_status(self, trade_id: str, *, status: str, updated_at: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE trades SET status = ?, updated_at = ? WHERE id = ?", (status, updated_at, trade_id))

    def update_trade_exit(self, trade_id: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit_date = :exit_date,
                    exit_price = :exit_price,
                    pnl_sol = :pnl_sol,
                    pnl_pct = :pnl_pct,
                    actual_profit = :actual_profit,
                    outcome = :outcome,
                    hold_time_minutes = :hold_time_minutes,
                    lessons = COALESCE(:lessons, lessons),
                    status = :status,
                    updated_at = :updated_at
                WHERE id = :trade_id
                """,
                {**payload, "trade_id": trade_id},
            )

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row is not None else None

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
        return [dict(row) for row in rows]

    def list_events(self, trade_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM trade_events"
        params: tuple[Any, ...] = ()
        if trade_id is not None:
            query += " WHERE trade_id = ?"
            params = (trade_id,)
        query += " ORDER BY event_time, id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

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
        return [dict(row) for row in rows]

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
                    expected_profit REAL,
                    actual_profit REAL,
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
            self._ensure_trade_columns(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _ensure_trade_columns(conn: sqlite3.Connection) -> None:
        existing = {str(row["name"]) for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
        migrations = {
            "expected_profit": "ALTER TABLE trades ADD COLUMN expected_profit REAL",
            "actual_profit": "ALTER TABLE trades ADD COLUMN actual_profit REAL",
        }
        for column, statement in migrations.items():
            if column not in existing:
                conn.execute(statement)
