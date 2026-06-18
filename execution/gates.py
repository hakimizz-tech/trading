"""Live execution gate helpers independent of aiomql."""

from __future__ import annotations

from dataclasses import dataclass, field

from execution.sizing import calculate_risk_position_size
from execution.state import BrokerSnapshot


@dataclass(frozen=True)
class ExecutionGateResult:
    allowed: bool
    reason: str | None = None
    volume: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def evaluate_live_execution_gate(
    *,
    trade_parameters: dict[str, object],
    snapshot: BrokerSnapshot,
    strategy: str,
    symbol: str,
    max_spread: float | None,
    max_open_positions: int,
    max_daily_loss_pct: float | None,
    max_daily_loss_amount: float | None,
    daily_net_pnl: float,
    use_risk_sizing: bool,
    fixed_volume: float,
    risk_per_trade: float,
    min_volume: float | None,
    max_volume: float | None,
    volume_step: float | None,
) -> ExecutionGateResult:
    """Evaluate broker state and return final order volume if allowed."""
    if max_open_positions < 1:
        return ExecutionGateResult(False, "max_open_positions must be at least 1")
    if max_spread is not None and snapshot.current_spread is not None and snapshot.current_spread > max_spread:
        return ExecutionGateResult(False, "current spread exceeds max_spread")
    open_positions = snapshot.positions_for(symbol=symbol, strategy=strategy)
    if len(open_positions) >= max_open_positions:
        return ExecutionGateResult(False, "max open positions reached")

    daily_loss_limit = _daily_loss_limit(snapshot.account.equity, max_daily_loss_pct, max_daily_loss_amount)
    if daily_loss_limit is not None and daily_net_pnl <= -daily_loss_limit:
        return ExecutionGateResult(False, "max daily loss reached")

    if not use_risk_sizing:
        if fixed_volume <= 0:
            return ExecutionGateResult(False, "fixed_volume must be positive")
        return ExecutionGateResult(True, volume=fixed_volume)

    entry_price = _float_param(trade_parameters, "entry_price")
    stop_price = _float_param(trade_parameters, "stop_loss_price")
    if entry_price is None or stop_price is None:
        return ExecutionGateResult(False, "entry_price and stop_loss_price are required for risk sizing")

    size = calculate_risk_position_size(
        equity=snapshot.account.equity,
        risk_per_trade=risk_per_trade,
        entry_price=entry_price,
        stop_price=stop_price,
        contract=snapshot.contract,
        min_volume=min_volume,
        max_volume=max_volume,
        volume_step=volume_step,
    )
    if not size.accepted:
        return ExecutionGateResult(False, size.reason or "risk sizing rejected trade")

    return ExecutionGateResult(
        True,
        volume=size.volume,
        metadata={
            "risk_amount": size.risk_amount,
            "stop_distance_price": size.stop_distance_price,
            "stop_distance_pips": size.stop_distance_pips,
            "risk_per_lot": size.risk_per_lot,
        },
    )


def _daily_loss_limit(
    equity: float,
    max_daily_loss_pct: float | None,
    max_daily_loss_amount: float | None,
) -> float | None:
    limits = []
    if max_daily_loss_pct is not None and max_daily_loss_pct > 0:
        limits.append(equity * max_daily_loss_pct)
    if max_daily_loss_amount is not None and max_daily_loss_amount > 0:
        limits.append(max_daily_loss_amount)
    return min(limits) if limits else None


def _float_param(values: dict[str, object], key: str) -> float | None:
    try:
        value = float(values[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value
