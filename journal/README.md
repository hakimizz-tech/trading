# Trade Journal

The `journal` package records strategy signals, order attempts, broker-confirmed fills, exits, and post-trade review notes. Application code should use `TradeJournal`; database code should live behind a `JournalBackend`.

`TradeRecord` is the data object for one planned, open, or closed trade. `TradeJournal` is the service that validates records, generates UUID trade ids, writes events, and reads records back.

## Imports

```python
from journal import JournalEvent, TradeJournal, TradeRecord
```

Do not import SQLite classes from strategy or execution code. Only wire a backend directly when configuring storage or writing backend tests.

## TradeRecord Fields

| Field | Type | Description |
| --- | --- | --- |
| `token` | `str` | Symbol, asset, or market identifier such as `EURUSD`, `SPY`, or `SOL`. |
| `direction` | `str` | Trade side. Must be `long` or `short`. |
| `entry_date` | `str` | Entry timestamp in ISO format, preferably UTC with `Z`. |
| `entry_price` | `float` | Planned or filled entry price. Must be positive. |
| `size_sol` | `float` | Position size. The legacy field name is neutralized by context; forex bots may store lots here. |
| `strategy` | `str` | Strategy name used for attribution and reporting. |
| `rationale` | `str` | Entry reason recorded before execution. |
| `id` | `str \| None` | Optional UUID trade id. If omitted, `TradeJournal` generates one. |
| `size_usd` | `float \| None` | Optional notional value. |
| `setup_quality` | `int \| None` | Optional discretionary score from 1 to 10. |
| `exit_date` | `str \| None` | Exit timestamp after close. |
| `exit_price` | `float \| None` | Realized exit price. |
| `pnl_sol` | `float \| None` | Realized P&L in the strategy/accounting unit. |
| `pnl_pct` | `float \| None` | Realized percentage return. |
| `outcome` | `str \| None` | `win`, `loss`, or `breakeven`. |
| `hold_time_minutes` | `int \| None` | Computed holding time after exit update. |
| `emotional_state` | `str \| None` | Optional human review field. |
| `lessons` | `str \| None` | Optional post-trade notes. |
| `tags` | `list[str]` | Strategy, behavior, setup, or review tags. |
| `stop_price` | `float \| None` | Planned stop price. |
| `target_price` | `float \| None` | Planned target price. |
| `risk_reward` | `float \| None` | Planned reward-to-risk ratio. |
| `fees_sol` | `float \| None` | Fees or commission in the strategy/accounting unit. |
| `slippage_bps` | `float \| None` | Estimated or realized slippage in basis points. |
| `expected_profit` | `float \| None` | Expected profit before or during order submission. |
| `actual_profit` | `float \| None` | Realized profit after broker-confirmed close. |
| `status` | `str` | Lifecycle status. Defaults to `signal`. |
| `mode` | `str` | Execution mode such as `dry_run`, `paper`, or `live`. |
| `source` | `str` | Signal/execution source such as `strategy` or `aiomql:BollingerBands`. |
| `metadata` | `dict[str, Any]` | Extra structured context: timeframe, broker ids, risk settings, raw broker payloads. |

## JournalEvent Fields

| Field | Type | Description |
| --- | --- | --- |
| `event_type` | `str` | Event name such as `signal`, `order_submitted`, `broker_history_deal`, or `exit`. |
| `event_time` | `str` | Event timestamp in ISO format. |
| `token` | `str` | Symbol or market identifier. |
| `strategy` | `str` | Strategy associated with the event. |
| `trade_id` | `str \| None` | UUID of the parent trade when available. |
| `direction` | `str \| None` | `long`, `short`, or broker-normalized side. |
| `price` | `float \| None` | Event price. |
| `size_sol` | `float \| None` | Event size. Forex bots may store lots here. |
| `status` | `str \| None` | Optional lifecycle status to apply to the parent trade. |
| `message` | `str \| None` | Human-readable event message. |
| `metadata` | `dict[str, Any]` | Broker ids, raw payloads, rejection reasons, or strategy context. |

## Lifecycle Statuses

| Field | Type | Description |
| --- | --- | --- |
| `signal` | `str` | Strategy produced a trade idea. |
| `blocked` | `str` | Risk, spread, session, or execution gate blocked the trade. |
| `submitted` | `str` | Order was submitted to the broker or execution venue. |
| `filled` | `str` | Broker confirmed a full fill. |
| `partially_filled` | `str` | Broker confirmed a partial fill. |
| `closed` | `str` | Broker or backtest confirmed the position was closed. |
| `rejected` | `str` | Broker or execution adapter rejected the order. |
| `error` | `str` | Unexpected execution or journal failure occurred. |

## TradeJournal Methods

