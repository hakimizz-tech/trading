# execution

`execution` - broker-neutral live execution support for strategies, risk gates, position sizing, broker adapters, aiomql integration, and position trackers.

## Overview

The `execution` package is the boundary between strategy decisions and broker-specific APIs. The current live path uses aiomql/MetaTrader 5, but strategy code should depend on the normalized execution API so future adapters can target stocks, crypto exchanges, Solana DEXs, or paper-trading engines.

Application code should usually import from `execution`:

```python
from execution import BrokerSnapshot, BrokerOrderCheck, evaluate_live_execution_gate
from journal import TradeJournal
```

Use `execution.base` only when writing aiomql-specific strategy classes or aiomql adapter code.

## Modules

| Module | Purpose |
| --- | --- |
| `execution.state` | Broker-neutral dataclasses for accounts, contracts, positions, fills, order checks, and pending orders |
| `execution.adapters` | Protocols that broker adapters implement |
| `execution.gates` | Live execution gates for spread, max positions, daily loss, and sizing |
| `execution.sizing` | Broker-aware fixed-fractional position sizing |
| `execution.base` | aiomql strategy lifecycle and aiomql/MT5 object normalizers |
| `execution.trackers` | Scheduled position-management helpers |

## State Classes

### `AccountSnapshot`

> Normalized account state required by execution gates.

| Field | Type | Description |
| --- | --- | --- |
| `equity` | `float` | Current account equity |
| `balance` | `float` | Current account balance |
| `free_margin` | `float` | Available margin for new positions |
| `currency` | `str` | Account currency label |

### `SymbolContract`

> Broker contract details required for sizing and volume validation.

| Field | Type | Description |
| --- | --- | --- |
| `symbol` | `str` | Broker symbol |
| `point` | `float` | Smallest quoted point size |
| `pip_size` | `float` | Pip size used by strategy/risk sizing |
| `tick_value` | `float` | Account-currency value per pip per 1.0 lot |
| `min_lot` | `float` | Broker minimum trade volume |
| `max_lot` | `float` | Broker maximum trade volume |
| `lot_step` | `float` | Broker volume increment |
| `contract_size` | `float \| None` | Optional contract size |
| `currency_profit` | `str \| None` | Optional profit currency |

### `OpenPosition`

> Normalized open broker position.

| Field | Type | Description |
| --- | --- | --- |
| `ticket` | `str` | Broker position ticket or identifier |
| `symbol` | `str` | Broker symbol |
| `direction` | `str` | `long` or `short` |
| `volume` | `float` | Position volume |
| `entry_price` | `float` | Open price |
| `current_price` | `float \| None` | Latest broker price |
| `profit` | `float` | Floating profit |
| `strategy` | `str \| None` | Strategy tag when identifiable |
| `magic` | `int \| None` | Broker magic number or strategy id |
| `comment` | `str \| None` | Broker comment |

### `BrokerSnapshot`

> Complete broker state for one execution decision.

| Field | Type | Description |
| --- | --- | --- |
| `account` | `AccountSnapshot` | Normalized account state |
| `contract` | `SymbolContract` | Symbol contract details |
| `open_positions` | `tuple[OpenPosition, ...]` | Current open positions |
| `current_spread` | `float \| None` | Current spread in broker units |

| Method | Returns | Description |
| --- | --- | --- |
| `positions_for(symbol=None, strategy=None)` | `tuple[OpenPosition, ...]` | Filters open positions by symbol and/or strategy |

### `BrokerFill`

> Broker-confirmed fill or position close.

| Field | Type | Description |
| --- | --- | --- |
| `external_id` | `str` | Broker deal/order/fill identifier |
| `symbol` | `str` | Broker symbol |
| `direction` | `str` | `long` or `short` |
| `volume` | `float` | Filled volume |
| `price` | `float` | Fill price |
| `occurred_at` | `str \| None` | Broker event timestamp |
| `realized_pnl` | `float \| None` | Realized P&L when this is a close |
| `commission` | `float` | Broker commission |
| `swap` | `float` | Broker swap/financing |
| `entry_price` | `float \| None` | Entry price when known |
| `exit_price` | `float \| None` | Exit price when known |
| `raw` | `object \| None` | Original broker payload |

### `BrokerOrderCheck`

> Normalized pre-trade result similar to aiomql `Order.check()`.

| Field | Type | Description |
| --- | --- | --- |
| `allowed` | `bool` | Whether the broker preflight accepted the order |
| `symbol` | `str` | Broker symbol |
| `direction` | `str` | `long` or `short` |
| `volume` | `float` | Requested volume |
| `price` | `float \| None` | Checked order price |
| `margin` | `float \| None` | Required margin estimate |
| `expected_profit` | `float \| None` | Estimated profit at target |
| `expected_loss` | `float \| None` | Estimated loss at stop |
| `retcode` | `int \| None` | Broker return code |
| `comment` | `str \| None` | Broker comment |
| `raw` | `object \| None` | Original broker payload |

