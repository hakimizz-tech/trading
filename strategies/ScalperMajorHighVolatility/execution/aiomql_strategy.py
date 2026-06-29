"""aiomql adapter for Scalper Major High Volatility.

The adapter is intentionally dry-run-first. It evaluates the newly closed candle,
records signal intent through the shared execution base, and relies on shared live
gates before any order can be submitted.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from execution.base import AiomqlStrategyBase, OrderType, to_ohlcv_frame
from strategies.ScalperMajorHighVolatility.core import (
    ScalperMajorConfig,
    compute_scalper_major_indicators,
    generate_scalper_major_signals,
)


logger = logging.getLogger(__name__)


class ScalperMajorAiomqlStrategy(AiomqlStrategyBase):
    """Execute Scalper Major signals through aiomql with shared risk gates."""

    parameters = {
        **AiomqlStrategyBase.parameters,
        "strategy_tag": "ScalperMajorHighVolatility",
        "timeframe": "H1",
        "interval": "H1",
        "count": 300,
        "signal_candle_offset": 1,
        "basket_recovery_enabled": False,
        "max_recovery_positions": 4,
        "grid_atr_multiple": 1.0,
        "profit_to_loss_ratio": 3.0,
        "rsi_period": 14,
        "sma_period": 20,
        "atr_period": 14,
        "oversold_rsi": 30.0,
        "overbought_rsi": 70.0,
        "min_sma_distance_atr": 0.25,
        "min_body_to_range": 0.75,
        "max_wick_to_range": 0.15,
        "stop_atr_multiple": 1.5,
        "take_profit_atr_multiple": 1.0,
        "comment": "ScalperMajor",
        "use_risk_sizing": True,
        "risk_per_trade": 0.01,
    }

    async def find_entry(self) -> None:
        candles = await self.symbol.copy_rates_from_pos(timeframe=self._timeframe(), count=int(self.count))
        data = to_ohlcv_frame(candles)
        if len(data) < max(int(self.sma_period), int(self.rsi_period), int(self.atr_period)) + 2:
            self._set_tracker_order(None)
            await self.sleep(secs=self.tracker.snooze)
            return

        config = self._strategy_config()
        indicators = compute_scalper_major_indicators(data, config)
        signals = generate_scalper_major_signals(data, config)
        signal_offset = max(1, int(self.signal_candle_offset))
        signal_row = signals.iloc[-signal_offset]
        signal_time = signals.index[-signal_offset]
        price = float(data["close"].iloc[-signal_offset])
        atr = float(indicators["atr"].iloc[-signal_offset]) if pd.notna(indicators["atr"].iloc[-signal_offset]) else 0.0

        order_type = None
        direction = None
        if bool(signal_row["long_entry"]):
            order_type = getattr(OrderType, "BUY", None)
            direction = "long"
        elif bool(signal_row["short_entry"]):
            order_type = getattr(OrderType, "SELL", None)
            direction = "short"

        if order_type is None or direction is None:
            self._set_tracker_order(None)
            logger.debug("No Scalper Major signal on %s at %s", self._symbol_name(), signal_time)
            return

        stop_distance = max(float(self.stop_loss_pips) * self._configured_pip_size(), config.stop_atr_multiple * atr)
        if direction == "long":
            stop_loss = price - stop_distance
            take_profit = price + stop_distance * float(self.take_profit_rr)
        else:
            stop_loss = price + stop_distance
            take_profit = price - stop_distance * float(self.take_profit_rr)

        self.trade_parameters = {
            **self._parameter_snapshot(),
            "entry_price": price,
            "stop_loss_price": stop_loss,
            "take_profit_price": take_profit,
            "stop_price": stop_loss,
            "signal_timestamp": str(signal_time),
            "entry_strategy": "rsi_sma20_marubozu_h1",
            "exit_strategy": "broker_gated_atr_or_basket",
            "basket_recovery_enabled": bool(self.basket_recovery_enabled),
            "max_recovery_positions": int(self.max_recovery_positions),
            "grid_atr_multiple": float(self.grid_atr_multiple),
            "profit_to_loss_ratio": float(self.profit_to_loss_ratio),
        }
        self._set_tracker_order(order_type)

    def _strategy_config(self) -> ScalperMajorConfig:
        return ScalperMajorConfig(
            rsi_period=int(self.rsi_period),
            sma_period=int(self.sma_period),
            atr_period=int(self.atr_period),
            oversold_rsi=float(self.oversold_rsi),
            overbought_rsi=float(self.overbought_rsi),
            min_sma_distance_atr=float(self.min_sma_distance_atr),
            min_body_to_range=float(self.min_body_to_range),
            max_wick_to_range=float(self.max_wick_to_range),
            stop_atr_multiple=float(self.stop_atr_multiple),
            take_profit_atr_multiple=float(self.take_profit_atr_multiple),
            initial_cash=20_000.0,
            risk_fraction=float(self.risk_per_trade),
        )

    def _set_tracker_order(self, order_type: Any | None) -> None:
        try:
            self.tracker.update(order_type=order_type, snooze=self.tracker.snooze)
        except AttributeError:
            self.tracker.order_type = order_type
