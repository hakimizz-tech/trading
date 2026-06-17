#!/usr/bin/env python3
"""Create a safe dry-run aiomql starter project."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

FILES: dict[str, str] = {
    "aiomql.json.example": '''{
  "login": 12345678,
  "password": "replace_me_locally",
  "server": "YourBroker-Demo"
}
''',
    ".gitignore": '''aiomql.json
.env
*.db
*.sqlite
logs/
trade_results/
__pycache__/
.pytest_cache/
''',
    "strategies/__init__.py": "",
    "strategies/ema_crossover.py": '''import logging

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

    def __init__(
        self,
        *,
        symbol: ForexSymbol,
        params: dict | None = None,
        trader: Trader | None = None,
        sessions: Sessions | None = None,
        name: str = "EMAXOver",
    ):
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
''',
    "bot.py": '''import logging
from datetime import time

from aiomql import Bot, ForexSymbol, OpenPositionsTracker, Session, Sessions
from strategies.ema_crossover import EMAXOver

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    london = Session(name="London", start=time(8, 0), end=time(16, 0))
    new_york = Session(name="New York", start=time(13, 0), end=time(21, 0))
    sessions = Sessions(sessions=[london, new_york])

    symbols = [ForexSymbol(name=name) for name in ["EURUSD", "GBPUSD", "USDJPY"]]
    strategies = [EMAXOver(symbol=symbol, sessions=sessions) for symbol in symbols]

    bot = Bot()
    bot.add_strategies(strategies)
    bot.add_coroutine(coroutine=OpenPositionsTracker(autocommit=True).track, on_separate_thread=True)
    bot.execute()


if __name__ == "__main__":
    main()
''',
    "tests/test_strategy_config.py": '''from strategies.ema_crossover import EMAXOver


def test_strategy_defaults_are_safe():
    assert EMAXOver.parameters["live_trading"] is False
    assert EMAXOver.parameters["fast_ema"] < EMAXOver.parameters["slow_ema"]
''',
}


def write_file(path: Path, content: str, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        print(f"skip existing {path}")
        return
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a safe dry-run aiomql starter project.")
    parser.add_argument("target", help="Target project directory")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)

    for relative, content in FILES.items():
        write_file(target / relative, content, args.overwrite)

    (target / "logs").mkdir(exist_ok=True)
    (target / "trade_results").mkdir(exist_ok=True)

    print("Done. Fill aiomql.json locally from aiomql.json.example before MT5 login.")
    print("The generated strategy defaults to dry-run mode with live_trading set to False.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
