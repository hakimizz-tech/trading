# Trading Accounting

The `accounting` package is the project's broker-neutral double-entry ledger.
It stores confirmed economic activity such as realized profit and loss, fees,
funding, withdrawals, and investment income.

It is not part of the aiomql API. aiomql, another broker adapter, or an exchange
client may provide confirmed trade data, but application code converts that
data into calls on `TradeLedger`.

## Accounting Boundary

| Event | Destination | Reason |
| --- | --- | --- |
| Strategy signal | Trade journal | No economic activity has occurred |
| Risk or spread rejection | Trade journal | The order was blocked |
| Order submitted | Trade journal | Submission does not prove execution |
| Broker rejection or error | Trade journal | No confirmed fill occurred |
| Confirmed spot purchase or sale | Accounting ledger | Cash and asset balances changed |
| Confirmed forex/CFD position close | Accounting ledger | Realized P&L, commission, or swap changed |
| Open forex/CFD position | Broker state and journal | Unrealized P&L is not posted by this ledger |

The live execution layer follows this rule automatically: only a
broker-confirmed result containing realized P&L is posted to `TradeLedger`.

## Quick Start

```python
from accounting import TradeLedger

ledger = TradeLedger(
    "db/trade_accounting.sqlite",
    base_currency="USD",
)

ledger.record_position_close(
    symbol="EURUSD",
    realized_pnl=125.40,
    commission=-7.00,
    swap=-1.25,
    strategy="BollingerBands",
    external_id="broker-deal-84721",
    direction="long",
    volume=1.0,
    entry_price=1.0820,
    exit_price=1.0834,
)

print(ledger.profit_and_loss())
print(ledger.trial_balance())
```

## Database Configuration

`TradeLedger` uses SQLAlchemy. A filesystem path creates a SQLite database,
while a SQLAlchemy URL can select another database backend.

```python
from accounting import TradeLedger

# Default SQLite backend
sqlite_ledger = TradeLedger("db/trade_accounting.sqlite")

# PostgreSQL example; obtain credentials from environment or secret storage.
postgres_ledger = TradeLedger(
    "postgresql+psycopg://user:password@localhost/trading"
)

# MySQL example
mysql_ledger = TradeLedger(
    "mysql+pymysql://user:password@localhost/trading"
)
```

Install the appropriate SQLAlchemy database driver when using PostgreSQL or
MySQL. Do not commit database credentials. Schema changes in a production
database should be managed with migrations rather than runtime table edits.

### `TradeLedger` Constructor

| Field | Type | Description |
| --- | --- | --- |
| `path` | `str \| Path` | SQLite path or complete SQLAlchemy database URL |
| `base_currency` | `str` | Reporting currency label, defaulting to `BASE` |
| `echo` | `bool` | Enables SQLAlchemy SQL logging for diagnostics |

Construction creates the required tables and ensures the default chart of
accounts exists.

## Public Data Types

Import public types from `accounting`, not from ORM implementation details.

```python
from accounting import (
    Account,
    AccountingError,
    LedgerPosting,
    LedgerTransaction,
    TradeLedger,
)
```

### `Account`

| Field | Type | Description |
| --- | --- | --- |
| `code` | `str` | Unique chart-of-accounts identifier |
| `name` | `str` | Human-readable account name |
| `category` | `str` | One of `asset`, `liability`, `income`, `expense`, or `equity` |
| `normal_balance` | `str` | Side that increases the account: `debit` or `credit` |

### `LedgerPosting`

A posting is one debit or credit line within a transaction.

| Field | Type | Description |
| --- | --- | --- |
| `account_code` | `str` | Existing account receiving the posting |
| `debit` | `float` | Non-negative debit amount; defaults to `0.0` |
| `credit` | `float` | Non-negative credit amount; defaults to `0.0` |
| `memo` | `str` | Optional explanation for this posting |

A posting cannot contain both a debit and a credit.

### `LedgerTransaction`

| Field | Type | Description |
| --- | --- | --- |
| `occurred_at` | `str` | UTC ISO-8601 timestamp for the economic event |
| `description` | `str` | Human-readable transaction description |
| `postings` | `list[LedgerPosting]` | At least two balanced posting lines |
| `external_id` | `str \| None` | Broker deal, exchange fill, or transfer identifier |
| `strategy` | `str \| None` | Strategy responsible for the transaction |
| `symbol` | `str \| None` | Traded instrument or asset |
| `metadata` | `dict[str, Any]` | Provider-neutral audit details |

