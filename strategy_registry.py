"""Registry and discovery helpers for executable strategy classes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from inspect import isclass
from pkgutil import iter_modules
import re
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


STRATEGY_ALIASES: dict[str, tuple[str, ...]] = {
    "BollingerBand": ("bollinger", "bollinger_bands"),
    "ScalperMajorHighVolatility": ("scalper_major", "scalper_major_high_volatility"),
}


def strategy_registry() -> dict[str, StrategyLoader]:
    """Return normalized strategy keys mapped to lazy class loaders."""
    registry: dict[str, StrategyLoader] = {}
    for registration in discover_strategy_registrations():
        keys = (registration.key, *registration.aliases)
        for key in keys:
            registry[normalize_strategy_type(key)] = registration.load
    return registry


def load_strategy_class(strategy_type: str) -> type[Any]:
    """Load the strategy class registered for ``strategy_type``."""
    if ":" in strategy_type:
        return StrategyRegistration(key=strategy_type, import_path=strategy_type).load()

    registry = strategy_registry()
    normalized = normalize_strategy_type(strategy_type)
    loader = registry.get(normalized)
    if loader is None:
        available = ", ".join(sorted(registry))
        raise ValueError(f"Unknown strategy type {strategy_type!r}. Available: {available}")
    return loader()


def discover_strategy_registrations() -> tuple[StrategyRegistration, ...]:
    """Discover strategy packages that expose an aiomql execution adapter."""
    return tuple(
        registration
        for package_name in _iter_strategy_package_names()
        if (registration := _registration_for_package(package_name)) is not None
    )


def normalize_strategy_type(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _iter_strategy_package_names() -> tuple[str, ...]:
    strategies = import_module("strategies")
    package_names = getattr(strategies, "__all__", None)
    if package_names is not None:
        return tuple(str(name) for name in package_names)

    strategy_paths = getattr(strategies, "__path__", ())
    return tuple(module.name for module in iter_modules(strategy_paths) if module.ispkg)


def _registration_for_package(package_name: str) -> StrategyRegistration | None:
    try:
        execution_module = import_module(f"strategies.{package_name}.execution")
    except ModuleNotFoundError as exc:
        if exc.name == f"strategies.{package_name}.execution":
            return None
        raise

    strategy_class = _select_strategy_class(execution_module)
    if strategy_class is None:
        return None

    key = _camel_to_snake(package_name)
    aliases = tuple(
        alias
        for alias in (*STRATEGY_ALIASES.get(package_name, ()), package_name)
        if normalize_strategy_type(alias) != normalize_strategy_type(key)
    )
    return StrategyRegistration(
        key=key,
        aliases=aliases,
        import_path=f"{strategy_class.__module__}:{strategy_class.__name__}",
    )


def _select_strategy_class(module: Any) -> type[Any] | None:
    exported_names = getattr(module, "__all__", None)
    names = tuple(exported_names) if exported_names is not None else tuple(dir(module))
    classes = [
        getattr(module, name)
        for name in names
        if isclass(getattr(module, name, None)) and str(name).endswith(("AiomqlStrategy", "Strategy"))
    ]
    if not classes:
        return None

    aiomql_classes = [cls for cls in classes if cls.__name__.endswith("AiomqlStrategy")]
    candidates = aiomql_classes or classes
    if len(candidates) == 1:
        return candidates[0]

    raise ValueError(f"Multiple executable strategy classes exported by {module.__name__}: {candidates!r}")


def _camel_to_snake(value: str) -> str:
    words = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", words)
    return normalize_strategy_type(words)
