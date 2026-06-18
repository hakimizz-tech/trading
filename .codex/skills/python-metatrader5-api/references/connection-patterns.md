# Connection Patterns

## Minimal connection

```python
import MetaTrader5 as mt5

if not mt5.initialize():
    print("initialize failed:", mt5.last_error())
    raise SystemExit(1)

try:
    print("terminal:", mt5.terminal_info())
    print("version:", mt5.version())
    print("account:", mt5.account_info())
finally:
    mt5.shutdown()
```

## Connection with terminal path

Use this when auto-discovery fails or multiple terminals are installed.

```python
mt5.initialize(path=r"C:\\Program Files\\MetaTrader 5\\terminal64.exe")
```

## Connection with account credentials

Prefer environment variables rather than hardcoding values.

```python
import os
import MetaTrader5 as mt5

login = int(os.environ["MT5_LOGIN"])
password = os.environ["MT5_PASSWORD"]
server = os.environ["MT5_SERVER"]

if not mt5.initialize(login=login, password=password, server=server):
    print("initialize failed:", mt5.last_error())
    raise SystemExit(1)
```

## Diagnostic checklist

When `initialize()` fails:

- Confirm the MetaTrader 5 desktop terminal is installed.
- Confirm the terminal is open or can be launched by Python.
- Try supplying the exact terminal path.
- Confirm bitness and package compatibility.
- Confirm account is logged in inside the terminal or provide `login`, `password`, and `server`.
- Print `mt5.last_error()` immediately after failure.

## Context manager pattern

```python
from contextlib import contextmanager
import MetaTrader5 as mt5

@contextmanager
def mt5_connection(**kwargs):
    if not mt5.initialize(**kwargs):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        yield
    finally:
        mt5.shutdown()

with mt5_connection():
    print(mt5.version())
```
