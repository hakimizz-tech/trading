from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from execution.trackers import build_tracker_callable, exit_at_points, exit_at_profit, position_points


def test_exit_at_profit_signals_without_closing_by_default() -> None:
    closed: list[object] = []
    positions = [SimpleNamespace(ticket=1, profit=5.0), SimpleNamespace(ticket=2, profit=1.0)]

    decisions = asyncio.run(
        exit_at_profit(
            profit_amount=4.0,
            live_management=False,
            positions_provider=lambda: positions,
            close_position=closed.append,
        )
    )

    assert [decision.should_close for decision in decisions] == [True, False]
    assert closed == []


def test_exit_at_profit_closes_only_when_live_management_is_enabled() -> None:
    closed: list[object] = []
    positions = [SimpleNamespace(ticket=1, profit=5.0)]

    asyncio.run(
        exit_at_profit(
            profit_amount=4.0,
            live_management=True,
            positions_provider=lambda: positions,
            close_position=closed.append,
        )
    )

    assert closed == positions


def test_exit_at_points_uses_directional_point_distance() -> None:
    closed: list[object] = []
    positions = [
        SimpleNamespace(ticket=1, direction="buy", price_open=1.1000, price_current=1.1100, point=0.0001),
        SimpleNamespace(ticket=2, direction="sell", price_open=1.1000, price_current=1.0900, point=0.0001),
    ]

    decisions = asyncio.run(
        exit_at_points(
            points=99.0,
            live_management=True,
            positions_provider=lambda: positions,
            close_position=closed.append,
        )
    )

    assert [round(position_points(position)) for position in positions] == [100, 100]
    assert [decision.should_close for decision in decisions] == [True, True]
    assert closed == positions


def test_build_tracker_callable_rejects_unknown_tracker() -> None:
    with pytest.raises(ValueError, match="Unknown tracker"):
        build_tracker_callable("missing")
