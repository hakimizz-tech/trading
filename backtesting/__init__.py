"""Shared backtesting interfaces for strategy packages."""

from backtesting.backtrader_engine import BacktraderConfig, BacktraderResult, run_backtrader
from backtesting.event_engine import EventBacktestConfig, EventBacktestResult, EventDrivenBacktester
from backtesting.execution_models import (
    BrokerProfile,
    ExecutionModel,
    IntrabarCollisionPolicy,
    SimulatedFill,
    SimulatedOrder,
    SimulatedOrderStatus,
    SimulatedOrderType,
)
from backtesting.signals import PreparedSignals
from backtesting.validation import SignalValidationError, SignalValidationReport, validate_prepared_signals
from backtesting.vectorbt_engine import VectorBTConfig, VectorBTResult, run_vectorbt

__all__ = [
    "BrokerProfile",
    "BacktraderConfig",
    "BacktraderResult",
    "EventBacktestConfig",
    "EventBacktestResult",
    "EventDrivenBacktester",
    "ExecutionModel",
    "IntrabarCollisionPolicy",
    "PreparedSignals",
    "SignalValidationError",
    "SignalValidationReport",
    "SimulatedFill",
    "SimulatedOrder",
    "SimulatedOrderStatus",
    "SimulatedOrderType",
    "VectorBTConfig",
    "VectorBTResult",
    "run_vectorbt",
    "run_backtrader",
    "validate_prepared_signals",
]