| Field | Type | Description |
| --- | --- | --- |
| `record_trade(trade)` | `str` | Writes a `TradeRecord` and returns its UUID trade id. |
| `record_signal_trade(...)` | `str` | Convenience method for recording a signal plus its first `signal` event. |
| `record_event(event)` | `int` | Appends a `JournalEvent`; if the event has a status, the parent trade status is updated. |
| `record_broker_history_event(...)` | `int` | Normalizes aiomql/MT5 history deals or orders into journal events. |
| `update_exit(...)` | `None` | Writes realized exit information and creates an `exit` event. |
| `get_trade(trade_id)` | `dict[str, Any] \| None` | Reads one trade by UUID. |
| `list_trades(...)` | `list[dict[str, Any]]` | Lists trades, optionally filtered by status or strategy. |
| `list_events(trade_id)` | `list[dict[str, Any]]` | Lists all events or only events for one trade UUID. |
| `summary_by_strategy()` | `list[dict[str, Any]]` | Returns backend-provided strategy summary rows. |
| `next_trade_id()` | `str` | Generates a UUID4 trade id. |

## Record A Strategy Signal

```python
from journal import TradeJournal

journal = TradeJournal("db/trade_journal.sqlite")

trade_id = journal.record_signal_trade(
    token="EURUSD",
    direction="long",
    entry_date="2026-06-17T10:00:00Z",
    entry_price=1.0850,
    size_sol=0.01,
    strategy="bollinger-adaptive",
    rationale="Long signal with spread and risk gates satisfied.",
    status="submitted",
    mode="live",
    source="aiomql:BollingerBands",
    stop_price=1.0800,
    target_price=1.0950,
    expected_profit=25.5,
    metadata={"timeframe": "M15", "risk_per_trade": 0.01},
)
```

## Record A Trade Manually

```python
from journal import TradeJournal, TradeRecord

journal = TradeJournal()

trade_id = journal.record_trade(
    TradeRecord(
        token="SPY",
        direction="long",
        entry_date="2026-06-17T14:30:00Z",
        entry_price=540.25,
        size_sol=10,
        strategy="rising-assets",
        rationale="ETF ranked in the top momentum bucket.",
        status="filled",
        mode="paper",
        source="backtest",
        tags=["momentum", "weekly-rotation"],
    )
)
```

## Update A Closed Trade

```python
journal.update_exit(
    trade_id,
    exit_date="2026-06-21T20:00:00Z",
    exit_price=548.10,
    pnl_sol=78.50,
    pnl_pct=1.45,
    outcome="win",
    actual_profit=78.50,
    lessons="Exit followed the weekly rotation rule.",
)
```

## Record aiomql History

```python
journal.record_broker_history_event(
    {
        "deal": 987654,
        "order": 123456,
        "position_id": 444,
        "symbol": "EURUSD",
        "type": "BUY",
        "entry": "OUT",
        "volume": 0.01,
        "price": 1.0875,
        "profit": 12.5,
        "commission": -0.07,
        "swap": 0.0,
        "time": "2026-06-17T10:15:00Z",
        "magic": 20260617,
        "comment": "bollinger-adaptive",
    },
    item_type="deal",
    strategy="bollinger-adaptive",
    trade_id=trade_id,
)
```

## Backend Contract

`TradeJournal` owns validation, UUID generation, lifecycle behavior, JSON conversion, and broker-history normalization. `JournalBackend` owns persistence only.

| Field | Type | Description |
| --- | --- | --- |
| `upsert_trade(payload)` | `Callable` | Insert or replace one normalized trade payload. |
| `insert_event(payload)` | `Callable[..., int]` | Insert one normalized event payload and return a backend row id. |
| `update_trade_status(...)` | `Callable` | Update the status and timestamp for one trade UUID. |
| `update_trade_exit(...)` | `Callable` | Update realized exit fields for one trade UUID. |
| `get_trade(trade_id)` | `Callable[..., dict \| None]` | Return one stored trade row. |
| `list_trades(...)` | `Callable[..., list[dict]]` | Return stored trade rows, optionally filtered. |
| `list_events(trade_id)` | `Callable[..., list[dict]]` | Return stored event rows. |
| `summary_by_strategy()` | `Callable[..., list[dict]]` | Return strategy-level summary rows. |

To add PostgreSQL, MySQL, or another production database, create a backend under `journal/backends/` that implements this protocol, then inject it:

```python
from journal import TradeJournal

journal = TradeJournal(backend=PostgresJournalBackend("postgresql://..."))
```

The backend receives already-normalized dictionaries. It should not reimplement journal validation, lifecycle rules, or trade-id generation.

## Trade IDs

Trade ids are UUID4 strings generated by `TradeJournal`.

```text
4d3f30a0-7406-47c9-9f3e-58df2f4f61cf
```

Use:

- `id` for stable journal identity.
- `entry_date` for time ordering and date filtering.
- broker ids in `metadata` for MT5 tickets, deals, orders, and position ids.

SQLite event row ids are internal storage ids only. Application logic should use the trade UUID and broker metadata.

## Developer Rules

- Use `TradeJournal` from strategies, bots, scripts, and aiomql execution code.
- Use `TradeRecord` when constructing a full trade object manually.
- Use `record_signal_trade` when a strategy produces a fresh signal.
- Add database engines under `journal/backends/`.
- Keep SQL and database driver details out of strategies and execution adapters.
- Post accounting ledger entries only from broker-confirmed fills or closes, not from raw signals.
