# Shared Backtesting Contract

The `backtesting` package provides a broker-neutral signal contract, runtime
validation, shared vectorbt and Backtrader runners, and a deterministic custom
event simulator. Strategy logic prepares signals once and sends the same
validated data through fast research and realistic execution paths.

Use this module as the common bridge between strategy research and execution
validation. A strategy should calculate its own indicators, convert them into
`PreparedSignals`, validate that object, and then choose the right engine:
vectorbt for fast screening, Backtrader for event-driven order behavior, or the
custom event engine for broker-profile stress testing.

## Module Concepts

| Concept | Type | Description |
| --- | --- | --- |
| Strategy | Package/module | Owns the trading idea, indicators, entries, exits, and parameter defaults |
| `PreparedSignals` | Dataclass | Broker-neutral input contract consumed by every shared backtesting engine |
| Validation | Function/method | Runtime checks that catch bad indexes, signal conflicts, invalid prices, stop errors, and obvious leakage risk |
| Provenance | Metadata | Optional declaration of which columns are features, labels, and final signals, used to reduce semantic look-ahead mistakes |
| vectorbt engine | Function | Fast vectorized simulator for screening, optimization, and broad research |
| Backtrader engine | Function | Bar-by-bar simulator for order callbacks, protective orders, OCO behavior, and native Backtrader analyzers |
| Event engine | Class | Deterministic broker-neutral simulator for spread, slippage, latency, partial fills, rejections, margin, swaps, and provider constraints |
| Broker profile | Dataclass | Instrument contract, lot, spread, commission, swap, margin, and stop-distance assumptions |
| Provider data model | Dataclass | Optional column mapping for venue outages, borrow availability, corporate actions, variable leverage, and volume caps |
| Result object | Dataclass | Engine output containing metrics, trades, orders, fills, equity, returns, and drawdown |

## Terminology

| Term | Type | Description |
| --- | --- | --- |
| OHLCV | DataFrame columns | Open, high, low, close, and volume market bars |
| Entry signal | Boolean Series | A `True` value requesting a new long or short position |
| Exit signal | Boolean Series | A `True` value requesting closure of an existing position |
| Stop-loss distance | Float Series | Fractional distance from entry price, such as `0.02` for 2% |
| Take-profit distance | Float Series | Fractional profit target from entry price, such as `0.04` for 4% |
| Feature column | DataFrame column | Input used by strategy logic to create signals, such as RSI, volatility, or moving-average slope |
| Label column | DataFrame column | Future/target value used for research or ML training; it must not be used as a current-bar signal feature |
| Signal column | DataFrame column | Stored final signal or diagnostic column, such as `long_entry` or `regime` |
| Provenance | Tuple fields | Audit metadata stored on `PreparedSignals` to document feature, label, and signal origin |
| Look-ahead | Research defect | Any use of future information to make a current-bar decision |
| Minimum feature lag | Integer | Minimum number of bars between a feature value and the signal that consumes it |
| Collision policy | Enum | Assumption used when one bar touches both stop loss and take profit |
| Partial fill | Order state | Only part of requested volume was filled because simulated liquidity was limited |
| Provider constraint | Data column | Historical availability rule such as `borrow_available=False` or `exchange_outage=True` |
| Broker calibration | Process | Adjusting contract, margin, spread, commission, swap, and stop-level assumptions to match a real broker |

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
    BacktraderConfig,
    BrokerProfile,
    EventBacktestConfig,
    EventDrivenBacktester,
    ExecutionModel,
    PreparedSignals,
    ProviderDataModel,
    VectorBTConfig,
    VectorBTTargetOrdersConfig,
    run_backtrader,
    run_vectorbt,
    run_vectorbt_target_orders,
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
| `feature_columns` | `tuple[str, ...]` | Optional names of strategy feature columns used to create the signals |
| `label_columns` | `tuple[str, ...]` | Optional names of future/target columns used only for research labels |
| `signal_columns` | `tuple[str, ...]` | Optional names of final signal columns stored in `data` |
| `minimum_feature_lag` | `int \| None` | Minimum bars by which features are lagged before they can affect a signal |

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
| Missing provenance when `require_provenance=True` | Error |
| Label columns reused as feature or signal columns | Error |
| `minimum_feature_lag < 1` when provenance is required | Error |

Column-name checks can identify obvious leakage but cannot prove that strategy
logic is free from look-ahead. For ML and research-heavy strategies, populate
`feature_columns`, `label_columns`, `signal_columns`, and
`minimum_feature_lag`, then call `signals.validate(require_provenance=True)`.
Walk-forward tests and code review remain required.

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
        feature_columns=("fast_sma", "slow_sma"),
        signal_columns=("long_entry", "long_exit"),
        minimum_feature_lag=1,
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

### Provenance Validation

Provenance is most useful for ML strategies and research modules where the
dataset contains both current-bar features and future-bar labels. It does not
prove a strategy is correct, but it makes common mistakes harder to miss.

| Field | Type | Description |
| --- | --- | --- |
| `feature_columns` | `tuple[str, ...]` | Columns that strategy logic is allowed to use for signal generation |
| `label_columns` | `tuple[str, ...]` | Future/target columns used for training or evaluation only |
| `signal_columns` | `tuple[str, ...]` | Final strategy signal columns stored in `PreparedSignals.data` |
| `minimum_feature_lag` | `int` | Number of bars features are shifted before influencing a signal |
| `require_provenance` | `bool` | Validation flag that turns missing/unsafe provenance into errors |

