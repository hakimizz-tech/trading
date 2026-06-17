"""Configuration helpers for aiomql bot orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StrategySpec:
    """A strategy instance template that can run on one or many symbols."""

    name: str
    type: str
    enabled: bool = True
    symbols: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BotSettings:
    """Top-level bot settings loaded from JSON."""

    symbols: list[str] = field(default_factory=list)
    strategies: list[StrategySpec] = field(default_factory=list)
    track_open_positions: bool = True


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

    strategies = [_parse_strategy_spec(item, global_symbols) for item in raw_strategies]
    return BotSettings(
        symbols=global_symbols,
        strategies=strategies,
        track_open_positions=bool(raw.get("track_open_positions", True)),
    )


def _parse_strategy_spec(raw: object, global_symbols: list[str]) -> StrategySpec:
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

    return StrategySpec(
        name=name,
        type=strategy_type,
        enabled=bool(raw.get("enabled", True)),
        symbols=symbols,
        params=dict(params),
    )


def _string_list(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    result = [str(item).strip() for item in value]
    return [item for item in result if item]
