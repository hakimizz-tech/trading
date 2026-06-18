"""Broker-aware fixed-fractional position sizing."""

from __future__ import annotations

import math
from dataclasses import dataclass

from execution.state import SymbolContract


@dataclass(frozen=True)
class PositionSizeResult:
    accepted: bool
    volume: float
    risk_amount: float
    stop_distance_price: float
    stop_distance_pips: float
    risk_per_lot: float
    reason: str | None = None


def calculate_risk_position_size(
    *,
    equity: float,
    risk_per_trade: float,
    entry_price: float,
    stop_price: float,
    contract: SymbolContract,
    min_volume: float | None = None,
    max_volume: float | None = None,
    volume_step: float | None = None,
) -> PositionSizeResult:
    """Calculate volume so stop-loss risk is capped by ``risk_per_trade``.

    ``tick_value`` is interpreted as account-currency value per pip per 1.0 lot.
    The final volume is rounded down to the broker step to avoid exceeding the
    requested risk.
    """
    validation_error = _validate_inputs(equity, risk_per_trade, entry_price, stop_price, contract)
    if validation_error is not None:
        return _rejected(validation_error)

    min_lot = min_volume if min_volume is not None else contract.min_lot
    max_lot = max_volume if max_volume is not None else contract.max_lot
    lot_step = volume_step if volume_step is not None else contract.lot_step
    if min_lot <= 0 or max_lot <= 0 or lot_step <= 0:
        return _rejected("volume limits and step must be positive")
    if min_lot > max_lot:
        return _rejected("min_volume must be less than or equal to max_volume")

    stop_distance_price = abs(entry_price - stop_price)
    stop_distance_pips = stop_distance_price / contract.pip_size
    risk_amount = equity * risk_per_trade
    risk_per_lot = stop_distance_pips * contract.tick_value
    if risk_per_lot <= 0:
        return _rejected("risk_per_lot must be positive")

    raw_volume = risk_amount / risk_per_lot
    stepped_volume = _round_down_to_step(raw_volume, lot_step)
    capped_volume = min(stepped_volume, max_lot)
    volume = _round_down_to_step(capped_volume, lot_step)

    if volume < min_lot:
        return PositionSizeResult(
            accepted=False,
            volume=0.0,
            risk_amount=risk_amount,
            stop_distance_price=stop_distance_price,
            stop_distance_pips=stop_distance_pips,
            risk_per_lot=risk_per_lot,
            reason="calculated volume is below minimum volume",
        )

    return PositionSizeResult(
        accepted=True,
        volume=round(volume, _step_decimals(lot_step)),
        risk_amount=risk_amount,
        stop_distance_price=stop_distance_price,
        stop_distance_pips=stop_distance_pips,
        risk_per_lot=risk_per_lot,
    )


def _validate_inputs(
    equity: float,
    risk_per_trade: float,
    entry_price: float,
    stop_price: float,
    contract: SymbolContract,
) -> str | None:
    if equity <= 0:
        return "equity must be positive"
    if risk_per_trade <= 0 or risk_per_trade > 0.05:
        return "risk_per_trade must be in the range (0, 0.05]"
    if entry_price <= 0 or stop_price <= 0:
        return "entry_price and stop_price must be positive"
    if entry_price == stop_price:
        return "entry_price and stop_price must differ"
    if contract.tick_value <= 0:
        return "contract tick_value must be positive"
    if contract.pip_size <= 0:
        return "contract pip_size must be positive"
    return None


def _rejected(reason: str) -> PositionSizeResult:
    return PositionSizeResult(
        accepted=False,
        volume=0.0,
        risk_amount=0.0,
        stop_distance_price=0.0,
        stop_distance_pips=0.0,
        risk_per_lot=0.0,
        reason=reason,
    )


def _round_down_to_step(value: float, step: float) -> float:
    if value <= 0:
        return 0.0
    return math.floor((value / step) + 1e-12) * step


def _step_decimals(step: float) -> int:
    text = f"{step:.12f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.rsplit(".", 1)[1])