### `BrokerPendingOrder`

> Normalized active pending order.

| Field | Type | Description |
| --- | --- | --- |
| `ticket` | `str` | Broker pending-order ticket |
| `symbol` | `str` | Broker symbol |
| `direction` | `str` | `long` or `short` |
| `volume` | `float` | Pending order volume |
| `price` | `float` | Pending order price |
| `stop_loss` | `float \| None` | Stop-loss price |
| `take_profit` | `float \| None` | Take-profit price |
| `strategy` | `str \| None` | Strategy tag when identifiable |
| `magic` | `int \| None` | Broker magic number or strategy id |
| `comment` | `str \| None` | Broker comment |
| `raw` | `object \| None` | Original broker payload |

### `BrokerOrderCancelResult`

> Normalized result from cancelling a pending order.

| Field | Type | Description |
| --- | --- | --- |
| `ticket` | `str` | Broker pending-order ticket |
| `cancelled` | `bool` | Whether the broker confirmed cancellation |
| `retcode` | `int \| None` | Broker return code |
| `comment` | `str \| None` | Broker comment |
| `raw` | `object \| None` | Original broker payload |

## Adapter Protocols

### `BrokerDataAdapter`

> Read-only broker state needed by live execution gates and reconciliation.

| Method | Returns | Description |
| --- | --- | --- |
| `snapshot(symbol, strategy=None)` | `BrokerSnapshot` | Returns account, contract, spread, and open-position state |
| `history(date_from, date_to, group=None)` | `tuple[list[Mapping], list[Mapping]]` | Returns historical deals and orders |

### `BrokerExecutionAdapter`

> Broker order execution and pending-order management.

| Method | Returns | Description |
| --- | --- | --- |
| `check_market_order(symbol, direction, volume, parameters=None)` | `BrokerOrderCheck` | Validates margin/profit/loss assumptions before an order |
| `place_market_order(symbol, direction, volume, parameters=None)` | `BrokerFill \| None` | Places a market order and returns confirmed fill when available |
| `pending_orders(symbol=None, strategy=None)` | `list[BrokerPendingOrder]` | Returns active pending orders |
| `cancel_order(ticket, symbol=None)` | `BrokerOrderCancelResult` | Cancels an active pending order |

### `BrokerAdapter`

> Combined protocol for broker implementations.

| Inherits | Description |
| --- | --- |
| `BrokerDataAdapter` | Broker state and history |
| `BrokerExecutionAdapter` | Broker execution and pending-order management |

## Live Execution Gate

### `ExecutionGateResult`

| Field | Type | Description |
| --- | --- | --- |
| `allowed` | `bool` | Whether execution is allowed |
| `reason` | `str \| None` | Rejection reason |
| `volume` | `float \| None` | Final order volume |
| `metadata` | `dict[str, object]` | Risk-sizing metadata |

### `evaluate_live_execution_gate(...)`

| Parameter | Type | Description |
| --- | --- | --- |
| `trade_parameters` | `dict[str, object]` | Entry price, stop price, and strategy execution metadata |
| `snapshot` | `BrokerSnapshot` | Current broker/account state |
| `strategy` | `str` | Strategy tag |
| `symbol` | `str` | Broker symbol |
| `max_spread` | `float \| None` | Maximum allowed spread |
| `max_open_positions` | `int` | Maximum open positions for symbol/strategy |
| `max_daily_loss_pct` | `float \| None` | Daily loss cap as equity fraction |
| `max_daily_loss_amount` | `float \| None` | Absolute daily loss cap |
| `daily_net_pnl` | `float` | Current realized daily P&L |
| `use_risk_sizing` | `bool` | Whether to calculate volume from risk |
| `fixed_volume` | `float` | Fixed volume when risk sizing is disabled |
| `risk_per_trade` | `float` | Equity fraction risked per trade |
| `min_volume` | `float \| None` | Optional volume floor override |
| `max_volume` | `float \| None` | Optional volume cap override |
| `volume_step` | `float \| None` | Optional volume step override |

Checks performed:

- maximum spread
- maximum open positions
- maximum daily loss
- fixed-volume validity
- optional risk-based sizing using entry and stop prices

```python
gate = evaluate_live_execution_gate(
    trade_parameters={"entry_price": 1.0850, "stop_loss_price": 1.0800},
    snapshot=snapshot,
    strategy="bollinger-adaptive",
    symbol="EURUSD",
    max_spread=30.0,
    max_open_positions=1,
    max_daily_loss_pct=0.02,
    max_daily_loss_amount=None,
    daily_net_pnl=0.0,
    use_risk_sizing=True,
    fixed_volume=0.01,
    risk_per_trade=0.01,
    min_volume=None,
    max_volume=None,
    volume_step=None,
)
```

