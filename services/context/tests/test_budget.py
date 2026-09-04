"""Unit tests for BudgetCalculator."""

from __future__ import annotations

import unittest

from app.budget import MIN_VIABLE_MEMORY_BUDGET, BudgetCalculator, Message
from app.capability_catalog import UnknownModelError, default_catalog
from app.estimate import ESTIMATE_CHARS_DIV_4, ESTIMATE_RUNES_DIV_3_5


class BudgetCalculatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calc = BudgetCalculator(default_catalog())

    def test_calculate_gpt4o_happy_path(self) -> None:
        budget = self.calc.calculate(
            "gpt-4o",
            [Message(role="user", content="hello world")],
            directive="be helpful",
        )
        self.assertEqual(budget.context_window, 128_000)
        self.assertEqual(budget.response_reserve, 4096)  # min(0.15*128k, 16384, 4096)
        self.assertEqual(budget.safety_buffer, int(128_000 * 0.02))
        self.assertEqual(budget.estimate_kind, ESTIMATE_CHARS_DIV_4)
        self.assertGreater(budget.usable_budget, MIN_VIABLE_MEMORY_BUDGET)
        self.assertFalse(budget.is_constrained)

    def test_unknown_model_raises(self) -> None:
        with self.assertRaises(UnknownModelError):
            self.calc.calculate("not-a-real-model", [], "")

    def test_family_buffers_differ(self) -> None:
        gpt = self.calc.calculate("gpt-4o", [], "")
        claude = self.calc.calculate("claude-sonnet-4-5", [], "")
        self.assertEqual(gpt.safety_buffer, int(128_000 * 0.02))
        self.assertEqual(claude.safety_buffer, int(200_000 * 0.05))
        self.assertNotEqual(gpt.safety_buffer, claude.safety_buffer)
        self.assertEqual(gpt.estimate_kind, ESTIMATE_CHARS_DIV_4)
        self.assertEqual(claude.estimate_kind, ESTIMATE_RUNES_DIV_3_5)

    def test_is_constrained_when_prompt_huge(self) -> None:
        huge = "x" * 600_000  # chars_div_4 → 150_000 tokens > gpt-4o usable
        budget = self.calc.calculate(
            "gpt-4o",
            [Message(role="user", content=huge)],
            directive="",
        )
        self.assertEqual(budget.usable_budget, 0)
        self.assertTrue(budget.is_constrained)


if __name__ == "__main__":
    unittest.main()
