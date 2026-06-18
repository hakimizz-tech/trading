"""Central registry for executable strategy classes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any


StrategyLoader = Callable[[], type[Any]]


@dataclass(frozen=True)
class StrategyRegistration:
    """Lazy strategy registration used by bot orchestration."""

    key: str
    import_path: str
    aliases: tuple[str, ...] = ()

    def load(self) -> type[Any]:
        module_name, _, attr = self.import_path.partition(":")
        if not module_name or not attr:
            raise ValueError(f"Invalid strategy import path: {self.import_path!r}")
        return getattr(import_module(module_name), attr)


STRATEGY_REGISTRATIONS: tuple[StrategyRegistration, ...] = (
    StrategyRegistration(
        key="bollinger",
        aliases=("bollinger_bands",),
        import_path="strategies.BollingerBand.execution.aiomql_strategy:BollingerBandsAiomqlStrategy",
    ),
)


def strategy_registry() -> dict[str, StrategyLoader]:
    """Return normalized strategy keys mapped to lazy class loaders."""
    registry: dict[str, StrategyLoader] = {}
    for registration in STRATEGY_REGISTRATIONS:
        keys = (registration.key, *registration.aliases)
        for key in keys:
            registry[normalize_strategy_type(key)] = registration.load
    return registry


def load_strategy_class(strategy_type: str) -> type[Any]:
    """Load the strategy class registered for ``strategy_type``."""
    registry = strategy_registry()
    normalized = normalize_strategy_type(strategy_type)
    loader = registry.get(normalized)
    if loader is None:
        available = ", ".join(sorted(registry))
        raise ValueError(f"Unknown strategy type {strategy_type!r}. Available: {available}")
    return loader()


def normalize_strategy_type(value: str) -> str:
    return value.strip().lower().replace("-", "_")
