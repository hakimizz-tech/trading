"""aiomql bot runner for one or many strategy specs.

This entry point is intended for the later Windows/MetaTrader 5 environment.
It is safe by default: strategies run in dry-run mode unless their params set
``live_trading`` to true and the strategy execution gates pass.
"""

from __future__ import annotations
import argparse
from datetime import time
from importlib import import_module
import logging
from pathlib import Path
from types import ModuleType
from typing import Any
from bot_config import BotSettings, SessionSpec, StrategySpec, TrackerSpec, load_bot_settings
from execution.trackers import build_tracker_callable
from strategy_registry import load_strategy_class


logger = logging.getLogger(__name__)


def build_strategy_instances(settings: BotSettings) -> list[Any]:
    """Build aiomql Strategy instances from settings."""
    strategies: list[Any] = []

    for spec in settings.strategies:
        if not spec.enabled:
            logger.info("Skipping disabled strategy: %s", spec.name)
            continue
        strategy_cls = load_strategy_class(spec.type)
        strategies.extend(_build_for_symbols(strategy_cls, spec))

    if not strategies:
        raise ValueError("No enabled strategies were configured")
    return strategies


def run_bot(settings: BotSettings) -> None:
    """Create and execute an aiomql Bot."""
    bot = build_bot(settings)
    bot.execute()


async def start_bot(settings: BotSettings) -> None:
    """Create and start an aiomql Bot from an existing async context."""
    bot = build_bot(settings)
    await bot.start()


def build_bot(settings: BotSettings) -> Any:
    """Build an aiomql Bot with strategies and configured background work."""
    aiomql = _load_aiomql()
    configure_aiomql(aiomql, settings)
    if settings.symbol_preflight:
        preflight_mt5_symbols(settings)

    bot = aiomql.Bot()
    bot.add_strategies(build_strategy_instances(settings))

    if settings.track_open_positions:
        bot.add_coroutine(coroutine=aiomql.OpenPositionsTracker(autocommit=True).track, on_separate_thread=True)
    add_configured_trackers(bot, settings.trackers)

    return bot


def _build_for_symbols(strategy_cls: type[Any], spec: StrategySpec) -> list[Any]:
    aiomql = _load_aiomql()
    sessions = _build_sessions(aiomql, spec.sessions)

    return [
        strategy_cls(
            symbol=_build_symbol(aiomql, symbol_name, spec.symbol_class),
            params=spec.params,
            sessions=sessions,
            name=f"{spec.name}:{symbol_name}",
        )
        for symbol_name in spec.symbols
    ]


def _build_symbol(aiomql: ModuleType, symbol_name: str, symbol_class: str = "forex") -> Any:
    """Build a documented aiomql Symbol wrapper for one broker symbol."""
    normalized = symbol_class.strip().lower()
    if normalized == "forex":
        symbol_cls = getattr(aiomql, "ForexSymbol", None)
        if symbol_cls is None:
            raise RuntimeError("symbol_class='forex' requires aiomql.ForexSymbol support.")
        return symbol_cls(name=symbol_name)
    if normalized in {"symbol", "generic"}:
        symbol_cls = getattr(aiomql, "Symbol", None)
        if symbol_cls is None:
            raise RuntimeError("symbol_class='symbol' requires aiomql.Symbol support.")
        return symbol_cls(name=symbol_name)
    raise ValueError("symbol_class must be one of: forex, symbol, generic")


def add_configured_trackers(bot: Any, trackers: list[TrackerSpec]) -> None:
    """Schedule configured bot-level trackers."""
    for spec in trackers:
        if not spec.enabled:
            logger.info("Skipping disabled tracker: %s", spec.name)
            continue
        tracker = build_tracker_callable(spec.name, spec.params)
        # Auto-close trackers stay disabled/signal-only by default until demo validation proves they behave safely.
        bot.add_coroutine(coroutine=tracker, interval=spec.interval, on_separate_thread=spec.on_separate_thread)


