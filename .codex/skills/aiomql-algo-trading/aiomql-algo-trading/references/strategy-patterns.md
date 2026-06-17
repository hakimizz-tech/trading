# aiomql Strategy Patterns

## Strategy design checklist

A good aiomql strategy should define:

- Symbol wrapper, usually `ForexSymbol` for FX.
- A `parameters` dictionary with tunable values.
- Session restrictions when trading should be time-bound.
- A signal method such as `find_entry()`.
- A `trade()` method that decides whether to sleep, log a dry-run signal, or place a trade.
- Risk controls before any live order.
- A tracker or cooldown to avoid duplicate entries.

## EMA crossover skeleton

```python
import logging

from aiomql import ForexSymbol, OrderType, ScalpTrader, Sessions, Strategy, TimeFrame, Tracker, Trader

logger = logging.getLogger(__name__)


class EMAXOver(Strategy):
    parameters = {
        "ttf": TimeFrame.H1,
        "tcc": 3000,
        "fast_ema": 34,
        "slow_ema": 55,
        "interval": TimeFrame.M15,
        "timeout": 3 * 60 * 60,
        "live_trading": False,
    }

    def __init__(self, *, symbol: ForexSymbol, params: dict | None = None, trader: Trader | None = None, sessions: Sessions | None = None, name: str = "EMAXOver"):
        super().__init__(symbol=symbol, params=params, sessions=sessions, name=name)
        self.tracker = Tracker(snooze=self.interval.seconds)
        self.trader = trader or ScalpTrader(symbol=self.symbol)

    async def find_entry(self) -> None:
        candles = await self.symbol.copy_rates_from_pos(timeframe=self.ttf, count=self.tcc)
        candles.ta.ema(length=self.fast_ema, append=True)
        candles.ta.ema(length=self.slow_ema, append=True)
        candles.rename(
            **{
                f"EMA_{self.fast_ema}": "fast_ema",
                f"EMA_{self.slow_ema}": "slow_ema",
            },
            inplace=True,
        )

        fast_above_slow = candles.ta_lib.above(candles.fast_ema, candles.slow_ema)
        fast_below_slow = candles.ta_lib.below(candles.fast_ema, candles.slow_ema)

        if fast_above_slow.iloc[-1]:
            self.tracker.update(order_type=OrderType.BUY, snooze=self.timeout)
        elif fast_below_slow.iloc[-1]:
            self.tracker.update(order_type=OrderType.SELL, snooze=self.timeout)
        else:
            self.tracker.update(order_type=None, snooze=self.interval.seconds)

    async def trade(self) -> None:
        await self.find_entry()

        if self.tracker.order_type is None:
            await self.sleep(secs=self.tracker.snooze)
            return

        if not self.live_trading:
            logger.info("Dry-run signal for %s: %s", self.symbol.name, self.tracker.order_type)
            await self.delay(secs=self.tracker.snooze)
            return

        await self.trader.place_trade(order_type=self.tracker.order_type, parameters=self.parameters)
        await self.delay(secs=self.tracker.snooze)
```

## Bot runner skeleton

```python
import logging

from aiomql import Bot, ForexSymbol, OpenPositionsTracker
from strategies.ema_crossover import EMAXOver

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    symbols = [ForexSymbol(name=name) for name in ["EURUSD", "GBPUSD", "USDJPY"]]
    strategies = [EMAXOver(symbol=symbol) for symbol in symbols]

    bot = Bot()
    bot.add_strategies(strategies)
    bot.add_coroutine(coroutine=OpenPositionsTracker(autocommit=True).track, on_separate_thread=True)
    bot.execute()


if __name__ == "__main__":
    main()
```

## Session skeleton

```python
from datetime import time
from aiomql import Session, Sessions

london = Session(name="London", start=time(8, 0), end=time(16, 0))
new_york = Session(name="New York", start=time(13, 0), end=time(21, 0))
sessions = Sessions(sessions=[london, new_york])
```

Pass `sessions=sessions` when constructing a strategy.

## Multi-process skeleton

```python
from aiomql import Bot


def run_forex() -> None:
    bot = Bot()
    # add forex strategies
    bot.execute()


def run_indices() -> None:
    bot = Bot()
    # add index strategies
    bot.execute()


Bot.process_pool(processes={run_forex: {}, run_indices: {}}, num_workers=2)
```

## Technical analysis guidance

- Fetch candles through the symbol wrapper.
- Append indicators to the candles DataFrame.
- Rename generated indicator columns to stable names.
- Avoid look-ahead bias. Use completed candles unless the user explicitly wants live forming-candle signals.
- Keep signal calculations separate from execution.

## Safe defaults for generated strategies

- `live_trading` false.
- One signal per cooldown window.
- No martingale.
- No averaging down unless explicitly requested and risk-limited.
- Require a stop-loss rule before live execution.
- Use demo account instructions first.
