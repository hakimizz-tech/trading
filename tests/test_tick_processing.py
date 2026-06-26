import unittest

import pandas as pd

from market_data import latest_tick, to_tick_frame


class FakeAiomqlTick:
    def __init__(
        self,
        *,
        time: int,
        bid: float,
        ask: float,
        last: float,
        volume: float,
        flags: int,
        volume_real: float,
        time_msc: int,
        Index: int,
    ) -> None:
        self.time = time
        self.bid = bid
        self.ask = ask
        self.last = last
        self.volume = volume
        self.flags = flags
        self.volume_real = volume_real
        self.time_msc = time_msc
        self.Index = Index

    def dict(self) -> dict[str, float | int]:
        return {
            "time": self.time,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "volume": self.volume,
            "flags": self.flags,
            "volume_real": self.volume_real,
            "time_msc": self.time_msc,
            "Index": self.Index,
        }


class FakeAiomqlTicks:
    def __init__(self) -> None:
        self.data = pd.DataFrame(
            [
                {
                    "time": 1767225600,
                    "bid": 1.1000,
                    "ask": 1.1002,
                    "last": 1.1001,
                    "volume": 3,
                    "flags": 6,
                    "volume_real": 2.5,
                    "time_msc": 1767225600123,
                    "Index": 0,
                },
                {
                    "time": 1767225601,
                    "bid": 1.1001,
                    "ask": 1.1004,
                    "last": 1.1002,
                    "volume": 4,
                    "flags": 6,
                    "volume_real": 3.5,
                    "time_msc": 1767225601456,
                    "Index": 1,
                },
            ]
        )


class TickProcessingTests(unittest.TestCase):
    def test_aiomql_ticks_data_attribute_convert_to_tick_frame(self) -> None:
        data = to_tick_frame(FakeAiomqlTicks(), symbol="EURUSD")

        self.assertEqual(str(data.index.tz), "UTC")
        self.assertIn("spread", data.columns)
        self.assertIn("mid", data.columns)
        self.assertIn("volume_real", data.columns)
        self.assertIn("index", data.columns)
        self.assertAlmostEqual(float(data["spread"].iloc[0]), 0.0002, places=8)
        self.assertAlmostEqual(float(data["mid"].iloc[0]), 1.1001, places=8)
        self.assertEqual(data.attrs["symbol"], "EURUSD")

    def test_aiomql_tick_objects_convert_to_tick_frame(self) -> None:
        ticks = [
            FakeAiomqlTick(
                time=1767225600,
                bid=1.1,
                ask=1.1002,
                last=1.1001,
                volume=3,
                flags=6,
                volume_real=2.5,
                time_msc=1767225600123,
                Index=0,
            )
        ]

        data = to_tick_frame(ticks, symbol="EURUSD")

        self.assertEqual(str(data.index.tz), "UTC")
        self.assertEqual(float(data["volume"].iloc[0]), 3.0)
        self.assertEqual(float(data["flags"].iloc[0]), 6.0)
        self.assertEqual(float(data["index"].iloc[0]), 0.0)

    def test_missing_last_and_volume_are_defaulted(self) -> None:
        data = to_tick_frame([{"time": 1767225600, "bid": 1.1, "ask": 1.1002}])

        self.assertEqual(float(data["last"].iloc[0]), 0.0)
        self.assertEqual(float(data["volume"].iloc[0]), 0.0)
        self.assertAlmostEqual(float(data["spread"].iloc[0]), 0.0002, places=8)

    def test_latest_tick_returns_plain_dict(self) -> None:
        tick = latest_tick(FakeAiomqlTicks(), symbol="EURUSD")

        self.assertEqual(tick["symbol"], "EURUSD")
        self.assertAlmostEqual(float(tick["bid"]), 1.1001, places=8)
        self.assertIn("timestamp", tick)


if __name__ == "__main__":
    unittest.main()
