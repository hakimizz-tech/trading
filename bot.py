"""aiomql bot runner for one or many strategy specs.

This entry point is intended for the later Windows/MetaTrader 5 environment.
It is safe by default: strategies run in dry-run mode unless their params set
``live_trading`` to true and the strategy execution gates pass.
"""

from __future__ import annotations
import argparse
import logging
from pathlib import Path
from typing import Any
from bot_config import BotSettings, StrategySpec, load_bot_settings
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
    from aiomql import Bot, OpenPositionsTracker

    bot = Bot()
    bot.add_strategies(build_strategy_instances(settings))

    if settings.track_open_positions:
        bot.add_coroutine(coroutine=OpenPositionsTracker(autocommit=True).track, on_separate_thread=True)

    bot.execute()


def _build_for_symbols(strategy_cls: type[Any], spec: StrategySpec) -> list[Any]:
    from aiomql import ForexSymbol

    return [
        strategy_cls(
            symbol=ForexSymbol(name=symbol_name),
            params=spec.params,
            name=f"{spec.name}:{symbol_name}",
        )
        for symbol_name in spec.symbols
    ]


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
