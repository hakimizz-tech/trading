"""Database backend contract for the trade journal."""

from __future__ import annotations

from typing import Any, Protocol


class JournalBackend(Protocol):
    """Storage adapter used by the database-neutral trade journal service."""

    def upsert_trade(self, payload: dict[str, Any]) -> None:
        """Insert or update a trade payload."""
        ...

    def insert_event(self, payload: dict[str, Any]) -> int:
        """Insert a trade event and return its storage row id."""
        ...

    def update_trade_status(self, trade_id: str, *, status: str, updated_at: str) -> None:
        """Update the lifecycle status for an existing trade."""
        ...

    def update_trade_exit(self, trade_id: str, payload: dict[str, Any]) -> None:
        """Update a trade with realized exit fields."""
        ...

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        """Fetch one trade by id."""
        ...

    def list_trades(self, *, status: str | None = None, strategy: str | None = None) -> list[dict[str, Any]]:
        """List trades, optionally filtered by status or strategy."""
        ...

    def list_events(self, trade_id: str | None = None) -> list[dict[str, Any]]:
        """List lifecycle events."""
        ...

    def summary_by_strategy(self) -> list[dict[str, Any]]:
        """Aggregate journal outcomes by strategy."""
        ...
