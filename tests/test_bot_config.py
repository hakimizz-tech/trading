import tempfile
import unittest
from pathlib import Path

from bot_config import load_bot_settings


class BotConfigTests(unittest.TestCase):
    def test_loads_multiple_strategy_specs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                """
                {
                  "symbols": ["EURUSD"],
                  "track_open_positions": false,
                  "strategies": [
                    {
                      "name": "BB",
                      "type": "bollinger",
                      "params": {"signal_mode": "mean_reversion"}
                    },
                    {
                      "name": "BBMA",
                      "type": "bollinger",
                      "symbols": ["GBPUSD"],
                      "params": {"signal_mode": "bbma"}
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            settings = load_bot_settings(path)

        self.assertFalse(settings.track_open_positions)
        self.assertEqual(len(settings.strategies), 2)
        self.assertEqual(settings.strategies[0].symbols, ["EURUSD"])
        self.assertEqual(settings.strategies[1].symbols, ["GBPUSD"])

    def test_requires_symbols_for_each_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text('{"strategies": [{"name": "BB", "type": "bollinger"}]}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "at least one symbol"):
                load_bot_settings(path)

    def test_loads_global_and_strategy_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                """
                {
                  "symbols": ["EURUSD"],
                  "symbol_preflight": false,
                  "aiomql_config": {"trade_record_mode": "sql"},
                  "sessions": [
                    {"name": "global", "start": "07:00", "end": "17:00", "timezone": "UTC", "on_end": "close_loss"}
                  ],
                  "trackers": [
                    {
                      "name": "exit_at_profit",
                      "enabled": true,
                      "interval": 5,
                      "on_separate_thread": true,
                      "params": {"profit_amount": 4.0, "live_management": false}
                    }
                  ],
                  "strategies": [
                    {"name": "BB", "type": "bollinger"},
                    {
                      "name": "London BB",
                      "type": "bollinger",
                      "sessions": [
                        {"start": "08:00", "end": "12:00", "timezone": "Europe/London"}
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            settings = load_bot_settings(path)

        self.assertFalse(settings.symbol_preflight)
        self.assertEqual(settings.aiomql_config["trade_record_mode"], "sql")
        self.assertEqual(settings.sessions[0].name, "global")
        self.assertEqual(settings.sessions[0].on_end, "close_loss")
        self.assertEqual(settings.strategies[0].sessions[0].start, "07:00")
        self.assertEqual(settings.strategies[1].sessions[0].start, "08:00")
        self.assertEqual(settings.trackers[0].name, "exit_at_profit")
        self.assertEqual(settings.trackers[0].interval, 5)
        self.assertTrue(settings.trackers[0].on_separate_thread)


if __name__ == "__main__":
    unittest.main()
