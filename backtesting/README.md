# Shared Backtesting Contract

The `backtesting` package provides a broker-neutral signal contract, runtime
validation, shared vectorbt and Backtrader runners, and a deterministic custom
event simulator. Strategy logic prepares signals once and sends the same
validated data through fast research and realistic execution paths.

## Responsibilities

| Layer | Responsibility |
| --- | --- |
| Strategy core | Calculate indicators and trading rules |
| Strategy signal adapter | Convert strategy output into `PreparedSignals` |
| Shared `backtesting` package | Validate signals and provide vectorized and event-driven engines |
| Strategy backtest engine | Supply strategy-specific configuration and reporting |
| Reporting package | Export metrics, trades, equity, drawdown, and charts |
| Live execution | Convert current signals into broker orders; it does not use simulated fills |

Backtesting objects are not aiomql API objects. aiomql is used later by the live
execution layer.

## Public API

```python
from backtesting import (
    EventDrivenBacktester,
    PreparedSignals,
    run_backtrader,
    run_vectorbt,
)
```

### `PreparedSignals`

`PreparedSignals` is an immutable dataclass containing market data and aligned
entry, exit, and optional stop series.

| Field | Type | Description |
| --- | --- | --- |
| `data` | `pandas.DataFrame` | Enriched market data containing OHLCV, indicators, regimes, and other strategy diagnostics |
| `close` | `pandas.Series` | Numeric close prices used by the portfolio simulator |
| `long_entries` | `pandas.Series` | Boolean signal that opens a long position when `True` |
| `long_exits` | `pandas.Series` | Boolean signal that closes a long position when `True` |
| `short_entries` | `pandas.Series` | Boolean signal that opens a short position when `True` |
| `short_exits` | `pandas.Series` | Boolean signal that closes a short position when `True` |
| `stop_loss` | `pandas.Series \| None` | Optional non-negative stop-loss distance as a fraction of entry price |
| `take_profit` | `pandas.Series \| None` | Optional non-negative take-profit distance as a fraction of entry price |

For vectorbt, a stop value of `0.02` means 2% from the entry price. It does not
mean an absolute price of `0.02`.

## Data Requirements

All series should:

- use the same chronological, unique index
- have the same length as `data`
- contain no missing close prices
- use boolean values for entry and exit signals
- replace missing signals with `False`
- avoid look-ahead data
- express stops as non-negative fractional distances

Call `signals.validate()` to enforce these conditions. All shared engines call
it automatically before simulation.

| Validation | Result |
| --- | --- |
| Empty, duplicate, or unsorted index | Error |
| Series index or length mismatch | Error |
| Missing, non-finite, or non-positive close | Error |
| Non-boolean or missing signal values | Error |
| Negative or non-finite stop distance | Error |
| Conflicting entry/exit signals | Error |
| Columns named like `future`, `target`, `label`, or `lead` | Warning requiring human review |

Column-name checks can identify obvious leakage but cannot prove that strategy
logic is free from look-ahead. Walk-forward tests and code review remain
required.

```python
import pandas as pd

from backtesting import PreparedSignals


def prepare_signals(data: pd.DataFrame) -> PreparedSignals:
    frame = data.sort_index().copy()
    close = frame["close"].astype(float)

    fast = close.rolling(10).mean()
    slow = close.rolling(30).mean()

    long_entries = (fast.gt(slow) & fast.shift(1).le(slow.shift(1))).fillna(False)
    long_exits = (fast.lt(slow) & fast.shift(1).ge(slow.shift(1))).fillna(False)

    frame["fast_sma"] = fast
    frame["slow_sma"] = slow
    frame["long_entry"] = long_entries
    frame["long_exit"] = long_exits

    return PreparedSignals(
        data=frame,
        close=close,
        long_entries=long_entries.astype(bool),
        long_exits=long_exits.astype(bool),
        short_entries=pd.Series(False, index=frame.index, dtype=bool),
        short_exits=pd.Series(False, index=frame.index, dtype=bool),
        stop_loss=pd.Series(0.02, index=frame.index, dtype=float),
        take_profit=pd.Series(0.04, index=frame.index, dtype=float),
    )
```

## Signal Semantics

| Signal combination | Meaning |
| --- | --- |
| `long_entries=True` | Request a long entry at that bar |
| `long_exits=True` | Request closure of an existing long position |
| `short_entries=True` | Request a short entry at that bar |
| `short_exits=True` | Request closure of an existing short position |
| All signals `False` | Hold the current state |