`record_transaction()` rejects unknown accounts, negative posting values,
single-line transactions, and transactions whose total debits and credits do
not match.

## Recording Forex And CFDs

Use `record_position_close()` for a confirmed leveraged position close. Margin
exposure and open-position market value are broker state, not asset holdings in
this ledger.

| Field | Type | Description |
| --- | --- | --- |
| `symbol` | `str` | Broker symbol, such as `EURUSD` |
| `realized_pnl` | `float` | Gross realized P&L in account currency |
| `commission` | `float` | Broker commission; either sign is accepted and treated as a cost |
| `swap` | `float` | Financing income when positive or financing cost when negative |
| `occurred_at` | `str \| None` | Broker event time; current UTC time is used when omitted |
| `strategy` | `str \| None` | Stable strategy identifier |
| `external_id` | `str \| None` | Unique broker deal identifier used for idempotency |
| `direction` | `str \| None` | Informational `long` or `short` metadata |
| `volume` | `float \| None` | Closed broker volume |
| `entry_price` | `float \| None` | Position entry price |
| `exit_price` | `float \| None` | Position close price |
| `memo` | `str \| None` | Optional transaction description |
| `idempotent` | `bool` | Reuses an existing transaction when `external_id` was already posted |

The method returns the ledger transaction ID, or `None` when P&L, commission,
and swap are all zero.

`record_broker_fill(**kwargs)` accepts the same fields and delegates to
`record_position_close()`. It is intended for provider adapters that have
already normalized and confirmed a closing fill.

```python
deal = {
    "symbol": "GBPUSD",
    "profit": -42.50,
    "commission": -3.50,
    "swap": 0.75,
    "ticket": "deal-10004",
}

ledger.record_broker_fill(
    symbol=deal["symbol"],
    realized_pnl=deal["profit"],
    commission=deal["commission"],
    swap=deal["swap"],
    external_id=deal["ticket"],
    strategy="ScalperMajorHighVolatility",
)
```

The dictionary above is illustrative provider data, not an aiomql type or a
required accounting schema.

## Recording Spot Assets

Use the spot helpers when ownership and cost basis move between cash and asset
holdings.

### `record_buy_fill()`

| Field | Type | Description |
| --- | --- | --- |
| `symbol` | `str` | Purchased asset |
| `cost_basis` | `float` | Acquisition value excluding separately recorded fee |
| `fee` | `float` | Trading fee |
| `occurred_at` | `str \| None` | Confirmed fill time |
| `strategy` | `str \| None` | Strategy identifier |
| `external_id` | `str \| None` | Exchange or broker fill identifier |
| `memo` | `str \| None` | Optional description |

### `record_sell_fill()`

| Field | Type | Description |
| --- | --- | --- |
| `symbol` | `str` | Sold asset |
| `proceeds` | `float` | Gross disposal proceeds |
| `cost_basis` | `float` | Cost basis removed for the quantity sold |
| `fee` | `float` | Trading fee |
| `occurred_at` | `str \| None` | Confirmed fill time |
| `strategy` | `str \| None` | Strategy identifier |
| `external_id` | `str \| None` | Exchange or broker fill identifier |
| `memo` | `str \| None` | Optional description |

```python
ledger.record_buy_fill(
    symbol="SPY",
    cost_basis=5_000.00,
    fee=1.00,
    strategy="RisingAssets",
    external_id="buy-fill-101",
)

ledger.record_sell_fill(
    symbol="SPY",
    proceeds=5_350.00,
    cost_basis=5_000.00,
    fee=1.00,
    strategy="RisingAssets",
    external_id="sell-fill-102",
)
```

The caller must supply the disposed cost basis. This package does not currently
select FIFO, LIFO, or specific tax lots.

## Other Economic Events

| Method | Required fields | Description |
| --- | --- | --- |
| `record_funding()` | `amount` | Debits cash and credits owner capital |
| `record_withdrawal()` | `amount` | Debits owner withdrawals and credits cash |
| `record_fee()` | `amount` | Records trading or gas/priority expense |
| `record_income()` | `amount`, `income_type` | Records staking, airdrop, LP-fee, or trading income |
| `add_account()` | `account` | Adds or updates a validated chart-of-accounts entry |
| `record_transaction()` | `transaction` | Records a custom balanced transaction |

