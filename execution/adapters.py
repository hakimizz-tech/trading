"""Broker adapter contracts for current and future execution backends.

The project currently executes through MetaTrader 5 via aiomql, but strategy
logic, risk gates, journaling, and accounting should not depend on one broker
SDK.  Future adapters for Solana DEX execution or stock brokers can implement
these protocols and return the same normalized state objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable
from execution.state import BrokerFill, BrokerOrderCancelResult, BrokerOrderCheck, BrokerPendingOrder, BrokerSnapshot


@runtime_checkable
class BrokerDataAdapter(Protocol):
    """Read-only broker state needed by live execution gates."""

    async def snapshot(self, *, symbol: str, strategy: str | None = None) -> BrokerSnapshot:
        """Return account, contract, spread, and open-position state."""
        ...

    async def history(self, *, date_from: object, date_to: object, group: str | None = None) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
        """Return historical deals and orders as mapping-like records."""
        ...


@runtime_checkable
class BrokerExecutionAdapter(Protocol):
    """Order execution boundary for broker-specific implementations."""

    async def place_market_order(
        self,
        *,
        symbol: str,
        direction: str,
        volume: float,
        parameters: Mapping[str, Any] | None = None,
    ) -> BrokerFill | None:
        """Place an order and return a normalized fill when the broker confirms one."""
        ...

    async def check_market_order(
        self,
        *,
        symbol: str,
        direction: str,
        volume: float,
        parameters: Mapping[str, Any] | None = None,
    ) -> BrokerOrderCheck:
        """Validate margin/profit/loss assumptions before placing an order."""
        ...

    async def pending_orders(
        self,
        *,
        symbol: str | None = None,
        strategy: str | None = None,
    ) -> list[BrokerPendingOrder]:
        """Return active pending orders known to the broker."""
        ...

    async def cancel_order(
        self,
        *,
        ticket: str,
        symbol: str | None = None,
    ) -> BrokerOrderCancelResult:
        """Cancel an active pending order by broker ticket."""
        ...


@runtime_checkable
class BrokerAdapter(BrokerDataAdapter, BrokerExecutionAdapter, Protocol):
    """Combined broker interface for strategy execution backends."""
