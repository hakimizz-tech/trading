"""Broker/account state interfaces independent of aiomql."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountSnapshot:
    """Normalized account state needed by live risk gates."""

    equity: float
    balance: float
    free_margin: float
    currency: str = "BASE"

    def __post_init__(self) -> None:
        _require_non_negative(self.equity, "equity")
        _require_non_negative(self.balance, "balance")
        _require_non_negative(self.free_margin, "free_margin")


@dataclass(frozen=True)
class SymbolContract:
    """Normalized symbol contract details for broker-aware sizing."""

    symbol: str
    point: float
    pip_size: float
    tick_value: float
    min_lot: float
    max_lot: float
    lot_step: float
    contract_size: float | None = None
    currency_profit: str | None = None

    def __post_init__(self) -> None:
        _require_positive(self.point, "point")
        _require_positive(self.pip_size, "pip_size")
        _require_positive(self.tick_value, "tick_value")
        _require_positive(self.min_lot, "min_lot")
        _require_positive(self.max_lot, "max_lot")
        _require_positive(self.lot_step, "lot_step")
        if self.min_lot > self.max_lot:
            raise ValueError("min_lot must be less than or equal to max_lot")


@dataclass(frozen=True)
class OpenPosition:
    """Normalized open broker position."""

    ticket: str
    symbol: str
    direction: str
    volume: float
    entry_price: float
    current_price: float | None = None
    profit: float = 0.0
    strategy: str | None = None
    magic: int | None = None
    comment: str | None = None

    def __post_init__(self) -> None:
        if self.direction not in {"long", "short"}:
            raise ValueError("direction must be 'long' or 'short'")
        _require_positive(self.volume, "volume")
        _require_positive(self.entry_price, "entry_price")


@dataclass(frozen=True)
class BrokerSnapshot:
    """Complete risk-gate snapshot for a strategy-symbol decision."""

    account: AccountSnapshot
    contract: SymbolContract
    open_positions: tuple[OpenPosition, ...] = ()
    current_spread: float | None = None

    def __post_init__(self) -> None:
        if self.current_spread is not None:
            _require_non_negative(self.current_spread, "current_spread")

    def positions_for(self, *, symbol: str | None = None, strategy: str | None = None) -> tuple[OpenPosition, ...]:
        """Return open positions matching optional symbol and strategy filters."""
        positions = self.open_positions
        if symbol is not None:
            positions = tuple(position for position in positions if position.symbol == symbol)
        if strategy is not None:
            positions = tuple(position for position in positions if position.strategy == strategy)
        return positions


@dataclass(frozen=True)
class BrokerFill:
    """Normalized broker fill/close event extracted from an order/deal result."""

    external_id: str
    symbol: str
    direction: str
    volume: float
    price: float
    occurred_at: str | None = None
    realized_pnl: float | None = None
    commission: float = 0.0
    swap: float = 0.0
    entry_price: float | None = None
    exit_price: float | None = None
    raw: object | None = None

    def __post_init__(self) -> None:
        if not self.external_id:
            raise ValueError("external_id is required")
        if self.direction not in {"long", "short"}:
            raise ValueError("direction must be 'long' or 'short'")
        _require_positive(self.volume, "volume")
        _require_positive(self.price, "price")


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_non_negative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must not be negative")
