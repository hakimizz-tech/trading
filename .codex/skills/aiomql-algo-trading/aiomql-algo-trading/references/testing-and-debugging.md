# Testing and Debugging aiomql Projects

## Skill trigger tests

Requests that should trigger this skill:

- Build me an aiomql bot for EURUSD.
- Create an async MetaTrader 5 script with aiomql.
- Add Sessions to my aiomql Strategy.
- Use RAM risk management in aiomql.
- Debug my aiomql MetaTrader login.
- Create a ForexSymbol EMA crossover strategy.
- Wire multiple strategies into Bot.

Requests that should not trigger this skill:

- Explain forex trading generally.
- Recommend whether I should buy EURUSD now.
- Build a non-aiomql stock screener.
- Write MQL5 Expert Advisor code without Python.

## Environment checks

Run:

```bash
python scripts/check_aiomql_env.py --project .
```

The script should report:

- Python version.
- OS platform.
- Whether aiomql imports.
- Project files found.
- Whether `aiomql.json` exists, with secrets redacted.
- `.gitignore` safety hints.

## Static checks

Use available tooling from the project. Common commands:

```bash
python -m compileall .
python -m pytest
python -m pip show aiomql
```

## Debugging map

### ImportError for aiomql

Likely causes:

- Wrong virtual environment.
- Python too old.
- Package not installed.

Fix:

```bash
python -m pip install aiomql
```

### LoginError or connection failure

Likely causes:

- Not on Windows.
- MetaTrader 5 terminal not installed or not running.
- Wrong broker server name.
- Wrong login or password.
- Broker account not enabled.

Fix:

- Test terminal login manually first.
- Verify `aiomql.json` locally.
- Redact credentials before sharing logs.

### Symbol not found

Likely causes:

- Broker uses suffixes such as `EURUSDm`.
- Symbol not visible in Market Watch.
- Wrong asset class.

Fix:

- Fetch available symbols.
- Ask user for exact broker symbol names.

### Orders rejected

Likely causes:

- Invalid volume step.
- Stop-loss too close.
- Market closed.
- Insufficient margin.
- Unsupported filling mode.
- Spread too high.

Fix:

- Validate symbol info.
- Check order before send where possible.
- Log full non-secret trade result.

### Async loop conflict

Likely causes:

- Calling `asyncio.run()` inside an existing event loop.
- Using `bot.execute()` inside async application code.

Fix:

- Use `await bot.start()` in async context.
- Keep `bot.execute()` for normal script entry points.
