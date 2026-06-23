"""Bot-level aiomql position trackers.

These callables are designed to be scheduled with ``Bot.add_coroutine``. They
default to signal-only mode and require an explicit ``live_management`` opt-in
before they call a broker close function.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any


logger = logging.getLogger(__name__)
AsyncCallable = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class TrackerDecision:
    """A position-management decision emitted by a tracker."""

    tracker: str
    ticket: str
    should_close: bool
    reason: str
    live_management: bool


def build_tracker_callable(name: str, params: dict[str, Any] | None = None) -> AsyncCallable:
    """Return a scheduled tracker callable by name."""
    normalized = normalize_tracker_name(name)
    tracker_params = dict(params or {})
    if normalized == "exit_at_profit":
        async def run_exit_at_profit() -> Any:
            return await exit_at_profit(**tracker_params)

        return run_exit_at_profit
    if normalized == "exit_at_points":
        async def run_exit_at_points() -> Any:
            return await exit_at_points(**tracker_params)

        return run_exit_at_points
    raise ValueError(f"Unknown tracker {name!r}. Available: exit_at_points, exit_at_profit")


async def exit_at_profit(
    *,
    profit_amount: float = 0.0,
    live_management: bool = False,
    positions_provider: str | Callable[[], Any] | None = None,
    close_position: str | Callable[[Any], Any] | None = None,
) -> list[TrackerDecision]:
    """Signal or close positions whose floating profit reaches ``profit_amount``."""
    provider = resolve_callable(positions_provider)
    closer = resolve_callable(close_position)
    positions = await load_positions(provider)
    decisions = [
        TrackerDecision(
            tracker="exit_at_profit",
            ticket=position_ticket(position),
            should_close=position_profit(position) >= float(profit_amount),
            reason=f"profit >= {float(profit_amount)}",
            live_management=bool(live_management),
        )
        for position in positions
    ]
    await apply_tracker_decisions(decisions, positions=positions, close_position=closer)
    return decisions


async def exit_at_points(
    *,
    points: float = 0.0,
    live_management: bool = False,
    positions_provider: str | Callable[[], Any] | None = None,
    close_position: str | Callable[[Any], Any] | None = None,
) -> list[TrackerDecision]:
    """Signal or close positions after price moves ``points`` from entry."""
    provider = resolve_callable(positions_provider)
    closer = resolve_callable(close_position)
    positions = await load_positions(provider)
    decisions = [
        TrackerDecision(
            tracker="exit_at_points",
            ticket=position_ticket(position),
            should_close=abs(position_points(position)) >= float(points),
            reason=f"abs(points) >= {float(points)}",
            live_management=bool(live_management),
        )
        for position in positions
    ]
    await apply_tracker_decisions(decisions, positions=positions, close_position=closer)
    return decisions


async def load_positions(provider: Callable[[], Any] | None) -> list[Any]:
    """Load open positions from a configured provider."""
    if provider is None:
        logger.info("Position tracker skipped because no positions_provider was configured")
        return []
    result = provider()
    if inspect.isawaitable(result):
        result = await result
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, tuple):
        return list(result)
    return list(result)


async def apply_tracker_decisions(
    decisions: list[TrackerDecision],
    *,
    positions: list[Any],
    close_position: Callable[[Any], Any] | None,
) -> None:
    """Apply close decisions only when live management and closer are enabled."""
    positions_by_ticket = {position_ticket(position): position for position in positions}
    for decision in decisions:
        if not decision.should_close:
            continue
        if not decision.live_management:
            logger.info("%s signaled close for ticket %s: %s", decision.tracker, decision.ticket, decision.reason)
            continue
        if close_position is None:
            logger.warning("%s wanted to close ticket %s but no close_position callable was configured", decision.tracker, decision.ticket)
            continue
        result = close_position(positions_by_ticket[decision.ticket])
        if inspect.isawaitable(result):
            await result


def resolve_callable(value: str | Callable[..., Any] | None) -> Callable[..., Any] | None:
    """Resolve a callable or ``module:attribute`` reference."""
    if value is None or callable(value):
        return value
    module_name, _, attr = value.partition(":")
    if not module_name or not attr:
        raise ValueError(f"Invalid callable path: {value!r}")
    return getattr(import_module(module_name), attr)


def normalize_tracker_name(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def position_ticket(position: Any) -> str:
    return str(first_value(position, ("ticket", "identifier", "id", "order")))


def position_profit(position: Any) -> float:
    return float(first_value(position, ("profit", "floating_profit", "pnl", "unrealized_pnl"), default=0.0) or 0.0)


def position_points(position: Any) -> float:
    explicit = first_value(position, ("points", "profit_points", "floating_points"))
    if explicit is not None:
        return float(explicit)

    current = first_value(position, ("price_current", "current_price", "price"))
    entry = first_value(position, ("price_open", "entry_price", "open_price"))
    point = float(first_value(position, ("point", "point_size"), default=1.0) or 1.0)
    direction = str(first_value(position, ("type", "direction", "side"), default="")).lower()
    if current is None or entry is None:
        return 0.0

    raw_points = (float(current) - float(entry)) / point
    if direction in {"sell", "short", "1"}:
        raw_points *= -1.0
    return raw_points


def first_value(value: Any, names: tuple[str, ...], *, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default