How simultaneous or opposite signals are resolved belongs to the engine
configuration. For example, vectorbt's `upon_opposite_entry` setting determines
whether an opposite entry closes, reverses, or is ignored.

Avoid setting entry and exit signals for the same direction on the same bar
unless the selected engine behavior is intentional and tested.

## Runtime Validation

```python
report = signals.validate(raise_on_error=False)
if not report.valid:
    print(report.errors)
print(report.warnings)

# Default behavior raises SignalValidationError on structural defects.
signals.validate()
```

## Choosing An Engine

| Engine | Function | Best use | Main trade-off |
| --- | --- | --- | --- |
| vectorbt | `run_vectorbt()` | Fast screening, optimization, and portfolio statistics | Simplified order lifecycle |
| Backtrader | `run_backtrader()` | Native event-driven orders, broker callbacks, OCO exits, and analyzers | Slower than vectorized execution |
| Custom event engine | `EventDrivenBacktester.run()` | Broker-profile stress tests, partial fills, dynamic spread, latency, swap, and margin stop-out | Generic model must be calibrated to the broker |

Use vectorbt first for broad research. Validate surviving configurations with
Backtrader and the custom event engine before MT5 Strategy Tester and demo
trading.

## Shared vectorbt Engine

```python
from backtesting import VectorBTConfig, run_vectorbt

signals = prepare_signals(ohlcv)
result = run_vectorbt(
    signals,
    config=VectorBTConfig(
        init_cash=10_000.0,
        fees=0.0002,
        slippage=0.0001,
        size=0.95,
        freq="1h",
    ),
)

print(result.stats)
print(result.trades)
```

The shared runner adds stop-loss and take-profit arrays only when present.
Strategy-specific vectorbt engines may still be used when a strategy requires
special sizing, optimization, or result fields.

## Shared Backtrader Engine

Backtrader reads the prepared signals through a custom `PandasData` feed. A
signal observed on a completed bar submits an order to Backtrader's broker,
which normally fills a market order on the next bar.

```python
from backtesting import BacktraderConfig, SimulatedOrderType, run_backtrader

result = run_backtrader(
    signals,
    config=BacktraderConfig(
        initial_cash=10_000.0,
        commission=0.0002,
        slippage_perc=0.0001,
        size=10.0,
        entry_order_type=SimulatedOrderType.MARKET,
        allow_short=True,
        use_stops=True,
        leverage=30.0,
        annualization_factor=252 * 24,
    ),
)

print(result.metrics)
print(result.orders)
print(result.trades)
```

When `PreparedSignals.stop_loss` or `take_profit` is populated, the adapter
creates protective Stop and Limit orders from the confirmed entry price. The
orders are linked OCO when both exist, so completing one cancels the other. A
normal strategy exit cancels active protective orders before submitting the
position close.

### `BacktraderConfig`

| Field | Type | Description |
| --- | --- | --- |
| `initial_cash` | `float` | Starting Backtrader broker cash |
| `commission` | `float` | Proportional commission per side, such as `0.001` for 0.1% |
| `slippage_perc` | `float` | Proportional price slippage applied by Backtrader |
| `size` | `float` | Fixed units submitted for each entry |
| `entry_order_type` | `SimulatedOrderType` | Market, limit, or stop entry; bracket maps to market plus protective orders |
| `limit_offset` | `float` | Fractional limit distance from signal close |
| `stop_offset` | `float` | Fractional stop-entry distance from signal close |
| `allow_short` | `bool` | Whether short-entry signals may open positions |
| `use_stops` | `bool` | Whether prepared stop and target distances create protective orders |
| `margin` | `float \| None` | Backtrader fixed margin per contract when configured |
| `leverage` | `float` | Leverage passed to Backtrader commission information |
| `multiplier` | `float` | P&L multiplier for futures/CFD-style contracts |
| `interest` | `float` | Annual short financing rate used by Backtrader |
| `stocklike` | `bool` | Whether Backtrader treats the instrument like a stock |
| `annualization_factor` | `float` | Periods per year used for normalized Sharpe |

### `BacktraderResult`

