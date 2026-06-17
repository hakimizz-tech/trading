"""aiomql wrapper for the Bollinger Bands signal module.

The indicator and signal math lives in ``BollingerBand.core`` so it can
be tested on Linux without MetaTrader 5. This file is the Windows/aiomql bridge.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import pandas as pd

from accounting import SQLiteLedger
from BollingerBand.core import BUY, SELL, AdaptiveRegimeConfig, ExitPlan, add_atr, calculate_bollinger_bands
from BollingerBand.core import generate_bb_rsi_signals, generate_bbma_signals
from BollingerBand.core import generate_adaptive_bollinger_signals, generate_mean_reversion_signals
from journal import JournalEvent, SQLiteTradeJournal, utc_now

try:
    from aiomql import ForexSymbol, OrderType, ScalpTrader, Sessions, Strategy, TimeFrame, Tracker, Trader
except ImportError as exc:  # pragma: no cover - exercised on non-aiomql systems
    AIOMQL_IMPORT_ERROR = exc
    ForexSymbol = OrderType = ScalpTrader = Sessions = Strategy = TimeFrame = Tracker = Trader = None  # type: ignore[assignment]
else:
    AIOMQL_IMPORT_ERROR = None


logger = logging.getLogger(__name__)


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


class BollingerBandsAiomqlStrategy(Strategy if Strategy is not None else object):  # type: ignore[misc,valid-type]
    """Bollinger Bands strategy wrapper for aiomql Bot orchestration."""

    parameters: ClassVar[dict[str, Any]] = {
        "signal_mode": "mean_reversion",
        "timeframe": "M15",
        "interval": "M15",
        "count": 300,
        "bb_window": 20,
        "bb_num_std": 2.0,
        "rsi_window": 14,
        "rsi_oversold": 30.0,
        "rsi_overbought": 70.0,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "bandwidth_lookback": 120,
        "squeeze_quantile": 0.20,
        "wide_quantile": 0.60,
        "squeeze_release_bars": 5,
        "breakout_buffer": 0.0,
        "require_volume_confirmation": False,
        "volume_window": 20,
        "volume_multiplier": 1.2,
        "atr_length": 14,
        "atr_stop_multiplier": 2.0,
        "take_profit_rr": 2.0,
        "trailing_atr_multiplier": 2.5,
        "trail_activation_rr": 1.0,
        "max_hold_bars": 50,
        "timeout_seconds": 60 * 60,
        "live_trading": False,
        "max_spread": 30.0,
        "max_open_positions": 1,
        "risk_per_trade": 0.01,
        "fixed_volume": 0.01,
        "stop_loss_pips": 30.0,
        "take_profit_pips": 60.0,
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
        name: str = "BollingerBands",
    ) -> None:
        require_aiomql()
        super().__init__(symbol=symbol, params=params, sessions=sessions, name=name)
        self.tracker = Tracker(snooze=self._interval_seconds())  # type: ignore[operator]
        self.trader = trader or ScalpTrader(symbol=self.symbol)  # type: ignore[operator]
        self.trade_parameters: dict[str, Any] = dict(self.parameters)
        self.journal = SQLiteTradeJournal(str(self.journal_db_path)) if bool(self.journal_enabled) else None
        self.ledger = SQLiteLedger(str(self.accounting_db_path)) if bool(self.accounting_enabled) else None

    async def find_entry(self) -> None:
        candles = await self.symbol.copy_rates_from_pos(timeframe=self._timeframe(), count=int(self.count))
        data = _to_ohlcv_frame(candles)
        if len(data) < int(self.bb_window) + 2:
            logger.info("%s has insufficient candles for Bollinger signal", self.symbol.name)
            self.tracker.update(order_type=None, snooze=self._interval_seconds())
            return

        signaled = self._generate_signals(data)
        latest_signal = self._latest_entry_signal(signaled)
        self.trade_parameters = self._build_trade_parameters(signaled, latest_signal)

        if latest_signal == BUY:
            self.tracker.update(order_type=OrderType.BUY, snooze=int(self.timeout_seconds))  # type: ignore[union-attr]
        elif latest_signal == SELL:
            self.tracker.update(order_type=OrderType.SELL, snooze=int(self.timeout_seconds))  # type: ignore[union-attr]
        else:
            self.tracker.update(order_type=None, snooze=self._interval_seconds())

    async def trade(self) -> None:
        await self.find_entry()

        if self.tracker.order_type is None:
            await self.sleep(secs=self.tracker.snooze)
            return

        if not self._execution_gate_allows_trade():
            logger.info("Execution gate blocked %s signal on %s", self.tracker.order_type, self.symbol.name)
            self._journal_signal(status="blocked", mode="live" if bool(self.live_trading) else "dry_run")
            await self.delay(secs=self.tracker.snooze)
            return

        if not bool(self.live_trading):
            logger.info("Dry-run signal for %s: %s", self.symbol.name, self.tracker.order_type)
            self._journal_signal(status="dry_run", mode="dry_run")
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
        await self.delay(secs=self.tracker.snooze)

    def _generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        enriched = calculate_bollinger_bands(
            data,
            window=int(self.bb_window),
            num_std=float(self.bb_num_std),
            price_col="close",
        )
        signal_mode = str(self.signal_mode)
        if signal_mode == "mean_reversion":
            return generate_mean_reversion_signals(enriched)
        if signal_mode == "bbma":
            return generate_bbma_signals(enriched)
        if signal_mode == "bb_rsi":
            return generate_bb_rsi_signals(enriched)
        if signal_mode == "adaptive":
            return generate_adaptive_bollinger_signals(data, config=self._adaptive_config())
        raise ValueError("signal_mode must be one of: mean_reversion, bbma, bb_rsi, adaptive")

    def _latest_entry_signal(self, signaled: pd.DataFrame) -> int:
        if bool(signaled["long_entry"].iloc[-1]):
            return BUY
        if bool(signaled["short_entry"].iloc[-1]):
            return SELL
        return 0

    def _build_trade_parameters(self, signaled: pd.DataFrame, signal: int) -> dict[str, Any]:
        params = dict(self.parameters)
        if signal == 0:
            return params

        exit_plan = self._exit_plan()
        with_atr = add_atr(signaled, window=exit_plan.atr_length)
        latest = with_atr.iloc[-1]
        entry_price = float(latest["close"])
        params.update({"entry_price": entry_price, "volume": float(self.fixed_volume)})
        atr_value = float(latest[f"atr_{exit_plan.atr_length}"])
        if not pd.notna(atr_value):
            return params

        risk = atr_value * exit_plan.atr_stop_multiplier
        if signal == BUY:
            stop_price = entry_price - risk
            take_profit_price = entry_price + risk * exit_plan.take_profit_rr
        else:
            stop_price = entry_price + risk
            take_profit_price = entry_price - risk * exit_plan.take_profit_rr

        params.update(
            {
                "entry_strategy": str(self.signal_mode),
                "exit_strategy": "atr_stop_rr_target_atr_trailing_time_stop",
                "stop_loss_price": stop_price,
                "take_profit_price": take_profit_price,
                "atr_value": atr_value,
                "atr_length": exit_plan.atr_length,
                "atr_stop_multiplier": exit_plan.atr_stop_multiplier,
                "take_profit_rr": exit_plan.take_profit_rr,
                "trailing_atr_multiplier": exit_plan.trailing_atr_multiplier,
                "trail_activation_rr": exit_plan.trail_activation_rr,
                "max_hold_bars": exit_plan.max_hold_bars,
            }
        )
        return params

    def _execution_gate_allows_trade(self) -> bool:
        """Keep live-trading risk gates explicit before order placement."""
        if float(self.fixed_volume) <= 0:
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

    def _journal_signal(self, *, status: str, mode: str) -> str | None:
        if self.journal is None:
            return None
        try:
            direction = self._journal_direction()
            entry_price = float(self.trade_parameters.get("entry_price", 0.0))
            trade_id = self.journal.record_signal_trade(
                token=self._symbol_name(),
                direction=direction,
                entry_price=entry_price,
                size_sol=float(self.trade_parameters.get("volume", self.fixed_volume)),
                strategy=self._journal_strategy_tag(),
                rationale=self._journal_rationale(direction),
                status=status,
                mode=mode,
                source=f"aiomql:{self.name}",
                stop_price=_optional_float(self.trade_parameters.get("stop_loss_price")),
                target_price=_optional_float(self.trade_parameters.get("take_profit_price")),
                risk_reward=_optional_float(self.trade_parameters.get("take_profit_rr")),
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
                    price=_optional_float(self.trade_parameters.get("entry_price")),
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
        if "SELL" in order_name:
            return "short"
        return "long"

    def _journal_strategy_tag(self) -> str:
        signal_mode = str(self.signal_mode)
        tags = {
            "mean_reversion": "range-fade",
            "bb_rsi": "oversold-bounce",
            "bbma": "trend-continuation",
            "adaptive": "bollinger-adaptive",
        }
        return tags.get(signal_mode, f"bollinger-{signal_mode}")

    def _journal_rationale(self, direction: str) -> str:
        entry_price = self.trade_parameters.get("entry_price", "unknown")
        stop_price = self.trade_parameters.get("stop_loss_price", "unknown")
        target_price = self.trade_parameters.get("take_profit_price", "unknown")
        return (
            f"{self._symbol_name()} {direction} {self.signal_mode} Bollinger signal on {self.timeframe}. "
            f"Entry {entry_price}, stop {stop_price}, target {target_price}."
        )

    def _journal_metadata(self) -> dict[str, Any]:
        keys = (
            "entry_strategy",
            "exit_strategy",
            "atr_value",
            "atr_length",
            "atr_stop_multiplier",
            "trailing_atr_multiplier",
            "trail_activation_rr",
            "max_hold_bars",
            "risk_per_trade",
            "max_spread",
            "max_open_positions",
        )
        metadata = {key: self.trade_parameters.get(key) for key in keys if key in self.trade_parameters}
        metadata["timeframe"] = str(self.timeframe)
        metadata["interval"] = str(self.interval)
        metadata["live_trading"] = bool(self.live_trading)
        return metadata

    def _symbol_name(self) -> str:
        return str(getattr(self.symbol, "name", self.symbol))

    def _exit_plan(self) -> ExitPlan:
        return ExitPlan(
            atr_length=int(self.atr_length),
            atr_stop_multiplier=float(self.atr_stop_multiplier),
            take_profit_rr=float(self.take_profit_rr),
            trailing_atr_multiplier=float(self.trailing_atr_multiplier),
            trail_activation_rr=float(self.trail_activation_rr),
            max_hold_bars=int(self.max_hold_bars),
        )

    def _adaptive_config(self) -> AdaptiveRegimeConfig:
        return AdaptiveRegimeConfig(
            bb_window=int(self.bb_window),
            bb_num_std=float(self.bb_num_std),
            rsi_window=int(self.rsi_window),
            rsi_oversold=float(self.rsi_oversold),
            rsi_overbought=float(self.rsi_overbought),
            macd_fast=int(self.macd_fast),
            macd_slow=int(self.macd_slow),
            macd_signal=int(self.macd_signal),
            bandwidth_lookback=int(self.bandwidth_lookback),
            squeeze_quantile=float(self.squeeze_quantile),
            wide_quantile=float(self.wide_quantile),
            squeeze_release_bars=int(self.squeeze_release_bars),
            breakout_buffer=float(self.breakout_buffer),
            require_volume_confirmation=bool(self.require_volume_confirmation),
            volume_window=int(self.volume_window),
            volume_multiplier=float(self.volume_multiplier),
        )

    def _timeframe(self) -> Any:
        return _resolve_timeframe(str(self.timeframe))

    def _interval_seconds(self) -> int:
        interval = _resolve_timeframe(str(self.interval))
        return int(getattr(interval, "seconds", 60))


def _resolve_timeframe(value: str) -> Any:
    require_aiomql()
    key = value.strip().upper()
    timeframe = getattr(TimeFrame, key, None)  # type: ignore[union-attr]
    if timeframe is None:
        raise ValueError(f"Unsupported aiomql timeframe: {value!r}")
    return timeframe


def _to_ohlcv_frame(candles: Any) -> pd.DataFrame:
    data = pd.DataFrame(candles).copy()
    data.columns = [str(column).strip().lower() for column in data.columns]
    rename_map = {"tick_volume": "volume", "real_volume": "volume"}
    data = data.rename(columns={key: value for key, value in rename_map.items() if key in data.columns})
    required = {"open", "high", "low", "close"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Candle data missing required columns: {sorted(missing)}")
    if "volume" not in data.columns:
        data["volume"] = 0.0
    return data[["open", "high", "low", "close", "volume"]].astype(float)


def _optional_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None
