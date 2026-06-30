"""Broker-neutral execution assumptions and simulated order records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import floor, isfinite
from typing import Any, Mapping


class SimulatedOrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    BRACKET = "bracket"


class SimulatedOrderStatus(str, Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class IntrabarCollisionPolicy(str, Enum):
    """Assumption used when one bar touches stop loss and take profit."""

    STOP_FIRST = "stop_first"
    TARGET_FIRST = "target_first"
    CONSERVATIVE = "conservative"


@dataclass(frozen=True)
class BrokerProfile:
    """Tradable contract, cost, and margin rules for one instrument."""

    symbol: str
    contract_size: float = 100_000.0
    leverage: float = 30.0
    point: float = 0.00001
    pip_size: float = 0.0001
    tick_value: float = 1.0
    min_volume: float = 0.01
    max_volume: float = 100.0
    volume_step: float = 0.01
    spread_points: float = 0.0
    commission_per_lot_per_side: float = 0.0
    swap_long_per_lot_per_day: float = 0.0
    swap_short_per_lot_per_day: float = 0.0
    margin_call_level: float = 1.0
    stop_out_level: float = 0.5
    min_stop_distance_points: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "contract_size",
            "leverage",
            "point",
            "pip_size",
            "tick_value",
            "min_volume",
            "max_volume",
            "volume_step",
        ):
            _require_positive(getattr(self, name), name)
        for name in ("spread_points", "commission_per_lot_per_side", "min_stop_distance_points"):
            _require_non_negative(getattr(self, name), name)
        if self.min_volume > self.max_volume:
            raise ValueError("min_volume must be less than or equal to max_volume")
        if not 0 < self.stop_out_level <= self.margin_call_level:
            raise ValueError("stop_out_level must be positive and no greater than margin_call_level")

    def normalize_volume(self, requested: float) -> float:
        """Round volume down to broker step and cap it to broker limits."""
        if requested < self.min_volume:
            return 0.0
        capped = min(float(requested), self.max_volume)
        steps = floor((capped + 1e-12) / self.volume_step)
        normalized = steps * self.volume_step
        if normalized < self.min_volume:
            return 0.0
        return round(normalized, 10)

    def margin_required(self, price: float, volume: float, *, leverage: float | None = None) -> float:
        effective_leverage = self.leverage if leverage is None else float(leverage)
        _require_positive(effective_leverage, "leverage")
        return abs(float(price) * self.contract_size * float(volume) / effective_leverage)

    def price_pnl(self, *, direction: str, entry_price: float, exit_price: float, volume: float) -> float:
        movement = float(exit_price) - float(entry_price)
        if direction == "short":
            movement = -movement
        return movement / self.point * self.tick_value * float(volume)


@dataclass(frozen=True)
class ProviderDataModel:
    """Optional market/broker columns that refine historical execution rules.

    These fields let a dataset carry provider-specific constraints without
    coupling strategy code to one broker, exchange, or asset class.
    """

    tradable_column: str = "tradable"
    outage_column: str = "exchange_outage"
    borrow_available_column: str = "borrow_available"
    leverage_column: str = "leverage"
    max_volume_column: str = "max_order_volume"
    min_stop_points_column: str = "min_stop_points"
    split_factor_column: str = "split_factor"
    dividend_column: str = "dividend"
    halt_on_corporate_action: bool = True

    def is_tradable(self, bar: Mapping[str, Any]) -> bool:
        if _bar_bool(bar, self.outage_column, default=False):
            return False
        return _bar_bool(bar, self.tradable_column, default=True)

    def borrow_available(self, bar: Mapping[str, Any]) -> bool:
        return _bar_bool(bar, self.borrow_available_column, default=True)

    def corporate_action_detected(self, bar: Mapping[str, Any]) -> bool:
        split_factor = _bar_float(bar, self.split_factor_column)
        dividend = _bar_float(bar, self.dividend_column)
        return (split_factor is not None and split_factor != 1.0) or (
            dividend is not None and dividend != 0.0
        )

    def leverage_for(self, bar: Mapping[str, Any], profile: BrokerProfile) -> float:
        value = _bar_float(bar, self.leverage_column)
        return profile.leverage if value is None or value <= 0 else value

    def min_stop_points_for(self, bar: Mapping[str, Any], profile: BrokerProfile) -> float:
        value = _bar_float(bar, self.min_stop_points_column)
        if value is None or value < 0:
            return profile.min_stop_distance_points
        return max(value, profile.min_stop_distance_points)

    def max_volume_for(self, bar: Mapping[str, Any]) -> float | None:
        value = _bar_float(bar, self.max_volume_column)
        if value is None or value < 0:
            return None
        return value


@dataclass(frozen=True)
class ExecutionModel:
    """Configurable assumptions for simulated order processing."""

    latency_bars: int = 1
    order_expiry_bars: int = 3
    slippage_points: float = 0.0
    max_volume_participation: float = 1.0
    allow_partial_fills: bool = True
    rejection_probability: float = 0.0
    spread_column: str = "spread"
    slippage_column: str = "slippage_points"
    liquidity_column: str = "volume"
    reject_column: str = "reject_order"
    collision_policy: IntrabarCollisionPolicy = IntrabarCollisionPolicy.CONSERVATIVE
    provider_data: ProviderDataModel = field(default_factory=ProviderDataModel)
    seed: int = 7

    def __post_init__(self) -> None:
        if self.latency_bars < 0:
            raise ValueError("latency_bars must not be negative")
        if self.order_expiry_bars < 1:
            raise ValueError("order_expiry_bars must be at least 1")
        _require_non_negative(self.slippage_points, "slippage_points")
        if not 0 < self.max_volume_participation <= 1:
            raise ValueError("max_volume_participation must be in (0, 1]")
        if not 0 <= self.rejection_probability <= 1:
            raise ValueError("rejection_probability must be in [0, 1]")

    def spread_points_for(self, bar: Mapping[str, Any], profile: BrokerProfile) -> float:
        return _non_negative_bar_value(bar, self.spread_column, profile.spread_points)

    def slippage_points_for(self, bar: Mapping[str, Any]) -> float:
        return _non_negative_bar_value(bar, self.slippage_column, self.slippage_points)

    def available_volume(self, bar: Mapping[str, Any], profile: BrokerProfile) -> float:
        raw = bar.get(self.liquidity_column)
        if raw is None:
            available = profile.max_volume
            provider_cap = self.provider_data.max_volume_for(bar)
            return min(available, provider_cap) if provider_cap is not None else available
        try:
            value = float(raw)
        except (TypeError, ValueError):
            available = profile.max_volume
            provider_cap = self.provider_data.max_volume_for(bar)
            return min(available, provider_cap) if provider_cap is not None else available
        if not isfinite(value) or value <= 0:
            return 0.0
        available = value * self.max_volume_participation
        provider_cap = self.provider_data.max_volume_for(bar)
        return min(available, provider_cap) if provider_cap is not None else available


@dataclass(frozen=True)
class SimulatedOrder:
    """Order request submitted to an event-driven simulator."""

    order_id: str
    symbol: str
    direction: str
    order_type: SimulatedOrderType
    volume: float
    submitted_at: Any
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    expires_after_bars: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in {"long", "short"}:
            raise ValueError("direction must be 'long' or 'short'")
        _require_positive(self.volume, "volume")
        if self.order_type == SimulatedOrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required for a limit order")
        if self.order_type == SimulatedOrderType.STOP and self.stop_price is None:
            raise ValueError("stop_price is required for a stop order")
        for name in ("limit_price", "stop_price", "stop_loss", "take_profit"):
            value = getattr(self, name)
            if value is not None:
                _require_positive(value, name)


@dataclass(frozen=True)
class SimulatedFill:
    """Normalized fill generated by the event-driven simulator."""

    order_id: str
    timestamp: Any
    symbol: str
    direction: str
    volume: float
    price: float
    commission: float
    spread_cost: float
    slippage_cost: float
    status: SimulatedOrderStatus
    reason: str
    realized_pnl: float | None = None
    margin_used: float = 0.0


def execution_price(
    *,
    reference_price: float,
    direction: str,
    is_entry: bool,
    spread_points: float,
    slippage_points: float,
    point: float,
) -> tuple[float, float, float]:
    """Apply half-spread and adverse slippage to a reference price."""
    side = 1.0 if (direction == "long") == is_entry else -1.0
    spread_price = spread_points * point / 2.0
    slippage_price = slippage_points * point
    price = float(reference_price) + side * (spread_price + slippage_price)
    return price, spread_price, slippage_price


def _non_negative_bar_value(bar: Mapping[str, Any], name: str, default: float) -> float:
    raw = bar.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    return value if isfinite(value) and value >= 0 else float(default)


def _bar_float(bar: Mapping[str, Any], name: str) -> float | None:
    if name not in bar:
        return None
    try:
        value = float(bar[name])
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _bar_bool(bar: Mapping[str, Any], name: str, *, default: bool) -> bool:
    raw = bar.get(name)
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw.strip().lower() not in {"", "0", "false", "no", "n", "off"}
    return bool(raw)


def _require_positive(value: float, name: str) -> None:
    if not isfinite(float(value)) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


def _require_non_negative(value: float, name: str) -> None:
    if not isfinite(float(value)) or value < 0:
        raise ValueError(f"{name} must be non-negative and finite")
