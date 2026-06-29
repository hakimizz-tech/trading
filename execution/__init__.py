"""Pure-Python execution support shared by live strategy adapters."""

from typing import Any

try:
    from execution.base import (
        AiomqlStrategyBase,
        OrderType,
        ScalpTrader,
        Sessions,
        SnapshotProvider,
        TimeFrame,
        Tracker,
        Trader,
        aiomql_available,
        broker_snapshot_from_sources,
        extract_broker_fill,
        extract_order_check,
        order_cancel_result_from_source,
        optional_float,
        optional_string,
        pending_order_from_source,
        require_aiomql,
        resolve_timeframe,
        to_ohlcv_frame,
    )
except ImportError as exc:  # pragma: no cover - depends on optional aiomql/pandas runtime.
    _AIOMQL_BASE_IMPORT_ERROR = exc
    AiomqlStrategyBase = OrderType = ScalpTrader = Sessions = SnapshotProvider = TimeFrame = Tracker = Trader = None

    def aiomql_available() -> bool:
        return False

    def require_aiomql() -> None:
        raise RuntimeError(
            "aiomql execution support is unavailable in this environment. Install the aiomql runtime "
            "dependencies on the Windows/MT5 execution host."
        ) from _AIOMQL_BASE_IMPORT_ERROR

    def broker_snapshot_from_sources(*args: Any, **kwargs: Any) -> Any:
        require_aiomql()

    def extract_broker_fill(*args: Any, **kwargs: Any) -> Any:
        require_aiomql()

    def extract_order_check(*args: Any, **kwargs: Any) -> Any:
        require_aiomql()

    def pending_order_from_source(*args: Any, **kwargs: Any) -> Any:
        require_aiomql()

    def order_cancel_result_from_source(*args: Any, **kwargs: Any) -> Any:
        require_aiomql()

    def resolve_timeframe(*args: Any, **kwargs: Any) -> Any:
        require_aiomql()

    def to_ohlcv_frame(*args: Any, **kwargs: Any) -> Any:
        require_aiomql()

    def optional_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
from execution.adapters import BrokerAdapter, BrokerDataAdapter, BrokerExecutionAdapter
from execution.gates import ExecutionGateResult, evaluate_live_execution_gate
from execution.sizing import PositionSizeResult, calculate_risk_position_size
from execution.state import (
    AccountSnapshot,
    BrokerFill,
    BrokerOrderCancelResult,
    BrokerOrderCheck,
    BrokerPendingOrder,
    BrokerSnapshot,
    OpenPosition,
    SymbolContract,
)

__all__ = [
    "AccountSnapshot",
    "BrokerFill",
    "BrokerOrderCancelResult",
    "BrokerOrderCheck",
    "BrokerPendingOrder",
    "BrokerAdapter",
    "BrokerDataAdapter",
    "BrokerExecutionAdapter",
    "BrokerSnapshot",
    "OpenPosition",
    "PositionSizeResult",
    "SymbolContract",
    "ExecutionGateResult",
    "OrderType",
    "ScalpTrader",
    "Sessions",
    "SnapshotProvider",
    "AiomqlStrategyBase",
    "TimeFrame",
    "Tracker",
    "Trader",
    "aiomql_available",
    "broker_snapshot_from_sources",
    "calculate_risk_position_size",
    "extract_broker_fill",
    "extract_order_check",
    "order_cancel_result_from_source",
    "optional_float",
    "optional_string",
    "pending_order_from_source",
    "require_aiomql",
    "resolve_timeframe",
    "to_ohlcv_frame",
    "evaluate_live_execution_gate",
]
