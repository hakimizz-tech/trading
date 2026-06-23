"""Paper-style basket recovery simulator for Scalper Major research.

This module deliberately keeps the grid/martingale engine separate from the
signal-only backtest. The goal is to make recovery risk measurable before any
aiomql adapter is allowed to place live orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from strategies.ScalperMajorHighVolatility.core import (
    ScalperMajorConfig,
    ScalperMajorResult,
    compute_scalper_major_indicators,
    generate_scalper_major_signals,
    recovery_lot_sequence,
)


Direction = Literal["long", "short"]


@dataclass(frozen=True)
class RecoveryConfig:
    """Broker-style assumptions for the basket recovery simulator."""

    initial_cash: float = 20_000.0
    base_lot: float = 0.01
    max_positions_per_direction: int = 14
    grid_atr_multiple: float = 1.0
    profit_to_loss_ratio: float = 3.0
    pip_size: float = 0.0001
    pip_value_per_lot: float = 10.0
    commission_per_lot: float = 7.0
    contract_size: float = 100_000.0
    leverage: float = 100.0
    max_global_drawdown: float = 0.25
    max_symbol_drawdown: float = 0.10
    allow_hedged_baskets: bool = True

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.base_lot <= 0:
            raise ValueError("base_lot must be positive")
        if self.max_positions_per_direction <= 0:
            raise ValueError("max_positions_per_direction must be positive")
        if self.grid_atr_multiple <= 0 or self.profit_to_loss_ratio <= 0:
            raise ValueError("grid_atr_multiple and profit_to_loss_ratio must be positive")
        if self.pip_size <= 0 or self.pip_value_per_lot <= 0:
            raise ValueError("pip_size and pip_value_per_lot must be positive")
        if self.contract_size <= 0 or self.leverage <= 0:
            raise ValueError("contract_size and leverage must be positive")


@dataclass(frozen=True)
class BasketPosition:
    """One simulated broker position."""

    direction: Direction
    entry_timestamp: object
    entry_price: float
    volume: float
    sequence_index: int


def backtest_scalper_major_recovery(
    ohlcv: pd.DataFrame,
    strategy_config: ScalperMajorConfig | None = None,
    recovery_config: RecoveryConfig | None = None,
) -> ScalperMajorResult:
    """Run a multi-position grid/martingale recovery simulation."""
    cfg = strategy_config or ScalperMajorConfig()
    rec = recovery_config or RecoveryConfig(initial_cash=cfg.initial_cash, base_lot=cfg.base_lot)
    data = cfg_validate_ohlcv(ohlcv)
    indicators = compute_scalper_major_indicators(data, cfg)
    signals = generate_scalper_major_signals(data, cfg)
    lot_sequence = recovery_lot_sequence(rec.base_lot, max_positions=rec.max_positions_per_direction)

    realized_equity = rec.initial_cash
    equity = pd.Series(rec.initial_cash, index=data.index, name="equity")
    returns = pd.Series(0.0, index=data.index, name="returns")
    drawdown = pd.Series(0.0, index=data.index, name="drawdown")
    positions: list[BasketPosition] = []
    trade_rows: list[dict[str, object]] = []

    for i, timestamp in enumerate(data.index):
        price = float(data["close"].iloc[i])
        atr = float(indicators["atr"].iloc[i]) if pd.notna(indicators["atr"].iloc[i]) else np.nan
        floating = _floating_pnl(positions, price, rec) - _open_commission(positions, rec)
        current_equity = realized_equity + floating
        peak = max(float(equity.iloc[: i + 1].max()), rec.initial_cash)
        current_drawdown = current_equity / peak - 1.0

        if positions and _basket_close_allowed(positions, price, rec):
            close_pnl = floating
            realized_equity += close_pnl
            for position in positions:
                trade_rows.append(
                    {
                        "entry_timestamp": position.entry_timestamp,
                        "exit_timestamp": timestamp,
                        "direction": position.direction,
                        "entry_price": position.entry_price,
                        "exit_price": price,
                        "volume": position.volume,
                        "sequence_index": position.sequence_index,
                        "return_pct": _position_return_pct(position, price),
                        "pnl": _position_pnl(position, price, rec) - position.volume * rec.commission_per_lot,
                        "exit_reason": "basket_target",
                    }
                )
            positions = []
            floating = 0.0
            current_equity = realized_equity

        if current_drawdown > -rec.max_global_drawdown and i >= cfg.required_history and pd.notna(atr):
            if bool(signals["long_entry"].iloc[i]):
                positions = _maybe_add_position("long", timestamp, price, atr, positions, lot_sequence, rec)
            if bool(signals["short_entry"].iloc[i]):
                positions = _maybe_add_position("short", timestamp, price, atr, positions, lot_sequence, rec)

        equity.iloc[i] = current_equity
        if i > 0:
            returns.iloc[i] = equity.iloc[i] / equity.iloc[i - 1] - 1.0
        drawdown.iloc[i] = equity.iloc[i] / max(float(equity.iloc[: i + 1].max()), rec.initial_cash) - 1.0

    if positions:
        timestamp = data.index[-1]
        price = float(data["close"].iloc[-1])
        floating = _floating_pnl(positions, price, rec) - _open_commission(positions, rec)
        realized_equity += floating
        equity.iloc[-1] = realized_equity
        returns.iloc[-1] = equity.iloc[-1] / equity.iloc[-2] - 1.0 if len(equity) > 1 else 0.0
        drawdown.iloc[-1] = equity.iloc[-1] / max(float(equity.max()), rec.initial_cash) - 1.0
        for position in positions:
            trade_rows.append(
                {
                    "entry_timestamp": position.entry_timestamp,
                    "exit_timestamp": timestamp,
                    "direction": position.direction,
                    "entry_price": position.entry_price,
                    "exit_price": price,
                    "volume": position.volume,
                    "sequence_index": position.sequence_index,
                    "return_pct": _position_return_pct(position, price),
                    "pnl": _position_pnl(position, price, rec) - position.volume * rec.commission_per_lot,
                    "exit_reason": "forced_end_of_data",
                }
            )

    trades = pd.DataFrame(trade_rows)
    metrics = _metrics(returns, equity, drawdown, trades)
    metrics.update(
        {
            "mode": "basket_recovery",
            "max_recovery_positions": rec.max_positions_per_direction,
            "base_lot": rec.base_lot,
        }
    )
    return ScalperMajorResult(data, indicators, signals, returns, equity, drawdown, trades, metrics, cfg)


def cfg_validate_ohlcv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    from strategies.ScalperMajorHighVolatility.core import validate_ohlcv

    return validate_ohlcv(ohlcv)


def _maybe_add_position(
    direction: Direction,
    timestamp: object,
    price: float,
    atr: float,
    positions: list[BasketPosition],
    lot_sequence: list[float],
    config: RecoveryConfig,
) -> list[BasketPosition]:
    same_side = [position for position in positions if position.direction == direction]
    opposite = [position for position in positions if position.direction != direction]
    if opposite and not config.allow_hedged_baskets:
        return positions
    if len(same_side) >= config.max_positions_per_direction:
        return positions
    if same_side:
        last_entry = same_side[-1].entry_price
        adverse_move = last_entry - price if direction == "long" else price - last_entry
        if adverse_move < config.grid_atr_multiple * atr:
            return positions
    next_position = BasketPosition(
        direction=direction,
        entry_timestamp=timestamp,
        entry_price=price,
        volume=lot_sequence[len(same_side)],
        sequence_index=len(same_side),
    )
    return [*positions, next_position]


def _basket_close_allowed(positions: list[BasketPosition], price: float, config: RecoveryConfig) -> bool:
    pnl_by_side = {
        "long": sum(_position_pnl(position, price, config) for position in positions if position.direction == "long"),
        "short": sum(_position_pnl(position, price, config) for position in positions if position.direction == "short"),
    }
    winning = max(pnl_by_side.values())
    losing = min(pnl_by_side.values())
    if losing >= 0:
        return winning > _open_commission(positions, config)
    return winning >= abs(losing) * config.profit_to_loss_ratio + _open_commission(positions, config)


def _floating_pnl(positions: list[BasketPosition], price: float, config: RecoveryConfig) -> float:
    return sum(_position_pnl(position, price, config) for position in positions)


def _position_pnl(position: BasketPosition, price: float, config: RecoveryConfig) -> float:
    direction = 1.0 if position.direction == "long" else -1.0
    pips = direction * (price - position.entry_price) / config.pip_size
    return pips * config.pip_value_per_lot * position.volume


def _position_return_pct(position: BasketPosition, price: float) -> float:
    direction = 1.0 if position.direction == "long" else -1.0
    return direction * (price / position.entry_price - 1.0) * 100.0


def _open_commission(positions: list[BasketPosition], config: RecoveryConfig) -> float:
    return sum(position.volume * config.commission_per_lot for position in positions)


def _metrics(
    returns: pd.Series,
    equity: pd.Series,
    drawdown: pd.Series,
    trades: pd.DataFrame,
) -> dict[str, float | int | str | None]:
    clean_returns = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) else 0.0
    volatility = float(clean_returns.std(ddof=0) * np.sqrt(252))
    sharpe = float(clean_returns.mean() / clean_returns.std(ddof=0) * np.sqrt(252)) if clean_returns.std(ddof=0) > 0 else None
    pnl = pd.to_numeric(trades["pnl"], errors="coerce").fillna(0.0) if not trades.empty else pd.Series(dtype=float)
    gross_profit = float(pnl[pnl > 0].sum()) if len(pnl) else 0.0
    gross_loss = float(abs(pnl[pnl < 0].sum())) if len(pnl) else 0.0
    return {
        "total_return": total_return,
        "annualized_return": total_return,
        "annualized_volatility": volatility,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "sharpe_ratio": sharpe,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "expected_payoff": float(pnl.mean()) if len(pnl) else None,
        "recovery_factor": None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": float(equity.iloc[-1] - equity.iloc[0]) if len(equity) else 0.0,
        "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "trade_count": int(len(trades)),
    }
