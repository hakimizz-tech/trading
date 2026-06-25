"""Database-neutral trade journal for strategy signals, order attempts, and exits."""

from __future__ import annotations

import json
import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from journal.backends import JournalBackend, SQLiteJournalBackend


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
    expected_profit: float | None = None
    actual_profit: float | None = None
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


class TradeJournal:
    """Persistent journal for all strategies with a pluggable database backend."""

    def __init__(
        self,
        path: str | Path = "trade_results/trade_journal.sqlite",
        *,
        backend: JournalBackend | None = None,
    ) -> None:
        self.backend = backend or SQLiteJournalBackend(path)

    def record_trade(self, trade: JournalTrade) -> str:
        """Insert or replace a trade record and return its trade id."""
        self._validate_trade(trade)
        trade_id = trade.id or self.next_trade_id(trade.entry_date)
        now = utc_now()
        payload = _trade_payload(trade, trade_id=trade_id, now=now)
        self.backend.upsert_trade(payload)
        return trade_id

    def record_event(self, event: JournalEvent) -> int:
        """Append a lifecycle event and return the backend row id."""
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
        row_id = self.backend.insert_event(payload)
        if event.trade_id is not None and event.status is not None:
            self.backend.update_trade_status(event.trade_id, status=event.status, updated_at=utc_now())
        return row_id

    def record_broker_history_event(
        self,
        item: Mapping[str, Any],
        *,
        item_type: str,
        strategy: str,
        trade_id: str | None = None,
        status: str | None = None,
    ) -> int:
        """Record a normalized event from aiomql History deals or orders.

        aiomql History exposes completed `deals` and `orders`. Their exact
        shape can vary by aiomql/MT5 version, so this method accepts a mapping
        produced by `model_dump()`, `_asdict()`, or the export script. Broker
        ticket/deal/position identifiers are stored in metadata for later
        reconciliation with the ledger and broker exports.
        """
        if item_type not in {"deal", "order"}:
            raise TradeJournalError("item_type must be 'deal' or 'order'")
        event_status = status or ("closed" if item_type == "deal" and _history_item_is_close(item) else "filled")
        if event_status not in TRADE_STATUSES:
            raise TradeJournalError(f"status must be one of: {', '.join(TRADE_STATUSES)}")
        event = JournalEvent(
            trade_id=trade_id,
            event_time=_history_event_time(item),
            event_type=f"broker_history_{item_type}",
            token=_history_symbol(item),
            strategy=strategy,
            direction=_history_direction(item),
            price=_float_or_none(_first_present(item, ("price", "price_open", "price_current"))),
            size_sol=_float_or_none(_first_present(item, ("volume", "volume_initial", "volume_current"))),
            status=event_status,
            message=f"Imported aiomql history {item_type}",
            metadata={
                "broker_external_id": _history_external_id(item),
                "broker_history_type": item_type,
                "broker_ticket": _string_or_none(_first_present(item, ("ticket", "order"))),
                "broker_deal": _string_or_none(_first_present(item, ("deal",))),
                "broker_order": _string_or_none(_first_present(item, ("order",))),
                "broker_position_id": _string_or_none(_first_present(item, ("position_id", "position"))),
                "profit": _float_or_none(_first_present(item, ("profit",))),
                "commission": _float_or_none(_first_present(item, ("commission",))),
                "swap": _float_or_none(_first_present(item, ("swap",))),
                "magic": _first_present(item, ("magic",)),
                "comment": _string_or_none(_first_present(item, ("comment",))),
                "raw": dict(item),
            },
        )
        return self.record_event(event)

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
        actual_profit: float | None = None,
        status: str = "closed",
    ) -> None:
        """Update a trade with realized exit information."""
        if outcome not in {"win", "loss", "breakeven"}:
            raise TradeJournalError("outcome must be one of: win, loss, breakeven")
        existing = self.get_trade(trade_id)
        if existing is None:
            raise TradeJournalError(f"Unknown trade id: {trade_id}")
        hold_minutes = _hold_minutes(existing["entry_date"], exit_date)
        self.backend.update_trade_exit(
            trade_id,
            {
                "exit_date": exit_date,
                "exit_price": exit_price,
                "pnl_sol": pnl_sol,
                "pnl_pct": pnl_pct,
                "actual_profit": pnl_sol if actual_profit is None else actual_profit,
                "outcome": outcome,
                "hold_time_minutes": hold_minutes,
                "lessons": lessons,
                "status": status,
                "updated_at": utc_now(),
            },
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
        expected_profit: float | None = None,
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
            expected_profit=expected_profit,
            status=status,
            mode=mode,
            source=source,
            metadata=metadata or {},
        )
        trade_id = self.record_trade(trade)
        event_metadata = dict(metadata or {})
        if expected_profit is not None:
            event_metadata["expected_profit"] = expected_profit
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
                metadata=event_metadata,
            )
        )
        return trade_id

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        row = self.backend.get_trade(trade_id)
        return _row_to_dict(row) if row is not None else None

    def list_trades(self, *, status: str | None = None, strategy: str | None = None) -> list[dict[str, Any]]:
        rows = self.backend.list_trades(status=status, strategy=strategy)
        return [_row_to_dict(row) for row in rows]

    def list_events(self, trade_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.backend.list_events(trade_id)
        return [_row_to_dict(row) for row in rows]

    def summary_by_strategy(self) -> list[dict[str, Any]]:
        rows = self.backend.summary_by_strategy()
        return [_row_to_dict(row) for row in rows]

    def next_trade_id(self, timestamp: str | None = None) -> str:
        """Return a UUID trade id.

        ``timestamp`` is accepted for backward-compatible call sites, but ids
        are intentionally not date-sequential. Use ``entry_date`` for temporal
        queries and the UUID for stable identity.
        """
        return str(uuid.uuid4())

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


def _row_to_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if "tags_json" in result:
        result["tags"] = json.loads(result.pop("tags_json") or "[]")
    if "metadata_json" in result:
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    return result


def _first_present(item: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _history_external_id(item: Mapping[str, Any]) -> str:
    value = _first_present(item, ("deal", "ticket", "order", "position_id", "position"))
    if value is not None:
        return str(value)
    digest = hashlib.sha256(_json_dumps(dict(item)).encode("utf-8")).hexdigest()[:16]
    return f"history:{digest}"


def _history_symbol(item: Mapping[str, Any]) -> str:
    value = _first_present(item, ("symbol", "instrument", "token"))
    return str(value) if value is not None else "UNKNOWN"


def _history_direction(item: Mapping[str, Any]) -> str | None:
    raw = _first_present(item, ("direction", "side", "type"))
    if raw is None:
        return None
    text = str(raw).lower()
    if "buy" in text or text in {"0", "long"}:
        return "long"
    if "sell" in text or text in {"1", "short"}:
        return "short"
    return None


def _history_item_is_close(item: Mapping[str, Any]) -> bool:
    entry = _first_present(item, ("entry", "entry_type"))
    if entry is None:
        return _float_or_none(_first_present(item, ("profit",))) is not None
    text = str(entry).lower()
    return "out" in text or text in {"1", "out", "close", "closed"}


def _history_event_time(item: Mapping[str, Any]) -> str:
    value = _first_present(item, ("time", "time_msc", "time_done", "time_setup", "timestamp", "created_at"))
    if value is None:
        return utc_now()
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000.0
        parsed = datetime.fromtimestamp(timestamp, tz=UTC)
    else:
        try:
            parsed = _parse_datetime(str(value))
        except ValueError:
            return utc_now()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hold_minutes(entry_date: str, exit_date: str) -> int:
    return int((_parse_datetime(exit_date) - _parse_datetime(entry_date)).total_seconds() // 60)