| Field | Type | Description |
| --- | --- | --- |
| `cerebro` | `Any` | Native Backtrader engine after execution |
| `strategy` | `Any` | Executed native Backtrader strategy instance |
| `analyzers` | `dict[str, Any]` | Drawdown, returns, and trade analyzer output |
| `metrics` | `dict[str, float \| int \| None]` | Normalized return, Sharpe, drawdown, trade, rejection, and equity metrics |
| `orders` | `pandas.DataFrame` | Submitted, accepted, completed, canceled, margin, rejected, and expired callbacks |
| `trades` | `pandas.DataFrame` | Closed trades with direction, prices, size, P&L, commission, and duration |
| `equity` | `pandas.Series` | Backtrader broker value recorded by bar |
| `returns` | `pandas.Series` | Period equity returns |
| `drawdown` | `pandas.Series` | Peak-to-trough equity decline |

Backtrader's commission, margin, multiplier, leverage, and interest settings
must match the asset and broker. They are not inferred from aiomql or
`BrokerProfile`.

## Event-Driven Validation

```python
from backtesting import (
    BrokerProfile,
    EventBacktestConfig,
    EventDrivenBacktester,
    ExecutionModel,
)

broker = BrokerProfile(
    symbol="EURUSD",
    contract_size=100_000.0,
    leverage=30.0,
    point=0.00001,
    pip_size=0.0001,
    tick_value=1.0,
    min_volume=0.01,
    max_volume=100.0,
    volume_step=0.01,
    spread_points=12.0,
    commission_per_lot_per_side=3.50,
    swap_long_per_lot_per_day=-1.20,
    swap_short_per_lot_per_day=0.35,
)
engine = EventDrivenBacktester(
    broker=broker,
    execution=ExecutionModel(
        latency_bars=1,
        order_expiry_bars=3,
        slippage_points=2.0,
        max_volume_participation=0.10,
        allow_partial_fills=True,
    ),
    config=EventBacktestConfig(
        initial_cash=10_000.0,
        order_volume=0.10,
    ),
)
result = engine.run(signals, lower_timeframe=m1_ohlcv)
```

### `BrokerProfile`

| Field | Type | Description |
| --- | --- | --- |
| `symbol` | `str` | Instrument identifier |
| `contract_size` | `float` | Underlying units represented by one volume unit |
| `leverage` | `float` | Account leverage used for margin estimation |
| `point` | `float` | Smallest quoted price increment |
| `pip_size` | `float` | Conventional pip size |
| `tick_value` | `float` | Account-currency value of one point for one volume unit |
| `min_volume` | `float` | Minimum order volume |
| `max_volume` | `float` | Maximum order volume |
| `volume_step` | `float` | Permitted volume increment |
| `spread_points` | `float` | Default full bid/ask spread in points |
| `commission_per_lot_per_side` | `float` | Commission per volume unit for each side |
| `swap_long_per_lot_per_day` | `float` | Daily long financing amount |
| `swap_short_per_lot_per_day` | `float` | Daily short financing amount |
| `margin_call_level` | `float` | Equity-to-margin level that blocks additional exposure |
| `stop_out_level` | `float` | Equity-to-margin level that forces liquidation |

### `ExecutionModel`

| Field | Type | Description |
| --- | --- | --- |
| `latency_bars` | `int` | Bars between signal submission and order eligibility |
| `order_expiry_bars` | `int` | Eligible bars before an unfilled order expires |
| `slippage_points` | `float` | Default adverse slippage in points |
| `max_volume_participation` | `float` | Maximum fraction of bar volume available to the order |
| `allow_partial_fills` | `bool` | Whether available liquidity may fill only part of an order |
| `rejection_probability` | `float` | Seeded synthetic rejection probability |
| `spread_column` | `str` | Data column overriding default spread per bar |
| `slippage_column` | `str` | Data column overriding default slippage per bar |
| `liquidity_column` | `str` | Data column used as available bar volume |
| `reject_column` | `str` | Boolean data column forcing broker rejection |
| `collision_policy` | `IntrabarCollisionPolicy` | Stop/target ordering assumption for ambiguous bars |
| `seed` | `int` | Random seed for reproducible rejection simulation |

### `EventBacktestConfig`

| Field | Type | Description |
| --- | --- | --- |
| `initial_cash` | `float` | Starting account balance |
| `order_volume` | `float` | Requested volume for each signal |
| `entry_order_type` | `SimulatedOrderType` | `market`, `limit`, `stop`, or `bracket` |
| `limit_offset_points` | `float` | Limit distance from signal close |
| `stop_offset_points` | `float` | Stop-entry distance from signal close |
| `force_close_at_end` | `bool` | Close an open position on the final bar |

