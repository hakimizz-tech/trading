"""Forex spread, slippage, and break-even cost helpers."""

from __future__ import annotations

from dataclasses import dataclass


PAPER_FOREX_COSTS: dict[str, tuple[float, float]] = {
    "EURUSD": (1.2, 0.0001),
    "JPYUSD": (1.5, 0.00001),
    "USDJPY": (1.5, 0.00001),
    "AUDUSD": (2.0, 0.0001),
    "CHFUSD": (2.5, 0.0001),
    "USDCHF": (2.5, 0.0001),
    "CNYUSD": (3.0, 0.0001),
    "USDCNY": (3.0, 0.0001),
    "MXNUSD": (8.0, 0.00005),
    "USDMXN": (8.0, 0.00005),
    "ZARUSD": (8.0, 0.00005),
    "USDZAR": (8.0, 0.00005),
    "TRYUSD": (3.0, 0.0001),
    "USDTRY": (3.0, 0.0001),
}

USD_BASE_TO_PAPER_SYMBOL: dict[str, str] = {
    "USDJPY": "JPYUSD",
    "USDCHF": "CHFUSD",
    "USDCNY": "CNYUSD",
    "USDMXN": "MXNUSD",
    "USDZAR": "ZARUSD",
    "USDTRY": "TRYUSD",
}


@dataclass(frozen=True)
class ForexCostSpec:
    """Pair-specific transaction-cost model from the paper."""

    spread_pips: float
    pip_value: float
    commission_pct: float = 0.0
    slippage_pct: float = 0.0

    def one_way_pct(self, price: float) -> float:
        if price <= 0:
            return float("nan")
        spread_pct = (self.spread_pips * self.pip_value) / price
        return spread_pct + self.commission_pct + self.slippage_pct

    def round_trip_pct(self, price: float) -> float:
        return 2.0 * self.one_way_pct(price)


def cost_spec_for_symbol(symbol: str, *, commission_pct: float = 0.0, slippage_pct: float = 0.0) -> ForexCostSpec:
    """Return pair-specific costs, falling back to a liquid-major assumption."""
    spread_pips, pip_value = PAPER_FOREX_COSTS.get(symbol.upper(), (2.0, 0.0001))
    return ForexCostSpec(
        spread_pips=spread_pips,
        pip_value=pip_value,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    )


def break_even_move_pct(price: float, cost_spec: ForexCostSpec, *, round_trip: bool = True, buffer_pct: float = 0.0) -> float:
    """Return the minimum move needed to clear modeled execution costs."""
    cost = cost_spec.round_trip_pct(price) if round_trip else cost_spec.one_way_pct(price)
    return cost + buffer_pct
