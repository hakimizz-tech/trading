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


if __name__ == "__main__":
    unittest.main()