```python
signals = PreparedSignals(
    data=frame,
    close=frame["close"],
    long_entries=frame["long_entry"].astype(bool),
    long_exits=frame["long_exit"].astype(bool),
    short_entries=frame["short_entry"].astype(bool),
    short_exits=frame["short_exit"].astype(bool),
    feature_columns=("rsi_14", "atr_14", "sma_slope"),
    label_columns=("next_5_bar_return",),
    signal_columns=("long_entry", "long_exit", "short_entry", "short_exit"),
    minimum_feature_lag=1,
)

signals.validate(require_provenance=True)
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

Use `run_vectorbt()` when a strategy has one close series plus long/short
entry and exit signals. This is the right fit for Bollinger Band, Scalper
Major signal research, and ML directional classifiers.

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

### Target-Order vectorbt Engine

Use `run_vectorbt_target_orders()` when a strategy produces portfolio target
weights rather than simple entry/exit booleans. This is the right fit for
monthly rotation, ETF basket, and allocation strategies.

```python
from backtesting import VectorBTTargetOrdersConfig, run_vectorbt_target_orders

result = run_vectorbt_target_orders(
    close=prices,
    target_orders=target_orders,
    config=VectorBTTargetOrdersConfig(
        init_cash=10_000.0,
        fees=0.0002,
        slippage=0.0001,
        freq="1d",
        direction="longonly",
    ),
)

print(result.metrics)
print(result.equity)
```

| Field | Type | Description |
| --- | --- | --- |
| `close` | `pandas.DataFrame` | Asset price matrix, one column per symbol |
| `target_orders` | `pandas.DataFrame` | Sparse target-percent order matrix aligned to `close` |
| `init_cash` | `float` | Starting capital |
| `fees` | `Any` | Proportional fees accepted by vectorbt, scalar or aligned array-like |
| `fixed_fees` | `Any` | Fixed fees accepted by vectorbt, scalar or aligned array-like |
| `slippage` | `Any` | Slippage accepted by vectorbt, scalar or aligned array-like |
| `freq` | `str \| None` | Bar frequency used by vectorbt metrics |
| `direction` | `str` | vectorbt direction mode, such as `longonly` or `both` |
| `cash_sharing` | `bool` | Whether all columns share one cash pool |
| `group_by` | `bool \| Any` | vectorbt grouping argument for portfolio aggregation |

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
    ProviderDataModel,
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
        provider_data=ProviderDataModel(),
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
| `min_stop_distance_points` | `float` | Broker minimum stop/target distance from entry in points |

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
| `provider_data` | `ProviderDataModel` | Optional column mapping for outages, borrow, leverage, stop levels, and corporate actions |
| `seed` | `int` | Random seed for reproducible rejection simulation |

### `ProviderDataModel`

`ProviderDataModel` describes optional market, exchange, and broker columns in
the OHLCV frame. If a column is absent, the engine uses the broker defaults.
This keeps provider-specific behavior out of strategy logic while still making
simulations less naive.

| Field | Type | Description |
| --- | --- | --- |
| `tradable_column` | `str` | Boolean column; `False` rejects new orders because the instrument is unavailable |
| `outage_column` | `str` | Boolean column; `True` rejects new orders because the venue is unavailable |
| `borrow_available_column` | `str` | Boolean column; `False` rejects short entries |
| `leverage_column` | `str` | Per-bar leverage override for margin calculations |
| `max_volume_column` | `str` | Per-bar maximum order volume cap before partial-fill logic |
| `min_stop_points_column` | `str` | Per-bar broker stop/target minimum distance in points |
| `split_factor_column` | `str` | Corporate action marker; values other than `1.0` can halt new orders |
| `dividend_column` | `str` | Corporate action marker; non-zero values can halt new orders |
| `halt_on_corporate_action` | `bool` | Whether split/dividend markers reject new orders until data is adjusted |

Example provider-aware columns:

```python
signals.data["exchange_outage"] = False
signals.data["borrow_available"] = True
signals.data["leverage"] = 30.0
signals.data["min_stop_points"] = 50.0
signals.data["max_order_volume"] = signals.data["volume"] * 0.10
```

The simulator uses these fields to reject orders, cap liquidity, apply variable
leverage, and enforce broker stop-distance rules. Corporate action fields do
not adjust prices by themselves; they halt new orders by default so the dataset
can be corrected upstream.

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

## Limitations And Mitigations

| Limitation | Mitigation in this package | Still required before live |
| --- | --- | --- |
| Indicator and signal generation are strategy concerns | Keep strategy `core.py` responsible for indicators and return `PreparedSignals` | Strategy-specific tests for indicators, signal timing, and no look-ahead |
| Column-name leakage checks are imperfect | Optional provenance fields and `validate(require_provenance=True)` catch label/feature/signal misuse | Code review, walk-forward validation, and research notebooks that prove feature lagging |
| Bar volume is only a liquidity proxy | `ExecutionModel.max_volume_participation` and `ProviderDataModel.max_volume_column` cap fills and create partial fills | Order-book, tick, or broker execution data when available |
| Margin formulas are generic | `BrokerProfile` plus per-bar `leverage_column` calibrate margin pressure and stop-out behavior | Broker/demo comparison against MT5 or target venue margin reports |
| Corporate actions and venue outages are not visible in plain OHLCV | `ProviderDataModel` can halt orders on splits, dividends, tradability, or outage columns | Upstream adjusted datasets and provider-specific calendars |
| Borrow and broker stop-level rules vary by instrument | Borrow availability and minimum stop-distance columns can reject invalid trades | Broker symbol metadata and historical borrow/shortability data |
| Historical fills are estimates | vectorbt, Backtrader, and the custom event engine provide progressively stricter simulations | MT5 Strategy Tester, aiomql dry run, demo trading, journal/ledger reconciliation, then limited live deployment |
