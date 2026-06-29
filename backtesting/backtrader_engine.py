"""Native Backtrader adapter for validated prepared signals."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd

from backtesting.execution_models import SimulatedOrderType
from backtesting.signals import PreparedSignals


@dataclass(frozen=True)
class BacktraderConfig:
    """Backtrader broker, sizing, and order assumptions."""

    initial_cash: float = 10_000.0
    commission: float = 0.0
    slippage_perc: float = 0.0
    size: float = 1.0
    entry_order_type: SimulatedOrderType = SimulatedOrderType.MARKET
    limit_offset: float = 0.0
    stop_offset: float = 0.0
    allow_short: bool = True
    use_stops: bool = True
    margin: float | None = None
    leverage: float = 1.0
    multiplier: float = 1.0
    interest: float = 0.0
    stocklike: bool = False
    annualization_factor: float = 252.0

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.size <= 0:
            raise ValueError("size must be positive")
        if self.commission < 0 or self.slippage_perc < 0:
            raise ValueError("commission and slippage_perc must not be negative")
        if self.limit_offset < 0 or self.stop_offset < 0:
            raise ValueError("entry offsets must not be negative")
        if self.leverage <= 0 or self.multiplier <= 0:
            raise ValueError("leverage and multiplier must be positive")
        if self.annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")


@dataclass(frozen=True)
class BacktraderResult:
    """Native Backtrader objects and normalized research outputs."""

    cerebro: Any
    strategy: Any
    analyzers: dict[str, Any]
    metrics: dict[str, float | int | None]
    orders: pd.DataFrame
    trades: pd.DataFrame
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series


def run_backtrader(
    signals: PreparedSignals,
    *,
    config: BacktraderConfig | None = None,
) -> BacktraderResult:
    """Run prepared signals through Backtrader's event-driven broker."""
    signals.validate()
    bt = _require_backtrader()
    cfg = config or BacktraderConfig()
    frame = _build_feed_frame(signals)

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(cfg.initial_cash)
    cerebro.broker.setcommission(
        commission=cfg.commission,
        margin=cfg.margin,
        mult=cfg.multiplier,
        leverage=cfg.leverage,
        stocklike=cfg.stocklike,
        interest=cfg.interest,
        percabs=True,
    )
    if cfg.slippage_perc:
        cerebro.broker.set_slippage_perc(cfg.slippage_perc)

    feed_type = _prepared_data_type(bt)
    strategy_type = _prepared_strategy_type(bt)
    cerebro.adddata(feed_type(dataname=frame), name="prepared_signals")
    cerebro.addstrategy(
        strategy_type,
        size=cfg.size,
        entry_order_type=cfg.entry_order_type.value,
        limit_offset=cfg.limit_offset,
        stop_offset=cfg.stop_offset,
        allow_short=cfg.allow_short,
        use_stops=cfg.use_stops,
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    strategies = cerebro.run()
    strategy = strategies[0]
    analyzers = {
        "drawdown": strategy.analyzers.drawdown.get_analysis(),
        "returns": strategy.analyzers.returns.get_analysis(),
        "trades": strategy.analyzers.trades.get_analysis(),
    }
    equity = _equity_series(strategy.equity_records, frame.index, cerebro.broker.getvalue())
    returns = equity.pct_change().fillna(0.0).rename("returns")
    drawdown = (equity / equity.cummax() - 1.0).rename("drawdown")
    orders = pd.DataFrame(strategy.order_records)
    trades = pd.DataFrame(strategy.trade_records)
    return BacktraderResult(
        cerebro=cerebro,
        strategy=strategy,
        analyzers=analyzers,
        metrics=_metrics(
            initial_cash=cfg.initial_cash,
            final_value=float(cerebro.broker.getvalue()),
            returns=returns,
            drawdown=drawdown,
            trades=trades,
            orders=orders,
            annualization_factor=cfg.annualization_factor,
        ),
        orders=orders,
        trades=trades,
        equity=equity,
        returns=returns,
        drawdown=drawdown,
    )


def _require_backtrader() -> Any:
    try:
        return import_module("backtrader")
    except ImportError as exc:
        raise RuntimeError(
            "backtrader is not installed. Install research dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc


def _build_feed_frame(signals: PreparedSignals) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = sorted(required.difference(signals.data.columns))
    if missing:
        raise ValueError(f"Backtrader requires OHLC columns: {', '.join(missing)}")

    frame = signals.data.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Backtrader requires a DatetimeIndex")
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame["long_entry"] = signals.long_entries.astype(int).to_numpy()
    frame["long_exit"] = signals.long_exits.astype(int).to_numpy()
    frame["short_entry"] = signals.short_entries.astype(int).to_numpy()
    frame["short_exit"] = signals.short_exits.astype(int).to_numpy()
    frame["sl_stop"] = (
        signals.stop_loss.astype(float).to_numpy()
        if signals.stop_loss is not None
        else np.full(len(frame), np.nan)
    )
    frame["tp_stop"] = (
        signals.take_profit.astype(float).to_numpy()
        if signals.take_profit is not None
        else np.full(len(frame), np.nan)
    )
    if "volume" not in frame:
        frame["volume"] = 0.0
    if "openinterest" not in frame:
        frame["openinterest"] = 0.0
    return frame


def _prepared_data_type(bt: Any) -> type[Any]:
    class PreparedSignalsData(bt.feeds.PandasData):
        lines = ("long_entry", "long_exit", "short_entry", "short_exit", "sl_stop", "tp_stop")
        params = (
            ("long_entry", "long_entry"),
            ("long_exit", "long_exit"),
            ("short_entry", "short_entry"),
            ("short_exit", "short_exit"),
            ("sl_stop", "sl_stop"),
            ("tp_stop", "tp_stop"),
        )

    return PreparedSignalsData


def _prepared_strategy_type(bt: Any) -> type[Any]:
    class PreparedSignalsStrategy(bt.Strategy):
        params = (
            ("size", 1.0),
            ("entry_order_type", SimulatedOrderType.MARKET.value),
            ("limit_offset", 0.0),
            ("stop_offset", 0.0),
            ("allow_short", True),
            ("use_stops", True),
        )

        def __init__(self) -> None:
            self.entry_order_ref: int | None = None
            self.close_order_ref: int | None = None
            self.protective_orders: list[Any] = []
            self.current_direction: str | None = None
            self.current_entry_size: float | None = None
            self.order_records: list[dict[str, Any]] = []
            self.trade_records: list[dict[str, Any]] = []
            self.equity_records: list[tuple[pd.Timestamp, float]] = []

        def next(self) -> None:
            self.equity_records.append((self._timestamp(), float(self.broker.getvalue())))
            if self.entry_order_ref is not None or self.close_order_ref is not None:
                return

            if self.position:
                is_long = self.position.size > 0
                should_exit = bool(self.data.long_exit[0]) if is_long else bool(self.data.short_exit[0])
                opposite = bool(self.data.short_entry[0]) if is_long else bool(self.data.long_entry[0])
                if should_exit or opposite:
                    self._cancel_protective_orders()
                    close_order = self.close(size=abs(float(self.position.size)))
                    close_order.addinfo(role="signal_exit", reason="opposite_entry" if opposite else "signal_exit")
                    self.close_order_ref = int(close_order.ref)
                return

            if bool(self.data.long_entry[0]):
                self._submit_entry("long")
            elif bool(self.data.short_entry[0]) and self.p.allow_short:
                self._submit_entry("short")

        def notify_order(self, order: Any) -> None:
            status_name = order.getstatusname()
            role = str(getattr(order.info, "role", "unknown"))
            self.order_records.append(
                {
                    "order_ref": int(order.ref),
                    "timestamp": self._timestamp(),
                    "role": role,
                    "direction": "long" if order.isbuy() else "short",
                    "status": status_name.lower(),
                    "requested_size": abs(float(order.created.size)),
                    "executed_size": abs(float(order.executed.size)),
                    "executed_price": float(order.executed.price),
                    "commission": float(order.executed.comm),
                    "reason": str(getattr(order.info, "reason", "")),
                }
            )
            if order.status not in {
                bt.Order.Completed,
                bt.Order.Canceled,
                bt.Order.Margin,
                bt.Order.Rejected,
                bt.Order.Expired,
            }:
                return

            if int(order.ref) == self.entry_order_ref:
                self.entry_order_ref = None
                if order.status == bt.Order.Completed:
                    self.current_direction = str(getattr(order.info, "entry_direction", "long"))
                    self.current_entry_size = abs(float(order.executed.size))
                    self._submit_protective_orders(order)
                return
            if int(order.ref) == self.close_order_ref:
                self.close_order_ref = None
                return
            self.protective_orders = [
                candidate for candidate in self.protective_orders if int(candidate.ref) != int(order.ref)
            ]

        def notify_trade(self, trade: Any) -> None:
            if not trade.isclosed:
                return
            self.trade_records.append(
                {
                    "symbol": str(self.data._name or "prepared_signals"),
                    "direction": self.current_direction,
                    "entry_time": pd.Timestamp(bt.num2date(trade.dtopen)).tz_localize(None),
                    "exit_time": pd.Timestamp(bt.num2date(trade.dtclose)).tz_localize(None),
                    "entry_price": float(trade.price),
                    "size": self.current_entry_size,
                    "gross_pnl": float(trade.pnl),
                    "net_pnl": float(trade.pnlcomm),
                    "commission": float(trade.pnl - trade.pnlcomm),
                    "bar_length": int(trade.barlen),
                }
            )
            self.current_direction = None
            self.current_entry_size = None

        def stop(self) -> None:
            self.equity_records.append((self._timestamp(), float(self.broker.getvalue())))

        def _submit_entry(self, direction: str) -> None:
            order_type = str(self.p.entry_order_type)
            close = float(self.data.close[0])
            kwargs: dict[str, Any] = {"size": float(self.p.size)}
            if order_type == SimulatedOrderType.LIMIT.value:
                kwargs.update(
                    exectype=bt.Order.Limit,
                    price=close * (1.0 - self.p.limit_offset if direction == "long" else 1.0 + self.p.limit_offset),
                )
            elif order_type == SimulatedOrderType.STOP.value:
                kwargs.update(
                    exectype=bt.Order.Stop,
                    price=close * (1.0 + self.p.stop_offset if direction == "long" else 1.0 - self.p.stop_offset),
                )
            else:
                kwargs["exectype"] = bt.Order.Market

            entry_order = self.buy(**kwargs) if direction == "long" else self.sell(**kwargs)
            entry_order.addinfo(
                role="entry",
                entry_direction=direction,
                stop_loss_pct=_line_optional_float(self.data.sl_stop[0]),
                take_profit_pct=_line_optional_float(self.data.tp_stop[0]),
            )
            self.entry_order_ref = int(entry_order.ref)

        def _submit_protective_orders(self, entry_order: Any) -> None:
            if not self.p.use_stops:
                return
            stop_pct = getattr(entry_order.info, "stop_loss_pct", None)
            target_pct = getattr(entry_order.info, "take_profit_pct", None)
            if stop_pct is None and target_pct is None:
                return
            direction = str(getattr(entry_order.info, "entry_direction", "long"))
            price = float(entry_order.executed.price)
            size = abs(float(entry_order.executed.size))
            stop_order = None
            if stop_pct is not None:
                stop_price = price * (1.0 - stop_pct if direction == "long" else 1.0 + stop_pct)
                stop_order = (
                    self.sell(size=size, exectype=bt.Order.Stop, price=stop_price)
                    if direction == "long"
                    else self.buy(size=size, exectype=bt.Order.Stop, price=stop_price)
                )
                stop_order.addinfo(role="stop_loss", reason="stop_loss")
                self.protective_orders.append(stop_order)
            if target_pct is not None:
                target_price = price * (1.0 + target_pct if direction == "long" else 1.0 - target_pct)
                target_order = (
                    self.sell(size=size, exectype=bt.Order.Limit, price=target_price, oco=stop_order)
                    if direction == "long"
                    else self.buy(size=size, exectype=bt.Order.Limit, price=target_price, oco=stop_order)
                )
                target_order.addinfo(role="take_profit", reason="take_profit")
                self.protective_orders.append(target_order)

        def _cancel_protective_orders(self) -> None:
            for order in self.protective_orders:
                if order.alive():
                    self.cancel(order)
            self.protective_orders.clear()

        def _timestamp(self) -> pd.Timestamp:
            return pd.Timestamp(bt.num2date(self.data.datetime[0])).tz_localize(None)

    return PreparedSignalsStrategy


def _line_optional_float(value: Any) -> float | None:
    number = float(value)
    return number if np.isfinite(number) and number >= 0 else None


def _equity_series(
    records: list[tuple[pd.Timestamp, float]],
    fallback_index: pd.Index,
    final_value: float,
) -> pd.Series:
    if not records:
        return pd.Series([final_value], index=[fallback_index[-1]], name="equity", dtype=float)
    frame = pd.DataFrame(records, columns=["timestamp", "equity"]).drop_duplicates("timestamp", keep="last")
    return frame.set_index("timestamp")["equity"].astype(float).rename("equity")


def _metrics(
    *,
    initial_cash: float,
    final_value: float,
    returns: pd.Series,
    drawdown: pd.Series,
    trades: pd.DataFrame,
    orders: pd.DataFrame,
    annualization_factor: float,
) -> dict[str, float | int | None]:
    volatility = float(returns.std(ddof=0))
    sharpe = float(returns.mean() / volatility * sqrt(annualization_factor)) if volatility > 0 else None
    trade_count = len(trades)
    wins = int((trades["net_pnl"] > 0).sum()) if trade_count else 0
    gross_profit = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum()) if trade_count else 0.0
    gross_loss = abs(float(trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum())) if trade_count else 0.0
    rejected_statuses = {"margin", "rejected", "expired"}
    rejected = int(orders["status"].isin(rejected_statuses).sum()) if not orders.empty else 0
    total_return = final_value / initial_cash - 1.0
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
        "final_equity": final_value,
    }
