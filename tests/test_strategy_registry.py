import unittest

from strategy_registry import load_strategy_class, normalize_strategy_type, strategy_registry


class StrategyRegistryTests(unittest.TestCase):
    def test_normalizes_strategy_type(self) -> None:
        self.assertEqual(normalize_strategy_type("Bollinger-Bands"), "bollinger_bands")

    def test_registry_exposes_bollinger_aliases(self) -> None:
        registry = strategy_registry()

        self.assertIn("bollinger", registry)
        self.assertIn("bollinger_bands", registry)

    def test_load_strategy_class_uses_lazy_registration(self) -> None:
        strategy_cls = load_strategy_class("bollinger_bands")

        self.assertEqual(strategy_cls.__name__, "BollingerBandsAiomqlStrategy")

    def test_unknown_strategy_type_has_available_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "Available: .*bollinger"):
            load_strategy_class("missing")


if __name__ == "__main__":
    unittest.main()