def configure_aiomql(aiomql: ModuleType, settings: BotSettings) -> Any | None:
    """Apply optional aiomql Config settings without requiring credentials in source."""
    if not settings.aiomql_config:
        return None

    config_cls = getattr(aiomql, "Config", None)
    if config_cls is None:
        raise RuntimeError("Configured aiomql_config requires aiomql.Config support.")
    config_settings = dict(settings.aiomql_config)
    load_keys = {"filename", "config_file", "root"}
    if load_keys & set(config_settings):
        config = config_cls()
        load_config = getattr(config, "load_config", None)
        if not callable(load_config):
            return config_cls(**config_settings)
        return load_config(**config_settings)
    return config_cls(**config_settings)


def _load_aiomql() -> ModuleType:
    """Load aiomql lazily because it is only available in the MT5 runtime."""
    try:
        return import_module("aiomql")
    except ImportError as exc:
        raise RuntimeError(
            "aiomql is not available in this environment. Bot execution requires "
            "Windows, Python 3.13+, MetaTrader 5, and the aiomql package."
        ) from exc


def preflight_mt5_symbols(settings: BotSettings, *, mt5: Any | None = None) -> None:
    """Fail fast when configured MT5 symbols are missing or not selectable."""
    symbols = sorted({symbol for spec in settings.strategies if spec.enabled for symbol in spec.symbols})
    if not symbols:
        return

    mt5_module = mt5 or _load_mt5()
    if not mt5_module.initialize():
        raise RuntimeError(f"MT5 initialize failed during symbol preflight: {mt5_module.last_error()}")

    try:
        problems: list[str] = []
        for symbol in symbols:
            info = mt5_module.symbol_info(symbol)
            if info is None:
                problems.append(f"{symbol}: not found")
                continue
            if not bool(getattr(info, "visible", False)) and not mt5_module.symbol_select(symbol, True):
                problems.append(f"{symbol}: found but could not select in MarketWatch ({mt5_module.last_error()})")

        if problems:
            detail = "; ".join(problems)
            raise RuntimeError(
                "MT5 symbol preflight failed. Check broker suffixes such as EURUSDm or XAUUSD.pro. "
                f"Issues: {detail}"
            )
    finally:
        mt5_module.shutdown()


def _load_mt5() -> ModuleType:
    try:
        return import_module("MetaTrader5")
    except ImportError as exc:
        raise RuntimeError(
            "MetaTrader5 is not available for symbol preflight. Run bot execution on the Windows/MT5 "
            "runtime or set symbol_preflight to false only after manually checking broker symbols."
        ) from exc


def _build_sessions(aiomql: ModuleType, session_specs: list[SessionSpec]) -> Any | None:
    if not session_specs:
        return None

    session_cls = getattr(aiomql, "Session", None)
    sessions_cls = getattr(aiomql, "Sessions", None)
    if session_cls is None or sessions_cls is None:
        raise RuntimeError("Configured sessions require aiomql.Session and aiomql.Sessions support.")

    sessions = [_build_session(session_cls, spec) for spec in session_specs]
    try:
        return sessions_cls(sessions=sessions)
    except TypeError:
        return sessions_cls(*sessions)


def _build_session(session_cls: Any, spec: SessionSpec) -> Any:
    kwargs = {
        "start": _parse_session_time(spec.start),
        "end": _parse_session_time(spec.end),
        "timezone": spec.timezone,
    }
    if spec.name is not None:
        kwargs["name"] = spec.name
    if spec.on_start is not None:
        kwargs["on_start"] = spec.on_start
    if spec.on_end is not None:
        kwargs["on_end"] = spec.on_end
    kwargs.update(_resolve_session_actions(spec.actions))
    try:
        return session_cls(**kwargs)
    except TypeError:
        kwargs.pop("timezone", None)
        return session_cls(**kwargs)


def _parse_session_time(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) not in {2, 3}:
        raise ValueError(f"Invalid session time: {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    second = int(parts[2]) if len(parts) == 3 else 0
    return time(hour=hour, minute=minute, second=second)


def _resolve_session_actions(actions: dict[str, str]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for name, path in actions.items():
        module_name, _, attr = path.partition(":")
        if not module_name or not attr:
            raise ValueError(f"Invalid session action path for {name!r}: {path!r}")
        resolved[name] = getattr(import_module(module_name), attr)
    return resolved


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run aiomql strategy bot from JSON settings.")
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("bot_settings.example.json"),
        help="Path to bot settings JSON.",
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_bot_settings(args.settings)
    run_bot(settings)


if __name__ == "__main__":
    main()
