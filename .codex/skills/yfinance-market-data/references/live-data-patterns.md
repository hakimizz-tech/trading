# Live Data Patterns

## Synchronous WebSocket

```python
import yfinance as yf

ws = yf.WebSocket()
ws.subscribe(["AAPL", "MSFT"])
ws.listen()
```

Use for simple scripts where blocking behavior is acceptable.

## Async WebSocket

```python
import asyncio
import yfinance as yf

async def main():
    ws = yf.AsyncWebSocket()
    await ws.subscribe(["AAPL", "MSFT"])
    await ws.listen()

asyncio.run(main())
```

Use for applications that need to run other async tasks at the same time.

## Production guidance

Add reconnect logic, graceful shutdown on Ctrl+C, message parsing, a timeout or stop condition, logging, and data persistence if stream messages are important.

## Timeout wrapper example

```python
import asyncio
import yfinance as yf

async def stream_for_seconds(symbols, seconds=30):
    ws = yf.AsyncWebSocket()
    await ws.subscribe(symbols)
    try:
        await asyncio.wait_for(ws.listen(), timeout=seconds)
    except asyncio.TimeoutError:
        print("Stream timeout reached")

asyncio.run(stream_for_seconds(["AAPL"], 30))
```

## Important limitations

- yfinance WebSocket is a data stream, not an order execution API.
- Stream availability can vary by symbol and Yahoo service status.
- Do not use stream examples as trading infrastructure without separate reliability controls.
