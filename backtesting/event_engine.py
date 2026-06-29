"""Deterministic event-driven simulation for prepared strategy signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from backtesting.execution_models import (
    BrokerProfile,
    ExecutionModel,
    IntrabarCollisionPolicy,
    SimulatedFill,
    SimulatedOrder,
    SimulatedOrderStatus,
    SimulatedOrderType,
    execution_price,
)
from backtesting.signals import PreparedSignals


@dataclass(frozen=True)
class EventBacktestConfig:
    """Portfolio and order assumptions for event-driven validation."""

    initial_cash: float = 10_000.0
    order_volume: float = 0.01
    entry_order_type: SimulatedOrderType = SimulatedOrderType.BRACKET
    limit_offset_points: float = 0.0
    stop_offset_points: float = 0.0
    force_close_at_end: bool = True

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.order_volume <= 0:
            raise ValueError("order_volume must be positive")
        if self.limit_offset_points < 0 or self.stop_offset_points < 0:
            raise ValueError("order offsets must not be negative")


@dataclass(frozen=True)
class EventBacktestResult:
    """Auditable output of one event-driven simulation."""

    orders: pd.DataFrame
    fills: pd.DataFrame
    trades: pd.DataFrame
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series
    metrics: dict[str, float | int | None]


@dataclass
class _PendingOrder:
    order: SimulatedOrder
    submitted_index: int
    eligible_index: int
    remaining_volume: float
    age: int = 0


@dataclass
class _Position:
    direction: str
    volume: float
    entry_price: float
    entry_time: Any
    entry_commission: float
    stop_loss: float | None
    take_profit: float | None
    swap: float = 0.0
    pending_exit_index: int | None = None
    pending_exit_reason: str | None = None


class EventDrivenBacktester:
    """Simulate validated signals with broker costs and order lifecycle events."""

    def __init__(
        self,
        *,
        broker: BrokerProfile,
        execution: ExecutionModel | None = None,
        config: EventBacktestConfig | None = None,
    ) -> None:
        self.broker = broker
        self.execution = execution or ExecutionModel()
        self.config = config or EventBacktestConfig()

    def run(
        self,
        signals: PreparedSignals,
        *,
        lower_timeframe: pd.DataFrame | None = None,
    ) -> EventBacktestResult:
        signals.validate()
        data = _require_ohlc(signals.data)
        lower = _prepare_lower_timeframe(lower_timeframe)
        rng = np.random.default_rng(self.execution.seed)

        cash = float(self.config.initial_cash)
        position: _Position | None = None
        pending: list[_PendingOrder] = []
        order_records: list[dict[str, Any]] = []
        fills: list[SimulatedFill] = []
        trades: list[dict[str, Any]] = []
        equity_values: list[float] = []
        last_date: Any = None

        for index_number, (timestamp, bar_series) in enumerate(data.iterrows()):
            bar = bar_series.to_dict()
            next_timestamp = data.index[index_number + 1] if index_number + 1 < len(data) else None

            if position is not None and last_date is not None and _date_key(timestamp) != last_date:
                swap = (
                    self.broker.swap_long_per_lot_per_day
                    if position.direction == "long"
                    else self.broker.swap_short_per_lot_per_day
                ) * position.volume
                position.swap += swap
                cash += swap
            last_date = _date_key(timestamp)

            if position is not None and position.pending_exit_index is not None:
                if index_number >= position.pending_exit_index:
                    cash, position = self._close_position(
                        position=position,
                        timestamp=timestamp,
                        reference_price=float(bar["open"]),
                        bar=bar,
                        reason=position.pending_exit_reason or "signal_exit",
                        cash=cash,
                        fills=fills,
                        trades=trades,
                    )

            pending, position, cash = self._process_pending_orders(
                pending=pending,
                position=position,
                cash=cash,
                timestamp=timestamp,
                index_number=index_number,
                bar=bar,
                rng=rng,
                order_records=order_records,
                fills=fills,
            )

            if position is not None:
                intrabar = _intrabar_slice(lower, timestamp, next_timestamp)
                trigger = _position_exit_trigger(
                    position,
                    intrabar if intrabar is not None and not intrabar.empty else pd.DataFrame([bar]),
                    self.execution.collision_policy,
                )
                if trigger is not None:
                    reason, trigger_price = trigger
                    cash, position = self._close_position(
                        position=position,
                        timestamp=timestamp,
                        reference_price=trigger_price,
                        bar=bar,
                        reason=reason,
                        cash=cash,
                        fills=fills,
                        trades=trades,
                    )

            if position is not None:
                equity = cash + self._unrealized_pnl(position, float(bar["close"]))
                margin = self.broker.margin_required(position.entry_price, position.volume)
                margin_level = equity / margin if margin > 0 else float("inf")
                if margin_level <= self.broker.stop_out_level:
                    cash, position = self._close_position(
                        position=position,
                        timestamp=timestamp,
                        reference_price=float(bar["close"]),
                        bar=bar,
                        reason="margin_stop_out",
                        cash=cash,
                        fills=fills,
                        trades=trades,
                    )

            if position is not None:
                exit_signal = (
                    bool(signals.long_exits.iloc[index_number])
                    if position.direction == "long"
                    else bool(signals.short_exits.iloc[index_number])
                )
                opposite_entry = (
                    bool(signals.short_entries.iloc[index_number])
                    if position.direction == "long"
                    else bool(signals.long_entries.iloc[index_number])
                )
                if exit_signal or opposite_entry:
                    position.pending_exit_index = index_number + max(1, self.execution.latency_bars)
                    position.pending_exit_reason = "opposite_entry" if opposite_entry else "signal_exit"
            elif not pending:
                direction = _entry_direction(signals, index_number)
                if direction is not None:
                    order = self._build_entry_order(
                        direction=direction,
                        timestamp=timestamp,
                        close=float(bar["close"]),
                        stop_loss_pct=_optional_series_value(signals.stop_loss, index_number),
                        take_profit_pct=_optional_series_value(signals.take_profit, index_number),
                    )
                    pending.append(
                        _PendingOrder(
                            order=order,
                            submitted_index=index_number,
                            eligible_index=index_number + self.execution.latency_bars,
                            remaining_volume=order.volume,
                        )
                    )
                    order_records.append(_order_record(order, SimulatedOrderStatus.SUBMITTED, timestamp, "signal"))
                    if self.execution.latency_bars == 0:
                        pending, position, cash = self._process_pending_orders(
                            pending=pending,
                            position=position,
                            cash=cash,
                            timestamp=timestamp,
                            index_number=index_number,
                            bar={**bar, "open": bar["close"]},
                            rng=rng,
                            order_records=order_records,
                            fills=fills,
                        )

            marked_equity = cash
            if position is not None:
                marked_equity += self._unrealized_pnl(position, float(bar["close"]))
            equity_values.append(marked_equity)

        if position is not None and self.config.force_close_at_end:
            timestamp = data.index[-1]
            bar = data.iloc[-1].to_dict()
            cash, position = self._close_position(
                position=position,
                timestamp=timestamp,
                reference_price=float(bar["close"]),
                bar=bar,
                reason="end_of_data",
                cash=cash,
                fills=fills,
                trades=trades,
            )
            equity_values[-1] = cash

        for item in pending:
            order_records.append(
                _order_record(item.order, SimulatedOrderStatus.EXPIRED, data.index[-1], "end_of_data")
            )

        equity = pd.Series(equity_values, index=data.index, name="equity", dtype=float)
        returns = equity.pct_change().fillna(0.0).rename("returns")
        drawdown = (equity / equity.cummax() - 1.0).rename("drawdown")
        trades_frame = pd.DataFrame(trades)
        fills_frame = pd.DataFrame(
            [
                {
                    **fill.__dict__,
                    "status": fill.status.value,
                }
                for fill in fills
            ]
        )
        orders_frame = pd.DataFrame(order_records)
        return EventBacktestResult(
            orders=orders_frame,
            fills=fills_frame,
            trades=trades_frame,
            equity=equity,
            returns=returns,
            drawdown=drawdown,
            metrics=_metrics(
                initial_cash=self.config.initial_cash,
                equity=equity,
                returns=returns,
                drawdown=drawdown,
                trades=trades_frame,
                orders=orders_frame,
            ),
        )

    def _build_entry_order(
        self,
        *,
        direction: str,
        timestamp: Any,
        close: float,
        stop_loss_pct: float | None,
        take_profit_pct: float | None,
    ) -> SimulatedOrder:
        order_type = self.config.entry_order_type
        limit_price = None
        stop_price = None
        if order_type == SimulatedOrderType.LIMIT:
            offset = self.config.limit_offset_points * self.broker.point
            limit_price = close - offset if direction == "long" else close + offset
        elif order_type == SimulatedOrderType.STOP:
            offset = self.config.stop_offset_points * self.broker.point
            stop_price = close + offset if direction == "long" else close - offset
        return SimulatedOrder(
            order_id=str(uuid4()),
            symbol=self.broker.symbol,
            direction=direction,
            order_type=order_type,
            volume=self.config.order_volume,
            submitted_at=timestamp,
            limit_price=limit_price,
            stop_price=stop_price,
            expires_after_bars=self.execution.order_expiry_bars,
            metadata={
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
            },
        )

    def _process_pending_orders(
        self,
        *,
        pending: list[_PendingOrder],
        position: _Position | None,
        cash: float,
        timestamp: Any,
        index_number: int,
        bar: dict[str, Any],
        rng: np.random.Generator,
        order_records: list[dict[str, Any]],
        fills: list[SimulatedFill],
    ) -> tuple[list[_PendingOrder], _Position | None, float]:
        remaining_orders: list[_PendingOrder] = []
        for item in pending:
            if index_number < item.eligible_index:
                remaining_orders.append(item)
                continue
            item.age += 1
            expiry = item.order.expires_after_bars or self.execution.order_expiry_bars
            if item.age > expiry:
                order_records.append(_order_record(item.order, SimulatedOrderStatus.EXPIRED, timestamp, "expired"))
                continue
            if _should_reject(bar, self.execution, rng):
                order_records.append(_order_record(item.order, SimulatedOrderStatus.REJECTED, timestamp, "broker_rejection"))
                continue
            reference = _order_reference_price(item.order, bar)
            if reference is None:
                remaining_orders.append(item)
                continue

            available = self.execution.available_volume(bar, self.broker)
            fill_volume = min(item.remaining_volume, available)
            fill_volume = self.broker.normalize_volume(fill_volume)
            if fill_volume <= 0:
                remaining_orders.append(item)
                continue
            if fill_volume < item.remaining_volume and not self.execution.allow_partial_fills:
                remaining_orders.append(item)
                continue

            spread_points = self.execution.spread_points_for(bar, self.broker)
            slippage_points = self.execution.slippage_points_for(bar)
            price, spread_price, slippage_price = execution_price(
                reference_price=reference,
                direction=item.order.direction,
                is_entry=True,
                spread_points=spread_points,
                slippage_points=slippage_points,
                point=self.broker.point,
            )
            required_margin = self.broker.margin_required(price, fill_volume)
            existing_margin = (
                self.broker.margin_required(position.entry_price, position.volume)
                if position is not None
                else 0.0
            )
            equity = cash
            if position is not None:
                equity += self._unrealized_pnl(position, float(bar["close"]))
            if equity - existing_margin < required_margin or (
                existing_margin > 0 and equity / existing_margin <= self.broker.margin_call_level
            ):
                order_records.append(
                    _order_record(item.order, SimulatedOrderStatus.REJECTED, timestamp, "insufficient_margin")
                )
                continue

            commission = self.broker.commission_per_lot_per_side * fill_volume
            cash -= commission
            item.remaining_volume = round(item.remaining_volume - fill_volume, 10)
            fill_status = (
                SimulatedOrderStatus.FILLED
                if item.remaining_volume <= 0
                else SimulatedOrderStatus.PARTIALLY_FILLED
            )
            fill = SimulatedFill(
                order_id=item.order.order_id,
                timestamp=timestamp,
                symbol=item.order.symbol,
                direction=item.order.direction,
                volume=fill_volume,
                price=price,
                commission=commission,
                spread_cost=spread_price / self.broker.point * self.broker.tick_value * fill_volume,
                slippage_cost=slippage_price / self.broker.point * self.broker.tick_value * fill_volume,
                status=fill_status,
                reason="entry",
                margin_used=required_margin,
            )
            fills.append(fill)
            order_records.append(_order_record(item.order, fill_status, timestamp, "entry_fill"))
            position = _merge_position(position, item.order, fill)
            if item.remaining_volume > 0:
                remaining_orders.append(item)
        return remaining_orders, position, cash

    def _close_position(
        self,
        *,
        position: _Position,
        timestamp: Any,
        reference_price: float,
        bar: dict[str, Any],
        reason: str,
        cash: float,
        fills: list[SimulatedFill],
        trades: list[dict[str, Any]],
    ) -> tuple[float, None]:
        spread_points = self.execution.spread_points_for(bar, self.broker)
        slippage_points = self.execution.slippage_points_for(bar)
        exit_price, spread_price, slippage_price = execution_price(
            reference_price=reference_price,
            direction=position.direction,
            is_entry=False,
            spread_points=spread_points,
            slippage_points=slippage_points,
            point=self.broker.point,
        )
        gross_pnl = self.broker.price_pnl(
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            volume=position.volume,
        )
        commission = self.broker.commission_per_lot_per_side * position.volume
        cash += gross_pnl - commission
        net_pnl = gross_pnl - position.entry_commission - commission + position.swap
        fill = SimulatedFill(
            order_id=str(uuid4()),
            timestamp=timestamp,
            symbol=self.broker.symbol,
            direction=position.direction,
            volume=position.volume,
            price=exit_price,
            commission=commission,
            spread_cost=spread_price / self.broker.point * self.broker.tick_value * position.volume,
            slippage_cost=slippage_price / self.broker.point * self.broker.tick_value * position.volume,
            status=SimulatedOrderStatus.FILLED,
            reason=reason,
            realized_pnl=net_pnl,
        )
        fills.append(fill)
        trades.append(
            {
                "symbol": self.broker.symbol,
                "direction": position.direction,
                "entry_time": position.entry_time,
                "exit_time": timestamp,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
                "volume": position.volume,
                "gross_pnl": gross_pnl,
                "commission": position.entry_commission + commission,
                "swap": position.swap,
                "net_pnl": net_pnl,
                "exit_reason": reason,
            }
        )
        return cash, None

    def _unrealized_pnl(self, position: _Position, price: float) -> float:
        return self.broker.price_pnl(
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=price,
            volume=position.volume,
        )


def _require_ohlc(data: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"event-driven backtest requires OHLC columns: {', '.join(missing)}")
    frame = data.copy()
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame


def _prepare_lower_timeframe(data: pd.DataFrame | None) -> pd.DataFrame | None:
    if data is None:
        return None
    frame = _require_ohlc(data).sort_index()
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("lower_timeframe index must be unique and chronological")
    return frame


def _intrabar_slice(
    lower: pd.DataFrame | None,
    start: Any,
    end: Any | None,
) -> pd.DataFrame | None:
    if lower is None:
        return None
    if end is None:
        return lower.loc[lower.index >= start]
    return lower.loc[(lower.index >= start) & (lower.index < end)]


def _position_exit_trigger(
    position: _Position,
    bars: pd.DataFrame,
    policy: IntrabarCollisionPolicy,
) -> tuple[str, float] | None:
    for _, bar in bars.iterrows():
        low = float(bar["low"])
        high = float(bar["high"])
        if position.direction == "long":
            stop_hit = position.stop_loss is not None and low <= position.stop_loss
            target_hit = position.take_profit is not None and high >= position.take_profit
        else:
            stop_hit = position.stop_loss is not None and high >= position.stop_loss
            target_hit = position.take_profit is not None and low <= position.take_profit

        if stop_hit and target_hit:
            if policy in {IntrabarCollisionPolicy.STOP_FIRST, IntrabarCollisionPolicy.CONSERVATIVE}:
                return "stop_loss", float(position.stop_loss)
            return "take_profit", float(position.take_profit)
        if stop_hit:
            return "stop_loss", float(position.stop_loss)
        if target_hit:
            return "take_profit", float(position.take_profit)
    return None


def _entry_direction(signals: PreparedSignals, index_number: int) -> str | None:
    if bool(signals.long_entries.iloc[index_number]):
        return "long"
    if bool(signals.short_entries.iloc[index_number]):
        return "short"
    return None


def _optional_series_value(series: pd.Series | None, index_number: int) -> float | None:
    if series is None:
        return None
    value = series.iloc[index_number]
    if pd.isna(value):
        return None
    return float(value)


def _order_reference_price(order: SimulatedOrder, bar: dict[str, Any]) -> float | None:
    if order.order_type in {SimulatedOrderType.MARKET, SimulatedOrderType.BRACKET}:
        return float(bar["open"])
    if order.order_type == SimulatedOrderType.LIMIT:
        assert order.limit_price is not None
        if order.direction == "long" and float(bar["low"]) <= order.limit_price:
            return min(float(bar["open"]), order.limit_price)
        if order.direction == "short" and float(bar["high"]) >= order.limit_price:
            return max(float(bar["open"]), order.limit_price)
    if order.order_type == SimulatedOrderType.STOP:
        assert order.stop_price is not None
        if order.direction == "long" and float(bar["high"]) >= order.stop_price:
            return max(float(bar["open"]), order.stop_price)
        if order.direction == "short" and float(bar["low"]) <= order.stop_price:
            return min(float(bar["open"]), order.stop_price)
    return None


def _merge_position(
    position: _Position | None,
    order: SimulatedOrder,
    fill: SimulatedFill,
) -> _Position:
    if position is not None and position.direction != fill.direction:
        raise RuntimeError("cannot merge fills in opposite directions")
    previous_volume = position.volume if position is not None else 0.0
    total_volume = previous_volume + fill.volume
    weighted_entry = (
        ((position.entry_price * previous_volume) if position is not None else 0.0)
        + fill.price * fill.volume
    ) / total_volume
    stop_pct = order.metadata.get("stop_loss_pct")
    target_pct = order.metadata.get("take_profit_pct")
    stop_loss = None
    take_profit = None
    if stop_pct is not None:
        stop_loss = weighted_entry * (1.0 - float(stop_pct)) if fill.direction == "long" else weighted_entry * (1.0 + float(stop_pct))
    if target_pct is not None:
        take_profit = weighted_entry * (1.0 + float(target_pct)) if fill.direction == "long" else weighted_entry * (1.0 - float(target_pct))
    return _Position(
        direction=fill.direction,
        volume=total_volume,
        entry_price=weighted_entry,
        entry_time=position.entry_time if position is not None else fill.timestamp,
        entry_commission=(position.entry_commission if position is not None else 0.0) + fill.commission,
        stop_loss=stop_loss,
        take_profit=take_profit,
        swap=position.swap if position is not None else 0.0,
    )


def _should_reject(
    bar: dict[str, Any],
    execution: ExecutionModel,
    rng: np.random.Generator,
) -> bool:
    raw = bar.get(execution.reject_column, False)
    if bool(raw):
        return True
    return bool(execution.rejection_probability and rng.random() < execution.rejection_probability)


def _order_record(
    order: SimulatedOrder,
    status: SimulatedOrderStatus,
    timestamp: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "timestamp": timestamp,
        "symbol": order.symbol,
        "direction": order.direction,
        "order_type": order.order_type.value,
        "volume": order.volume,
        "status": status.value,
        "reason": reason,
    }


def _date_key(value: Any) -> Any:
    return value.date() if hasattr(value, "date") else value


def _metrics(
    *,
    initial_cash: float,
    equity: pd.Series,
    returns: pd.Series,
    drawdown: pd.Series,
    trades: pd.DataFrame,
    orders: pd.DataFrame,
) -> dict[str, float | int | None]:
    total_return = float(equity.iloc[-1] / initial_cash - 1.0)
    volatility = float(returns.std(ddof=0))
    sharpe = float(returns.mean() / volatility * np.sqrt(252.0)) if volatility > 0 else None
    trade_count = len(trades)
    wins = int((trades["net_pnl"] > 0).sum()) if trade_count else 0
    gross_profit = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum()) if trade_count else 0.0
    gross_loss = abs(float(trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum())) if trade_count else 0.0
    rejected = int((orders["status"] == SimulatedOrderStatus.REJECTED.value).sum()) if not orders.empty else 0
    return {
        "total_return": total_return,
        "total_return_pct": total_return * 100.0,
        "sharpe_ratio": sharpe,
        "max_drawdown": float(drawdown.min()),
        "max_drawdown_pct": float(drawdown.min()) * 100.0,
        "trade_count": trade_count,
        "win_rate": wins / trade_count if trade_count else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "rejected_order_count": rejected,
        "final_equity": float(equity.iloc[-1]),
    }