Common optional fields include `occurred_at` and `external_id`.
`record_fee()` also accepts `fee_type`, `strategy`, and `symbol`.
`record_income()` accepts `income_type` values `staking`, `airdrop`, `lp_fee`,
or `trading`.

### Custom Transaction

```python
from accounting import LedgerPosting, LedgerTransaction, TradeLedger, utc_now

ledger = TradeLedger("db/trade_accounting.sqlite")
transaction_id = ledger.record_transaction(
    LedgerTransaction(
        occurred_at=utc_now(),
        description="Manual slippage adjustment",
        strategy="ExampleStrategy",
        symbol="EURUSD",
        postings=[
            LedgerPosting("4030", debit=2.50, memo="Execution slippage"),
            LedgerPosting("1010", credit=2.50, memo="Cash impact"),
        ],
        metadata={"source": "reconciliation"},
    )
)
```

## Queries And Reports

| Method | Returns | Description |
| --- | --- | --- |
| `transaction_by_external_id(external_id)` | `dict[str, Any] \| None` | Finds the first transaction with a provider identifier |
| `list_transactions()` | `list[dict[str, Any]]` | Returns transactions ordered by event time and ID |
| `list_postings(transaction_id=None)` | `list[dict[str, Any]]` | Returns all postings or postings for one transaction |
| `trial_balance()` | `dict[str, float]` | Returns total debits, credits, and their difference |
| `account_balances()` | `list[dict[str, Any]]` | Returns debit, credit, and normal-balance totals per account |
| `profit_and_loss()` | `dict[str, Any]` | Returns income, expenses, totals, and net income |
| `net_income_since(start, strategy=None, symbol=None)` | `float` | Returns filtered net income from an ISO timestamp |
| `balance_sheet()` | `dict[str, Any]` | Returns assets, liabilities, equity, totals, and balance check |

### Transaction Result Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | `int` | Internal ledger transaction ID |
| `occurred_at` | `str` | Economic event timestamp |
| `description` | `str` | Transaction description |
| `external_id` | `str \| None` | Provider identifier |
| `strategy` | `str \| None` | Strategy identifier |
| `symbol` | `str \| None` | Instrument |
| `metadata` | `dict[str, Any]` | Decoded transaction metadata |
| `created_at` | `str` | Ledger insertion timestamp |

### Posting Result Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | `int` | Internal posting ID |
| `transaction_id` | `int` | Parent ledger transaction ID |
| `account_code` | `str` | Posted account |
| `debit` | `float` | Debit amount |
| `credit` | `float` | Credit amount |
| `memo` | `str` | Posting explanation |

## Default Chart Of Accounts

| Code | Account | Category | Normal balance |
| --- | --- | --- | --- |
| `1010` | Cash - Base | Asset | Debit |
| `1020` | Cash - Quote | Asset | Debit |
| `1100` | Token Holdings | Asset | Debit |
| `1200` | LP Positions | Asset | Debit |
| `1300` | Staking Deposits | Asset | Debit |
| `2010` | Margin Borrowing | Liability | Credit |
| `2020` | Accrued Taxes Payable | Liability | Credit |
| `3010` | Realized Trading Gains | Income | Credit |
| `3020` | Staking Rewards | Income | Credit |
| `3030` | Airdrop Income | Income | Credit |
| `3040` | LP Fee Income | Income | Credit |
| `4010` | Trading Fees | Expense | Debit |
| `4020` | Gas & Priority Fees | Expense | Debit |
| `4030` | Slippage Cost | Expense | Debit |
| `5010` | Owner Capital | Equity | Credit |
| `5020` | Retained Earnings | Equity | Credit |
| `5030` | Owner Withdrawals | Equity | Debit |

## Reconciliation

Use broker or exchange history as the source of truth:

1. Fetch confirmed deals for a fixed UTC interval.
2. Normalize provider records into project fields.
3. Use the provider deal ID as `external_id`.
4. Post missing economic events.
5. Compare broker deals, journal events, and ledger transactions.
6. Confirm `trial_balance()["difference"] == 0.0`.

The project reconciliation entry point is:

```bash
python scripts/reconcile_trading_records.py --help
```

## Important Limitations

- This ledger records realized accounting activity; it is not a live broker
  position service.
- Open-position margin and unrealized P&L remain in `BrokerSnapshot`.
- Spot cost basis must be supplied by the caller.
- Production schema evolution still requires a migration tool such as Alembic.
- Financial and tax treatment depends on jurisdiction; this module is an
  operational ledger, not tax or legal advice.
