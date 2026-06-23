import unittest

from strategy_registry import discover_strategy_registrations, load_strategy_class, normalize_strategy_type, strategy_registry


class StrategyRegistryTests(unittest.TestCase):
    def test_normalizes_strategy_type(self) -> None:
        self.assertEqual(normalize_strategy_type("Bollinger-Bands"), "bollinger_bands")

    def test_discovers_executable_strategy_packages(self) -> None:
        registrations = {registration.key: registration for registration in discover_strategy_registrations()}

        self.assertIn("bollinger_band", registrations)
        self.assertIn("scalper_major_high_volatility", registrations)

    def test_registry_exposes_strategy_aliases(self) -> None:
        registry = strategy_registry()

        self.assertIn("bollinger", registry)
        self.assertIn("bollinger_bands", registry)
        self.assertIn("bollinger_band", registry)
        self.assertIn("scalper_major", registry)
        self.assertIn("scalper_major_high_volatility", registry)

    def test_load_strategy_class_uses_lazy_registration(self) -> None:
        strategy_cls = load_strategy_class("bollinger_bands")

        self.assertEqual(strategy_cls.__name__, "BollingerBandsAiomqlStrategy")

    def test_load_strategy_class_supports_discovered_strategy(self) -> None:
        strategy_cls = load_strategy_class("scalper-major")

        self.assertEqual(strategy_cls.__name__, "ScalperMajorAiomqlStrategy")

    def test_load_strategy_class_supports_explicit_import_path(self) -> None:
        strategy_cls = load_strategy_class(
            "strategies.ScalperMajorHighVolatility.execution.aiomql_strategy:ScalperMajorAiomqlStrategy"
        )

        self.assertEqual(strategy_cls.__name__, "ScalperMajorAiomqlStrategy")

    def test_unknown_strategy_type_has_available_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "Available: .*bollinger.*scalper_major"):
            load_strategy_class("missing")


if __name__ == "__main__":
    unittest.main()