### Event Result Fields

| Field | Type | Description |
| --- | --- | --- |
| `orders` | `pandas.DataFrame` | Submitted, filled, partially filled, rejected, and expired order states |
| `fills` | `pandas.DataFrame` | Entry and exit fills with costs, margin, status, and reason |
| `trades` | `pandas.DataFrame` | Closed positions with gross/net P&L, commission, swap, and exit reason |
| `equity` | `pandas.Series` | Mark-to-market account equity |
| `returns` | `pandas.Series` | Period equity returns |
| `drawdown` | `pandas.Series` | Peak-to-trough equity decline |
| `metrics` | `dict[str, float \| int \| None]` | Return, Sharpe, drawdown, trade, win-rate, profit-factor, rejection, and equity metrics |

### Intrabar Replay

Pass lower-timeframe OHLC data using `lower_timeframe`. For each parent bar,
the engine replays child bars chronologically from the parent timestamp up to
the next parent timestamp. This determines whether a stop or target was reached
first.

When lower-timeframe data is absent, one OHLC bar cannot reveal price ordering.
The configured collision policy is then applied:

| Policy | Behavior |
| --- | --- |
| `STOP_FIRST` | Assume the stop was reached first |
| `TARGET_FIRST` | Assume the target was reached first |
| `CONSERVATIVE` | Use stop-first behavior to avoid optimistic bias |

## Expected Backtest Results

A strategy-specific result dataclass should normally expose:

| Field | Type | Description |
| --- | --- | --- |
| `portfolio` or native engine | `Any` | vectorbt portfolio, Backtrader strategy/Cerebro, or custom simulator state |
| `signals` | `PreparedSignals` | Exact normalized inputs used by the simulation |
| `stats` | `pandas.Series` | Native vectorbt statistics |
| `metrics` | `dict[str, float \| int \| None]` | Stable project metrics for reports and comparisons |
| `trades` | `pandas.DataFrame` | Normalized trade records |
| `equity` | `pandas.Series` | Portfolio value over time |
| `returns` | `pandas.Series` | Period returns |
| `drawdown` | `pandas.Series` | Peak-to-trough equity decline over time |

Recommended metrics include total return, annualized return, Sharpe ratio,
Sortino ratio, maximum drawdown, win rate, profit factor, and trade count.

## Adding A New Strategy

1. Keep indicator and signal rules in the strategy's `core.py`.
2. Add `strategies/<Strategy>/backtesting/signals.py`.
3. Return the shared `PreparedSignals` type from the preparation function.
4. Add a strategy-specific engine that consumes those prepared signals.
5. Model fees, spread, slippage, sizing, and bar frequency explicitly.
6. Preserve the prepared signals in the result for reporting and auditability.
7. Test index alignment, signal dtype, no-look-ahead behavior, and engine output.
8. Run out-of-sample or walk-forward validation before deployment decisions.

Suggested structure:

```text
strategies/
  ExampleStrategy/
    core.py
    backtesting/
      __init__.py
      signals.py
      backtrader_engine.py
      vectorbt_engine.py
      event_engine.py
    tests/
      test_signals.py
      test_backtrader_engine.py
      test_vectorbt_engine.py
```

## Validation Funnel

```text
vectorbt research and parameter screening
              |
              v
event-driven historical simulation
              |
              v
MT5 Strategy Tester comparison
              |
              v
aiomql dry-run signal validation
              |
              v
demo-account paper trading
              |
              v
limited live deployment
```

Promotion should require agreement on signal timestamps, trade direction,
costs, position sizing, and drawdown within documented tolerances. A stage
failure sends the strategy back to research rather than being ignored.

## Remaining Limitations

- Indicator and signal generation intentionally remain strategy concerns.
- Column-name leakage warnings cannot detect every semantic look-ahead error.
- Bar volume is only a liquidity proxy; true order-book queue position is not
  available from OHLCV.
- Margin formulas are generic and must be calibrated against broker rules.
- Corporate actions, borrow availability, exchange outages, variable leverage,
  and broker-specific stop levels require additional provider models.
- No historical simulator can guarantee live fills. Demo trading and broker
  reconciliation remain mandatory before limited deployment.
