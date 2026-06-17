import unittest
from pathlib import Path


class StrategyDefinitionTests(unittest.TestCase):
    def test_strategy_definition_has_framework_sections(self) -> None:
        strategy_doc = Path(__file__).resolve().parents[1] / "STRATEGY.md"
        text = strategy_doc.read_text(encoding="utf-8")

        required_sections = [
            "## Overview",
            "## Entry Rules",
            "## Entry Execution",
            "## Exit Rules",
            "## Position Sizing",
            "## Risk Parameters",
            "## Filters",
            "## Performance Criteria",
            "## Backtest Results",
            "## Dependencies",
            "## Change Log",
        ]

        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, text)

    def test_strategy_definition_marks_live_status_as_not_approved(self) -> None:
        strategy_doc = Path(__file__).resolve().parents[1] / "STRATEGY.md"
        text = strategy_doc.read_text(encoding="utf-8").lower()

        self.assertIn("research and dry-run only", text)
        self.assertIn("not approved for live trading", text)


if __name__ == "__main__":
    unittest.main()
