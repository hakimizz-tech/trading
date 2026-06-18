# Troubleshooting MetaTrader5 Python Integration

## `ModuleNotFoundError: No module named MetaTrader5`

Fix:

```bash
pip install MetaTrader5
```

Confirm the same interpreter is used:

```bash
python -m pip show MetaTrader5
python -c "import MetaTrader5 as mt5; print(mt5.__version__)"
```

## `initialize()` returns `False`

Run:

```python
print(mt5.last_error())
```

Likely causes:

- MetaTrader 5 terminal is not installed.
- Python cannot find the terminal executable.
- Terminal path is wrong.
- Account credentials or broker server are wrong.
- Terminal is blocked by OS permissions.

## Symbol not found

Broker symbols may have suffixes. Search matching symbols:

```python
matches = mt5.symbols_get("*XAU*")
for symbol in matches:
    print(symbol.name)
```

## No rates or ticks returned

Check:

- Correct symbol name.
- Symbol selected into MarketWatch.
- UTC date range.
- Terminal history availability.
- `Max. bars in chart` terminal setting.

## `order_send` fails

Inspect the result:

```python
result = mt5.order_send(request)
print(result)
if result is not None:
    print(result._asdict())
else:
    print(mt5.last_error())
```

Common reasons:

- Invalid volume.
- Invalid stops.
- Market closed.
- AutoTrading disabled.
- Unsupported filling mode.
- Symbol trade mode does not allow the requested operation.
- Account has insufficient margin.

## Linux and WSL note

The official Python package communicates with the MetaTrader 5 desktop terminal. On Linux or WSL, users often need a Windows terminal, Wine setup, broker VPS, or another bridge. Do not assume a local Linux-only environment will work without a terminal bridge.