## Position Sizing

### `PositionSizeResult`

| Field | Type | Description |
| --- | --- | --- |
| `accepted` | `bool` | Whether sizing produced a valid volume |
| `volume` | `float` | Final rounded volume |
| `risk_amount` | `float` | Account-currency amount risked |
| `stop_distance_price` | `float` | Absolute price distance to stop |
| `stop_distance_pips` | `float` | Stop distance in pips |
| `risk_per_lot` | `float` | Account-currency risk for 1.0 lot |
| `reason` | `str \| None` | Rejection reason |

### `calculate_risk_position_size(...)`

| Parameter | Type | Description |
| --- | --- | --- |
| `equity` | `float` | Account equity |
| `risk_per_trade` | `float` | Equity fraction to risk |
| `entry_price` | `float` | Entry price |
| `stop_price` | `float` | Stop-loss price |
| `contract` | `SymbolContract` | Broker contract details |
| `min_volume` | `float \| None` | Optional minimum volume override |
| `max_volume` | `float \| None` | Optional maximum volume override |
| `volume_step` | `float \| None` | Optional volume step override |

```python
size = calculate_risk_position_size(
    equity=10_000.0,
    risk_per_trade=0.01,
    entry_price=1.0850,
    stop_price=1.0800,
    contract=contract,
)
```

## aiomql Integration

### `AiomqlStrategyBase`

> Template base class for aiomql strategies. Subclasses implement signal
> discovery; the base class owns the common execution lifecycle.

```python
from execution import AiomqlStrategyBase


class MyAiomqlStrategy(AiomqlStrategyBase):
    async def find_entry(self) -> None:
        # Update self.tracker and self.trade_parameters.
        ...
```

| Member | Type | Description |
| --- | --- | --- |
| `parameters` | `ClassVar[dict[str, Any]]` | Shared dry-run, risk, journal, accounting, and execution defaults |
| `find_entry()` | `async override hook` | Strategy-specific signal discovery implemented by each subclass |
| `trade()` | `async template method` | Runs signal discovery, gates, submission, journaling, and fill accounting |
| `trade_parameters` | `dict[str, Any]` | Mutable parameters passed through risk gates and order submission |
| `snapshot_provider` | `Callable \| None` | Optional broker snapshot dependency for testability and live execution |
| `journal` | `TradeJournal \| None` | Strategy event and trade persistence service |
| `ledger` | `TradeLedger \| None` | Confirmed realized P&L accounting service |

| Feature | Description |
| --- | --- |
| Dry-run/live handling | Live execution is disabled by default |
| Journal logging | Signals, blocks, submissions, fills, and closes can be recorded |
| Accounting hooks | Broker-confirmed fills/closes can post to ledger |
| Broker snapshot gate | Reads spread, account, contract, and positions |
| Risk gates | Spread, max open positions, max daily loss, fixed volume, risk sizing |
| Broker-fill recording | Converts broker result into journal/ledger records |

### aiomql Normalizers

| Function | Returns | Description |
| --- | --- | --- |
| `broker_snapshot_from_sources(...)` | `BrokerSnapshot \| None` | Normalizes symbol/trader/account data into a snapshot |
| `extract_broker_fill(...)` | `BrokerFill \| None` | Normalizes aiomql/MT5 send results into fills |
| `extract_order_check(...)` | `BrokerOrderCheck` | Normalizes aiomql `Order.check()` output |
| `pending_order_from_source(...)` | `BrokerPendingOrder \| None` | Normalizes aiomql `TradeOrder` objects |
| `order_cancel_result_from_source(...)` | `BrokerOrderCancelResult` | Normalizes aiomql cancel/send result |

These helpers accept dict-like or object-like broker payloads. Store original broker payloads in the returned object's `raw` field when useful.

### aiomql `RAM`

aiomql includes a `RAM` risk-assessment class for account-equity risk, risk-to-reward settings, pips, target volume, and helper checks such as losing-position limits. Use it inside aiomql-specific strategy or adapter code when you are working directly with aiomql `Account`, `ForexSymbol`, `Order`, `Positions`, or `Trader` objects.

The shared project layer still uses `BrokerSnapshot`, `evaluate_live_execution_gate`, and `calculate_risk_position_size` so strategies remain portable beyond aiomql.

