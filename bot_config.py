"""Configuration helpers for aiomql bot orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrackerSpec:
    """Bot-level position tracker scheduled alongside strategies."""

    name: str
    enabled: bool = False
    interval: int = 60
    on_separate_thread: bool = False
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionSpec:
    """Trading session window passed to aiomql when configured."""

    start: str
    end: str
    timezone: str = "UTC"
    name: str | None = None
    on_start: str | None = None
    on_end: str | None = None
    actions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategySpec:
    """A strategy instance template that can run on one or many symbols."""

    name: str
    type: str
    enabled: bool = True
    symbols: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    sessions: list[SessionSpec] = field(default_factory=list)


@dataclass(frozen=True)
class BotSettings:
    """Top-level bot settings loaded from JSON."""

    symbols: list[str] = field(default_factory=list)
    strategies: list[StrategySpec] = field(default_factory=list)
    sessions: list[SessionSpec] = field(default_factory=list)
    trackers: list[TrackerSpec] = field(default_factory=list)
    aiomql_config: dict[str, Any] = field(default_factory=dict)
    track_open_positions: bool = True
    symbol_preflight: bool = True


def load_bot_settings(path: str | Path) -> BotSettings:
    """Load bot settings from a JSON file."""
    with Path(path).open("r", encoding="utf-8") as file:
        raw = json.load(file)

    if not isinstance(raw, dict):
        raise ValueError("Bot settings must be a JSON object")

    global_symbols = _string_list(raw.get("symbols", []), field_name="symbols")
    raw_strategies = raw.get("strategies", [])
    if not isinstance(raw_strategies, list):
        raise ValueError("strategies must be a list")

    global_sessions = _parse_sessions(raw.get("sessions", []), field_name="sessions")
    strategies = [_parse_strategy_spec(item, global_symbols, global_sessions) for item in raw_strategies]
    return BotSettings(
        symbols=global_symbols,
        strategies=strategies,
        sessions=global_sessions,
        trackers=_parse_trackers(raw.get("trackers", []), field_name="trackers"),
        aiomql_config=_parse_mapping(raw.get("aiomql_config", {}), field_name="aiomql_config"),
        track_open_positions=bool(raw.get("track_open_positions", True)),
        symbol_preflight=bool(raw.get("symbol_preflight", True)),
    )


def _parse_strategy_spec(raw: object, global_symbols: list[str], global_sessions: list[SessionSpec]) -> StrategySpec:
    if not isinstance(raw, dict):
        raise ValueError("Each strategy spec must be a JSON object")

    name = str(raw.get("name") or raw.get("type") or "Strategy")
    strategy_type = str(raw.get("type") or "").strip().lower()
    if not strategy_type:
        raise ValueError(f"Strategy {name!r} is missing a type")

    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(f"Strategy {name!r} params must be a JSON object")

    symbols = _string_list(raw.get("symbols", global_symbols), field_name=f"{name}.symbols")
    if not symbols:
        raise ValueError(f"Strategy {name!r} must define at least one symbol")

    sessions = _parse_sessions(raw.get("sessions", global_sessions), field_name=f"{name}.sessions")
    return StrategySpec(
        name=name,
        type=strategy_type,
        enabled=bool(raw.get("enabled", True)),
        symbols=symbols,
        params=dict(params),
        sessions=sessions,
    )


def _string_list(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    result = [str(item).strip() for item in value]
    return [item for item in result if item]


def _parse_sessions(value: object, *, field_name: str) -> list[SessionSpec]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of session objects")

    sessions: list[SessionSpec] = []
    for index, raw in enumerate(value):
        if isinstance(raw, SessionSpec):
            sessions.append(raw)
            continue
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name}[{index}] must be a JSON object")

        start = str(raw.get("start") or "").strip()
        end = str(raw.get("end") or "").strip()
        if not start or not end:
            raise ValueError(f"{field_name}[{index}] must define start and end")

        timezone = str(raw.get("timezone") or "UTC").strip() or "UTC"
        name = raw.get("name")
        actions = _parse_mapping(raw.get("actions", {}), field_name=f"{field_name}[{index}].actions")
        sessions.append(
            SessionSpec(
                start=start,
                end=end,
                timezone=timezone,
                name=str(name).strip() if name is not None else None,
                on_start=_optional_string(raw.get("on_start")),
                on_end=_optional_string(raw.get("on_end")),
                actions={str(key): str(value) for key, value in actions.items()},
            )
        )
    return sessions


def _parse_trackers(value: object, *, field_name: str) -> list[TrackerSpec]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of tracker objects")

    trackers: list[TrackerSpec] = []
    for index, raw in enumerate(value):
        if isinstance(raw, TrackerSpec):
            trackers.append(raw)
            continue
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name}[{index}] must be a JSON object")

        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"{field_name}[{index}] must define name")

        params = raw.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"{field_name}[{index}].params must be a JSON object")

        trackers.append(
            TrackerSpec(
                name=name,
                enabled=bool(raw.get("enabled", False)),
                interval=int(raw.get("interval", 60)),
                on_separate_thread=bool(raw.get("on_separate_thread", False)),
                params=dict(params),
            )
        )
    return trackers


def _parse_mapping(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return dict(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None
