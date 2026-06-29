"""aiomql wrapper for the Bollinger Bands signal module."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import pandas as pd

from strategies.BollingerBand.core import BUY, SELL, AdaptiveRegimeConfig, ExitPlan, add_atr, calculate_bollinger_bands
from strategies.BollingerBand.core import generate_adaptive_bollinger_signals, generate_bb_rsi_signals, generate_bbma_signals
from strategies.BollingerBand.core import generate_mean_reversion_signals
from execution.base import (
    AiomqlStrategyBase,
    OrderType,
    SnapshotProvider,
    aiomql_available,
    broker_snapshot_from_sources as _broker_snapshot_from_sources,
    extract_broker_fill as _extract_broker_fill,
    optional_float as _optional_float,
    optional_string as _optional_string,
    require_aiomql,
    resolve_timeframe as _resolve_timeframe,
    to_ohlcv_frame as _to_ohlcv_frame,
)


logger = logging.getLogger(__name__)


class BollingerBandsAiomqlStrategy(AiomqlStrategyBase):
    """Bollinger Bands strategy for aiomql Bot orchestration."""

    parameters: ClassVar[dict[str, Any]] = {
        **AiomqlStrategyBase.parameters,
        "signal_mode": "mean_reversion",
        "adaptive_regime_mode": "hybrid",
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
        "session_start": None,
        "session_end": None,
        "atr_length": 14,
        "atr_stop_multiplier": 2.0,
        "take_profit_rr": 2.0,
        "take_profit_pips": 60.0,
        "trailing_atr_multiplier": 2.5,
        "trail_activation_rr": 1.0,
        "max_hold_bars": 50,
        "comment": "BollingerBands",
    }

    def __init__(
        self,
        *,
        symbol: Any,
        params: dict[str, Any] | None = None,
        trader: Any | None = None,
        sessions: Any | None = None,
        snapshot_provider: SnapshotProvider | None = None,
        name: str = "BollingerBands",
    ) -> None:
        super().__init__(
            symbol=symbol,
            params=params,
            trader=trader,
            sessions=sessions,
            snapshot_provider=snapshot_provider,
            name=name,
        )

    async def find_entry(self) -> None:
        candles = await self.symbol.copy_rates_from_pos(timeframe=self._timeframe(), count=int(self.count))
        data = _to_ohlcv_frame(candles)
        if len(data) < int(self.bb_window) + 2:
            logger.info("%s has insufficient candles for Bollinger signal", self._symbol_name())
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
        if signal_mode in {"adaptive", "adaptive_mean_reversion", "adaptive_breakout"}:
            return generate_adaptive_bollinger_signals(data, config=self._adaptive_config())
        raise ValueError("signal_mode must be one of: mean_reversion, bbma, bb_rsi, adaptive, adaptive_mean_reversion, adaptive_breakout")

    def _latest_entry_signal(self, signaled: pd.DataFrame) -> int:
        if bool(signaled["long_entry"].iloc[-1]):
            return BUY
        if bool(signaled["short_entry"].iloc[-1]):
            return SELL
        return 0

    def _build_trade_parameters(self, signaled: pd.DataFrame, signal: int) -> dict[str, Any]:
        params = self._parameter_snapshot()
        if signal == 0:
            return params

        exit_plan = self._exit_plan()
        with_atr = add_atr(signaled, window=exit_plan.atr_length)
        latest = with_atr.iloc[-1]
        entry_price = float(latest["close"])
        params.update(
            {
                "entry_price": entry_price,
                "volume": float(self.fixed_volume),
                "magic": int(self.magic),
                "comment": str(self.comment),
            }
        )
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
                "stop_loss_pips": abs(entry_price - stop_price) / self._configured_pip_size(),
            }
        )
        return params

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
        metadata = super()._journal_metadata()
        keys = (
            "atr_value",
            "atr_length",
            "atr_stop_multiplier",
            "trailing_atr_multiplier",
            "trail_activation_rr",
            "max_hold_bars",
        )
        metadata.update({key: self.trade_parameters.get(key) for key in keys if key in self.trade_parameters})
        return metadata

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
            regime_mode=self._adaptive_regime_mode(),
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
            max_spread=_optional_float(self.max_spread),
            session_start=_optional_string(self.session_start),
            session_end=_optional_string(self.session_end),
        )

    def _adaptive_regime_mode(self) -> str:
        signal_mode = str(self.signal_mode)
        if signal_mode == "adaptive_mean_reversion":
            return "mean_reversion"
        if signal_mode == "adaptive_breakout":
            return "breakout"
        return str(self.adaptive_regime_mode)