| Field | Type | Description |
| --- | --- | --- |
| `RAM.get_amount` | `aiomql method` | Computes risk amount from account equity and configured risk percentage. |
| `risk` | `float` | aiomql RAM risk percentage used to calculate amount at risk. |
| `risk_to_reward` | `float` | aiomql RAM reward multiple for target calculations. |
| `pips` | `float` | aiomql RAM stop or target distance input, depending on strategy setup. |
| `check_losing_positions` | `aiomql method` | Helper for blocking new trades when losing-position rules are violated. |
| `calculate_risk_position_size` | `project function` | Broker-neutral sizing from equity, stop distance, pip value, and lot constraints. |
| `evaluate_live_execution_gate` | `project function` | Broker-neutral gate for spread, open positions, daily loss, fixed volume, and risk sizing. |

Recommended layering:

- Use aiomql `RAM` for aiomql-native account/risk checks that require live MT5 objects.
- Convert live account, symbol, spread, and positions into `BrokerSnapshot`.
- Run `evaluate_live_execution_gate` before order submission.
- Store RAM output or rejection details in journal metadata for auditability.
- Keep `RAM` out of shared strategy signal code so the same strategy can later run on stocks, crypto exchanges, Solana DEXs, or a paper broker.

## Position Trackers

### `TrackerDecision`

| Field | Type | Description |
| --- | --- | --- |
| `tracker` | `str` | Tracker name |
| `ticket` | `str` | Position ticket |
| `should_close` | `bool` | Whether tracker wants the position closed |
| `reason` | `str` | Decision reason |
| `live_management` | `bool` | Whether close execution is allowed |

### Tracker Methods

| Function | Returns | Description |
| --- | --- | --- |
| `build_tracker_callable(name, params=None)` | `Callable` | Builds a scheduled tracker callable |
| `exit_at_profit(...)` | `list[TrackerDecision]` | Signals/closes positions whose profit reaches a threshold |
| `exit_at_points(...)` | `list[TrackerDecision]` | Signals/closes positions whose point movement reaches a threshold |

Trackers default to signal-only behavior. They only call a broker close function when `live_management=True` and a `close_position` callable is configured.

## Building A New Broker Adapter

A future broker adapter should implement `BrokerAdapter`.

```python
from collections.abc import Mapping
from typing import Any

from execution import (
    AccountSnapshot,
    BrokerAdapter,
    BrokerFill,
    BrokerOrderCancelResult,
    BrokerOrderCheck,
    BrokerPendingOrder,
    BrokerSnapshot,
    SymbolContract,
)


class MyBrokerAdapter:
    async def snapshot(self, *, symbol: str, strategy: str | None = None) -> BrokerSnapshot:
        return BrokerSnapshot(
            account=AccountSnapshot(equity=10_000.0, balance=10_000.0, free_margin=9_000.0),
            contract=SymbolContract(
                symbol=symbol,
                point=0.00001,
                pip_size=0.0001,
                tick_value=10.0,
                min_lot=0.01,
                max_lot=100.0,
                lot_step=0.01,
            ),
            current_spread=12.0,
        )

    async def history(
        self,
        *,
        date_from: object,
        date_to: object,
        group: str | None = None,
    ) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
        return ([], [])

    async def check_market_order(
        self,
        *,
        symbol: str,
        direction: str,
        volume: float,
        parameters: Mapping[str, Any] | None = None,
    ) -> BrokerOrderCheck:
        return BrokerOrderCheck(allowed=True, symbol=symbol, direction=direction, volume=volume)

    async def place_market_order(
        self,
        *,
        symbol: str,
        direction: str,
        volume: float,
        parameters: Mapping[str, Any] | None = None,
    ) -> BrokerFill | None:
        return None

    async def pending_orders(
        self,
        *,
        symbol: str | None = None,
        strategy: str | None = None,
    ) -> list[BrokerPendingOrder]:
        return []

    async def cancel_order(
        self,
        *,
        ticket: str,
        symbol: str | None = None,
    ) -> BrokerOrderCancelResult:
        return BrokerOrderCancelResult(ticket=ticket, cancelled=False, comment="paper adapter does not cancel")


adapter: BrokerAdapter = MyBrokerAdapter()
```

Adapter rules:

- Return normalized execution objects, not raw broker objects.
- Store raw broker payloads in the `raw` field when useful.
- Keep credentials and broker sessions inside the adapter.
- Do not let strategies import broker SDKs directly.
- Do not post accounting entries from raw signals; post them from confirmed fills/closes.

## Safety Notes

- Live trading should remain disabled by default.
- aiomql live execution requires Windows, MetaTrader 5, broker credentials, and a demo validation pass.
- Every live strategy should have a session gate, risk gate, spread gate, and journaling enabled.
- Broker-confirmed fills should flow into the journal and ledger; signals and rejected orders should not affect accounting.

## Tests

Useful focused tests:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m unittest tests.test_execution_adapters
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m unittest tests.test_execution_risk
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m unittest tests.test_aiomql_order_bridge
```
