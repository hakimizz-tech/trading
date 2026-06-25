"""Shared aiomql strategy base and broker-result adapters."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar, cast

import pandas as pd

from accounting import SQLiteLedger
from execution.gates import evaluate_live_execution_gate
from execution.state import AccountSnapshot, BrokerFill, BrokerSnapshot, OpenPosition, SymbolContract
from journal import JournalEvent, TradeJournal, utc_now
from market_data.ohlcv import to_ohlcv_frame as normalize_ohlcv_frame

try:
    from aiomql import ForexSymbol, OrderType, ScalpTrader, Sessions, Strategy, TimeFrame, Tracker, Trader  # pyright: ignore[reportMissingImports]
except ImportError as exc:  # pragma: no cover - exercised on non-aiomql systems
    AIOMQL_IMPORT_ERROR = exc
    ForexSymbol = OrderType = ScalpTrader = Sessions = Strategy = TimeFrame = Tracker = Trader = None  # type: ignore[assignment]
else:
    AIOMQL_IMPORT_ERROR = None


logger = logging.getLogger(__name__)
SnapshotProvider = Callable[[Any], BrokerSnapshot | Awaitable[BrokerSnapshot]]


def aiomql_available() -> bool:
    """Return True when aiomql can be imported in this environment."""
    return AIOMQL_IMPORT_ERROR is None


def require_aiomql() -> None:
    """Raise a clear error when aiomql is not available."""
    if AIOMQL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "aiomql is not available in this environment. Live MT5 execution "
            "requires Windows, Python 3.13+, MetaTrader 5, and the aiomql package."
        ) from AIOMQL_IMPORT_ERROR


class StrategyAiomqlBase(Strategy if Strategy is not None else object):  # type: ignore[misc,valid-type]
    """Base class for aiomql strategies with shared gates and persistence."""

    parameters: ClassVar[dict[str, Any]] = {
        "timeframe": "M15",
        "interval": "M15",
        "count": 300,
        "timeout_seconds": 60 * 60,
        "live_trading": False,
        "max_spread": 30.0,
        "max_open_positions": 1,
        "max_daily_loss_pct": 0.02,
        "max_daily_loss_amount": None,
        "use_risk_sizing": False,
        "risk_per_trade": 0.01,
        "fixed_volume": 0.01,
        "min_volume": 0.01,
        "max_volume": 100.0,
        "volume_step": 0.01,
        "magic": 260617,
        "comment": "Strategy",
        "stop_loss_pips": 30.0,
        "take_profit_rr": 2.0,
        "journal_enabled": True,
        "journal_db_path": "trade_results/trade_journal.sqlite",
        "accounting_enabled": True,
        "accounting_db_path": "trade_results/trade_accounting.sqlite",
    }

    def __init__(
        self,
        *,
        symbol: Any,
        params: dict[str, Any] | None = None,
        trader: Any | None = None,
        sessions: Any | None = None,
        snapshot_provider: SnapshotProvider | None = None,
        name: str = "Strategy",
    ) -> None:
        require_aiomql()
        super().__init__(symbol=symbol, params=params, sessions=sessions, name=name)
        self.runtime_params = dict(params or {})
        self.tracker = Tracker(snooze=self._interval_seconds())  # type: ignore[operator]
        self.trader = trader or ScalpTrader(symbol=self.symbol)  # type: ignore[operator]
        self.trade_parameters: dict[str, Any] = self._parameter_snapshot()
        self.journal = TradeJournal(str(self.journal_db_path)) if bool(self.journal_enabled) else None
        self.ledger = SQLiteLedger(str(self.accounting_db_path)) if bool(self.accounting_enabled) else None
        self.snapshot_provider = snapshot_provider

    async def find_entry(self) -> None:
        """Update ``self.tracker`` and ``self.trade_parameters`` with the latest signal."""
        raise NotImplementedError

    async def trade(self) -> None:
        await self.find_entry()

        if self.tracker.order_type is None:
            await self.sleep(secs=self.tracker.snooze)
            return

        if not self._basic_execution_gate_allows_trade():
            logger.info("Execution gate blocked %s signal on %s", self.tracker.order_type, self._symbol_name())
            self._journal_signal(status="blocked", mode="live" if bool(self.live_trading) else "dry_run")
            await self.delay(secs=self.tracker.snooze)
            return

        if not bool(self.live_trading):
            logger.info("Dry-run signal for %s: %s", self._symbol_name(), self.tracker.order_type)
            self._journal_signal(status="signal", mode="dry_run")
            await self.delay(secs=self.tracker.snooze)
            return

        live_gate = await self._live_execution_gate()
        if not live_gate:
            logger.info("Live execution gate blocked %s signal on %s", self.tracker.order_type, self._symbol_name())
            self._journal_signal(status="blocked", mode="live")
            await self.delay(secs=self.tracker.snooze)
            return

        trade_id = self._journal_signal(status="submitted", mode="live")
        try:
            order_result = await self.trader.place_trade(order_type=self.tracker.order_type, parameters=self.trade_parameters)
        except Exception as exc:
            self._journal_event(
                trade_id=trade_id,
                event_type="order_error",
                status="error",
                message=str(exc),
                metadata={"order_type": str(self.tracker.order_type)},
            )
            raise

        self._journal_event(
            trade_id=trade_id,
            event_type="order_submitted",
            status="submitted",
            message="aiomql trader.place_trade completed",
            metadata={"order_type": str(self.tracker.order_type), "order_result": str(order_result)},
        )
        self._record_broker_result(trade_id=trade_id, order_result=order_result)
        await self.delay(secs=self.tracker.snooze)

    def _basic_execution_gate_allows_trade(self) -> bool:
        if not bool(self.use_risk_sizing) and float(self.fixed_volume) <= 0:
            logger.warning("fixed_volume must be positive")
            return False
        if float(self.risk_per_trade) <= 0 or float(self.risk_per_trade) > 0.05:
            logger.warning("risk_per_trade must be in the range (0, 0.05]")
            return False
        if float(self.stop_loss_pips) <= 0:
            logger.warning("stop_loss_pips must be positive before execution")
            return False
        if float(self.take_profit_rr) <= 0:
            logger.warning("take_profit_rr must be positive before execution")
            return False
        if int(self.max_open_positions) < 1:
            logger.warning("max_open_positions must be at least 1")
            return False
        return True

    async def _live_execution_gate(self) -> bool:
        snapshot = await self._broker_snapshot()
        if snapshot is None:
            logger.warning("broker snapshot is required before live execution")
            return False
        gate = evaluate_live_execution_gate(
            trade_parameters=self.trade_parameters,
            snapshot=snapshot,
            strategy=self._journal_strategy_tag(),
            symbol=self._symbol_name(),
            max_spread=optional_float(self.max_spread),
            max_open_positions=int(self.max_open_positions),
            max_daily_loss_pct=optional_float(self.max_daily_loss_pct),
            max_daily_loss_amount=optional_float(self.max_daily_loss_amount),
            daily_net_pnl=self._daily_net_pnl(),
            use_risk_sizing=bool(self.use_risk_sizing),
            fixed_volume=float(self.fixed_volume),
            risk_per_trade=float(self.risk_per_trade),
            min_volume=optional_float(self.min_volume),
            max_volume=optional_float(self.max_volume),
            volume_step=optional_float(self.volume_step),
        )
        if not gate.allowed:
            logger.warning("live execution gate rejected trade: %s", gate.reason)
            self.trade_parameters["gate_rejection_reason"] = gate.reason
            return False
        if gate.volume is not None:
            self.trade_parameters["volume"] = gate.volume
        if gate.metadata:
            self.trade_parameters.update(gate.metadata)
        self.trade_parameters["current_spread"] = snapshot.current_spread
        self.trade_parameters["account_equity"] = snapshot.account.equity
        self.trade_parameters["account_free_margin"] = snapshot.account.free_margin
        return True

    async def _broker_snapshot(self) -> BrokerSnapshot | None:
        if self.snapshot_provider is not None:
            provided = self.snapshot_provider(self)
            if inspect.isawaitable(provided):
                return await cast(Awaitable[BrokerSnapshot], provided)
            return provided
        return broker_snapshot_from_sources(
            symbol=self.symbol,
            trader=self.trader,
            strategy=self._journal_strategy_tag(),
            fallback_symbol=self._symbol_name(),
            fallback_spread=optional_float(self.trade_parameters.get("current_spread")),
            fallback_min_lot=optional_float(self.min_volume),
            fallback_max_lot=optional_float(self.max_volume),
            fallback_lot_step=optional_float(self.volume_step),
        )

    def _daily_net_pnl(self) -> float:
        if self.ledger is None:
            return 0.0
        start = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        return self.ledger.net_income_since(start, strategy=self._journal_strategy_tag(), symbol=self._symbol_name())

    def _record_broker_result(self, *, trade_id: str | None, order_result: Any) -> None:
        fill = extract_broker_fill(
            order_result=order_result,
            trade_parameters=self.trade_parameters,
            symbol=self._symbol_name(),
            direction=self._journal_direction(),
        )
        if fill is None:
            self._journal_event(
                trade_id=trade_id,
                event_type="order_result_unparsed",
                status="submitted",
                message="Order result did not include a confirmed broker fill",
                metadata={"order_result": str(order_result)},
            )
            return

        status = "closed" if fill.realized_pnl is not None else "filled"
        if status == "closed" and self.journal is not None and trade_id is not None:
            try:
                realized_pnl = float(fill.realized_pnl or 0.0)
                self.journal.update_exit(
                    trade_id,
                    exit_date=fill.occurred_at or utc_now(),
                    exit_price=fill.exit_price or fill.price,
                    pnl_sol=realized_pnl,
                    pnl_pct=fill_price_return_pct(fill),
                    outcome=fill_outcome(realized_pnl),
                    status="closed",
                )
            except Exception:
                logger.exception("Failed to update journal exit for broker fill %s", fill.external_id)
                if bool(self.live_trading):
                    raise

        self._journal_event(
            trade_id=trade_id,
            event_type="broker_fill" if status == "filled" else "broker_position_close",
            status=status,
            message="Broker confirmed fill",
            metadata={
                "broker_external_id": fill.external_id,
                "price": fill.price,
                "volume": fill.volume,
                "realized_pnl": fill.realized_pnl,
                "commission": fill.commission,
                "swap": fill.swap,
            },
        )
        if self.ledger is not None and fill.realized_pnl is not None:
            self.ledger.record_broker_fill(
                symbol=fill.symbol,
                realized_pnl=fill.realized_pnl,
                commission=fill.commission,
                swap=fill.swap,
                occurred_at=fill.occurred_at,
                strategy=self._journal_strategy_tag(),
                external_id=fill.external_id,
                direction=fill.direction,
                volume=fill.volume,
                entry_price=fill.entry_price,
                exit_price=fill.exit_price or fill.price,
            )

    def _journal_signal(self, *, status: str, mode: str) -> str | None:
        if self.journal is None:
            return None
        try:
            direction = self._journal_direction()
            trade_id = self.journal.record_signal_trade(
                token=self._symbol_name(),
                direction=direction,
                entry_price=float(self.trade_parameters.get("entry_price", 0.0)),
                size_sol=float(self.trade_parameters.get("volume", self.fixed_volume)),
                strategy=self._journal_strategy_tag(),
                rationale=self._journal_rationale(direction),
                status=status,
                mode=mode,
                source=f"aiomql:{self.name}",
                stop_price=optional_float(self.trade_parameters.get("stop_loss_price")),
                target_price=optional_float(self.trade_parameters.get("take_profit_price")),
                risk_reward=optional_float(self.trade_parameters.get("take_profit_rr")),
                expected_profit=optional_float(self.trade_parameters.get("expected_profit")),
                metadata=self._journal_metadata(),
            )
            return trade_id
        except Exception:
            logger.exception("Failed to journal %s %s signal on %s", mode, status, self._symbol_name())
            if bool(self.live_trading):
                raise
            return None

    def _journal_event(
        self,
        *,
        trade_id: str | None,
        event_type: str,
        status: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.journal is None:
            return
        try:
            self.journal.record_event(
                JournalEvent(
                    trade_id=trade_id,
                    event_time=utc_now(),
                    event_type=event_type,
                    token=self._symbol_name(),
                    strategy=self._journal_strategy_tag(),
                    direction=self._journal_direction(),
                    price=optional_float(self.trade_parameters.get("entry_price")),
                    size_sol=float(self.trade_parameters.get("volume", self.fixed_volume)),
                    status=status,
                    message=message,
                    metadata=metadata or {},
                )
            )
        except Exception:
            logger.exception("Failed to journal event %s for %s", event_type, self._symbol_name())
            if bool(self.live_trading):
                raise

    def _journal_direction(self) -> str:
        order_name = str(self.tracker.order_type).upper()
        return "short" if "SELL" in order_name else "long"

    def _journal_strategy_tag(self) -> str:
        return str(getattr(self, "strategy_tag", self.name))

    def _journal_rationale(self, direction: str) -> str:
        return f"{self._symbol_name()} {direction} signal on {self.timeframe}."

    def _journal_metadata(self) -> dict[str, Any]:
        keys = (
            "entry_strategy",
            "exit_strategy",
            "risk_per_trade",
            "max_spread",
            "max_open_positions",
            "max_daily_loss_pct",
            "max_daily_loss_amount",
            "use_risk_sizing",
            "min_volume",
            "max_volume",
            "volume_step",
            "magic",
            "comment",
            "volume",
            "risk_amount",
            "stop_distance_price",
            "stop_distance_pips",
            "risk_per_lot",
            "current_spread",
            "account_equity",
            "account_free_margin",
            "gate_rejection_reason",
            "expected_profit",
        )
        metadata = {key: self.trade_parameters.get(key) for key in keys if key in self.trade_parameters}
        metadata["timeframe"] = str(self.timeframe)
        metadata["interval"] = str(self.interval)
        metadata["live_trading"] = bool(self.live_trading)
        return metadata

    def _symbol_name(self) -> str:
        return str(getattr(self.symbol, "name", self.symbol))

    def _parameter_snapshot(self) -> dict[str, Any]:
        """Return class defaults overlaid with runtime config params."""
        return {**self.parameters, **self.runtime_params}

    def _timeframe(self) -> Any:
        return resolve_timeframe(str(self.timeframe))

    def _interval_seconds(self) -> int:
        interval = resolve_timeframe(str(self.interval))
        return int(getattr(interval, "seconds", 60))

    def _configured_pip_size(self) -> float:
        pip_size = optional_float(getattr(self, "pip_size", None))
        if pip_size is not None and pip_size > 0:
            return pip_size
        return infer_pip_size(self._symbol_name(), 0.00001) or 0.0001


def resolve_timeframe(value: str) -> Any:
    require_aiomql()
    key = value.strip().upper()
    timeframe = getattr(TimeFrame, key, None)  # type: ignore[union-attr]
    if timeframe is None:
        raise ValueError(f"Unsupported aiomql timeframe: {value!r}")
    return timeframe


def to_ohlcv_frame(candles: Any) -> pd.DataFrame:
    return normalize_ohlcv_frame(candles)


def broker_snapshot_from_sources(
    *,
    symbol: Any,
    trader: Any,
    strategy: str,
    fallback_symbol: str,
    fallback_spread: float | None,
    fallback_min_lot: float | None,
    fallback_max_lot: float | None,
    fallback_lot_step: float | None,
) -> BrokerSnapshot | None:
    account_source = first_value(trader, ("account_info", "account", "account_snapshot"))
    if account_source is None:
        account_source = first_value(symbol, ("account_info", "account", "account_snapshot"))
    equity = number_from(account_source, ("equity",))
    balance = number_from(account_source, ("balance",))
    free_margin = number_from(account_source, ("margin_free", "free_margin", "marginFree"))
    if equity is None or balance is None or free_margin is None:
        return None

    contract_source = first_value(symbol, ("info", "symbol_info", "contract", "contract_info"))
    point = number_from(contract_source, ("point", "trade_tick_size"), default=number_from(symbol, ("point",)))
    raw_tick_value = number_from(contract_source, ("trade_tick_value", "tick_value", "tickValue"), default=number_from(symbol, ("tick_value",)))
    min_lot = number_from(contract_source, ("volume_min", "min_lot", "min_volume"), default=fallback_min_lot)
    max_lot = number_from(contract_source, ("volume_max", "max_lot", "max_volume"), default=fallback_max_lot)
    lot_step = number_from(contract_source, ("volume_step", "lot_step"), default=fallback_lot_step)
    pip_size = number_from(contract_source, ("pip_size",), default=infer_pip_size(fallback_symbol, point))
    pip_value = number_from(contract_source, ("pip_value", "pipValue"), default=pip_value_from_tick_value(raw_tick_value, point, pip_size))
    if point is None or pip_value is None or min_lot is None or max_lot is None or lot_step is None or pip_size is None:
        return None

    contract = SymbolContract(
        symbol=fallback_symbol,
        point=float(point),
        pip_size=float(pip_size),
        tick_value=float(pip_value),
        min_lot=float(min_lot),
        max_lot=float(max_lot),
        lot_step=float(lot_step),
        contract_size=number_from(contract_source, ("trade_contract_size", "contract_size")),
        currency_profit=text_from(contract_source, ("currency_profit", "profit_currency")),
    )
    positions = tuple(
        position
        for item in positions_from_sources(symbol=symbol, trader=trader)
        for position in [open_position_from_source(item, strategy=strategy)]
        if position is not None
    )
    return BrokerSnapshot(
        account=AccountSnapshot(
            equity=float(equity),
            balance=float(balance),
            free_margin=float(free_margin),
            currency=text_from(account_source, ("currency",), default="BASE") or "BASE",
        ),
        contract=contract,
        open_positions=positions,
        current_spread=number_from(contract_source, ("spread",), default=fallback_spread),
    )


def extract_broker_fill(
    *,
    order_result: Any,
    trade_parameters: dict[str, Any],
    symbol: str,
    direction: str,
) -> BrokerFill | None:
    external_id = text_from(order_result, ("deal", "deal_id", "ticket", "order", "external_id"))
    if external_id is None:
        return None
    price = number_from(order_result, ("price", "price_open", "price_current"), default=optional_float(trade_parameters.get("entry_price")))
    volume = number_from(order_result, ("volume", "volume_initial", "volume_current"), default=optional_float(trade_parameters.get("volume")))
    if price is None or volume is None:
        return None
    realized_pnl = number_from(order_result, ("profit", "realized_pnl", "pnl"))
    return BrokerFill(
        external_id=external_id,
        symbol=text_from(order_result, ("symbol",), default=symbol) or symbol,
        direction=direction,
        volume=float(volume),
        price=float(price),
        occurred_at=text_from(order_result, ("time", "time_done", "occurred_at")),
        realized_pnl=realized_pnl,
        commission=float(number_from(order_result, ("commission",), default=0.0) or 0.0),
        swap=float(number_from(order_result, ("swap",), default=0.0) or 0.0),
        entry_price=number_from(order_result, ("entry_price",), default=optional_float(trade_parameters.get("entry_price"))),
        exit_price=number_from(order_result, ("exit_price",), default=price if realized_pnl is not None else None),
        raw=order_result,
    )


def fill_outcome(realized_pnl: float) -> str:
    if realized_pnl > 0:
        return "win"
    if realized_pnl < 0:
        return "loss"
    return "breakeven"


def fill_price_return_pct(fill: BrokerFill) -> float:
    if fill.entry_price is None or fill.entry_price <= 0:
        return 0.0
    exit_price = fill.exit_price or fill.price
    if fill.direction == "short":
        return (fill.entry_price - exit_price) / fill.entry_price * 100.0
    return (exit_price - fill.entry_price) / fill.entry_price * 100.0


def positions_from_sources(*, symbol: Any, trader: Any) -> list[Any]:
    for source in (trader, symbol):
        positions = first_value(source, ("positions", "open_positions", "positions_get"))
        if positions is None:
            continue
        if isinstance(positions, list):
            return positions
        if isinstance(positions, tuple):
            return list(positions)
    return []


def open_position_from_source(value: Any, *, strategy: str) -> OpenPosition | None:
    symbol = text_from(value, ("symbol",))
    ticket = text_from(value, ("ticket", "id", "identifier"))
    volume = number_from(value, ("volume",))
    entry_price = number_from(value, ("price_open", "entry_price", "open_price"))
    if symbol is None or ticket is None or volume is None or entry_price is None:
        return None
    raw_type = str(value_from(value, "type") or value_from(value, "direction") or "").upper()
    direction = "short" if "SELL" in raw_type or raw_type in {"1", "-1", "SHORT"} else "long"
    comment = text_from(value, ("comment",))
    return OpenPosition(
        ticket=ticket,
        symbol=symbol,
        direction=direction,
        volume=float(volume),
        entry_price=float(entry_price),
        current_price=number_from(value, ("price_current", "current_price")),
        profit=number_from(value, ("profit",), default=0.0) or 0.0,
        strategy=strategy if comment is None or strategy in comment else None,
        magic=int(number_from(value, ("magic",), default=0) or 0) or None,
        comment=comment,
    )


def first_value(source: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        value = value_from(source, name)
        if value is not None:
            return value
    return None


def value_from(source: Any, name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    value = getattr(source, name, None)
    if callable(value):
        try:
            return value()
        except TypeError:
            return None
    return value


def number_from(source: Any, names: tuple[str, ...], default: float | None = None) -> float | None:
    value = first_value(source, names)
    if value is None:
        return default
    return optional_float(value)


def text_from(source: Any, names: tuple[str, ...], default: str | None = None) -> str | None:
    value = first_value(source, names)
    if value is None:
        return default
    return str(value)


def optional_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def infer_pip_size(symbol: str, point: float | None) -> float | None:
    if "JPY" in symbol.upper():
        return 0.01
    if point is None:
        return None
    return max(float(point) * 10.0, 0.0001)


def pip_value_from_tick_value(raw_tick_value: float | None, point: float | None, pip_size: float | None) -> float | None:
    if raw_tick_value is None or point is None or pip_size is None or point <= 0:
        return raw_tick_value
    return float(raw_tick_value) * (float(pip_size) / float(point))
