"""Unit tests for BudgetCalculator."""

from __future__ import annotations

import secrets
import unittest
from unittest.mock import patch

from app.budget import (
    MAX_NONCE_BYTES,
    MIN_VIABLE_MEMORY_BUDGET,
    BudgetCalculator,
    Message,
    WrappedMemoryEstimate,
    estimate_wrapped_memory_tokens,
    representative_nonce,
)
from app.capability_catalog import (
    CapabilityCatalog,
    ModelCapability,
    TokenizerFamilyPolicy,
    UnknownModelError,
    default_catalog,
)
from app.estimate import ESTIMATE_CHARS_DIV_4, ESTIMATE_RUNES_DIV_3_5


def _tiny_catalog(*, context_window: int, max_output: int) -> CapabilityCatalog:
    return CapabilityCatalog(
        schema_version=1,
        source="test",
        models={
            "tiny-model": ModelCapability(
                model_id="tiny-model",
                provider="test",
                context_window=context_window,
                max_output_tokens=max_output,
                supports_tools=False,
                supports_vision=False,
                supports_streaming=True,
                tokenizer_family="o200k_base",
            )
        },
        tokenizer_families={
            "o200k_base": TokenizerFamilyPolicy(ESTIMATE_CHARS_DIV_4, 0.02),
        },
    )


class BudgetCalculatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calc = BudgetCalculator(default_catalog())

    def test_default_catalog_constructor(self) -> None:
        calc = BudgetCalculator()
        budget = calc.calculate("gpt-4o", [], "")
        self.assertEqual(budget.context_window, 128_000)
        self.assertEqual(budget.estimate_kind, ESTIMATE_CHARS_DIV_4)

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

    def test_response_reserve_floor_on_small_window(self) -> None:
        # 0.15 * 1000 = 150 < floor 500 → reserve clamps to 500
        calc = BudgetCalculator(_tiny_catalog(context_window=1000, max_output=8000))
        budget = calc.calculate("tiny-model", [], "")
        self.assertEqual(budget.response_reserve, 500)
        self.assertEqual(budget.safety_buffer, int(1000 * 0.02))
        # usable = 1000 - 500 - 20 - 0 - 0 = 480 >= 256
        self.assertEqual(budget.usable_budget, 480)
        self.assertFalse(budget.is_constrained)

    def test_multi_message_concat_counts(self) -> None:
        budget = self.calc.calculate(
            "gpt-4o",
            [
                Message(role="system", content="a"),
                Message(role="user", content="bcde"),
            ],
            directive="",
        )
        # "system: a\nuser: bcde" = 20 chars → ceil(20/4)=5
        self.assertEqual(budget.messages_tokens, 5)
        self.assertEqual(budget.directive_tokens, 0)

    def test_estimate_kind_mismatch_fails_closed(self) -> None:
        """Defensive: directive/messages must share one labeled estimate_kind."""
        messages = [Message(role="user", content="x")]
        patcher = patch(
            "app.budget.estimate_tokens",
            side_effect=[(1, ESTIMATE_CHARS_DIV_4), (1, ESTIMATE_RUNES_DIV_3_5)],
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(RuntimeError):
            self.calc.calculate("gpt-4o", messages, "y")

    def test_estimate_kind_mismatch_on_tool_schemas_fails_closed(self) -> None:
        messages = [Message(role="user", content="x")]
        patcher = patch(
            "app.budget.estimate_tokens",
            side_effect=[
                (1, ESTIMATE_CHARS_DIV_4),  # directive
                (1, ESTIMATE_CHARS_DIV_4),  # messages
                (1, ESTIMATE_RUNES_DIV_3_5),  # tools
            ],
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(RuntimeError) as ctx:
            self.calc.calculate("gpt-4o", messages, "y", tool_schemas=['{"n":1}'])
        self.assertIn("tool_schemas", str(ctx.exception))

    def test_estimate_kind_mismatch_on_formatter_overhead_fails_closed(self) -> None:
        messages = [Message(role="user", content="x")]
        patcher = patch(
            "app.budget.estimate_tokens",
            side_effect=[
                (1, ESTIMATE_CHARS_DIV_4),  # directive
                (1, ESTIMATE_CHARS_DIV_4),  # messages
                (0, ESTIMATE_CHARS_DIV_4),  # tools (empty)
                (1, ESTIMATE_RUNES_DIV_3_5),  # formatter overhead
            ],
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(RuntimeError) as ctx:
            self.calc.calculate("gpt-4o", messages, "y")
        self.assertIn("formatter overhead", str(ctx.exception))

    def test_representative_nonce_matches_token_urlsafe_length(self) -> None:
        for nbytes in (1, 16, 32, MAX_NONCE_BYTES):
            placeholder = representative_nonce(nbytes)
            actual = secrets.token_urlsafe(nbytes)
            self.assertEqual(len(placeholder), len(actual), msg=f"nbytes={nbytes}")
        self.assertEqual(len(representative_nonce(MAX_NONCE_BYTES + 10)), len(secrets.token_urlsafe(MAX_NONCE_BYTES)))

    def test_larger_nonce_bytes_increases_formatter_overhead(self) -> None:
        small = self.calc.calculate("gpt-4o", [], "be helpful", nonce_bytes=16)
        large = self.calc.calculate("gpt-4o", [], "be helpful", nonce_bytes=64)
        self.assertGreater(large.formatter_overhead_tokens, small.formatter_overhead_tokens)

    def test_estimate_wrapped_memory_tokens_uses_nonce(self) -> None:
        policy = default_catalog().family_policy("o200k_base")
        short = estimate_wrapped_memory_tokens(
            WrappedMemoryEstimate(
                content="hello",
                memory_id="m1",
                category="factual",
                policy=policy,
                nonce=representative_nonce(16),
            )
        )
        long = estimate_wrapped_memory_tokens(
            WrappedMemoryEstimate(
                content="hello",
                memory_id="m1",
                category="factual",
                policy=policy,
                nonce=representative_nonce(64),
            )
        )
        self.assertGreater(long[0], short[0])
        self.assertEqual(short[1], long[1])

    def test_tool_schemas_reduce_usable_budget(self) -> None:
        """F4-028: tool schemas are subtracted before usable_budget."""
        without = self.calc.calculate("gpt-4o", [], "be helpful")
        tools = ['{"name":"search","parameters":{"type":"object"}}' * 40]
        with_tools = self.calc.calculate(
            "gpt-4o",
            [],
            "be helpful",
            tool_schemas=tools,
        )
        self.assertGreater(with_tools.tool_schemas_tokens, 0)
        self.assertGreater(with_tools.formatter_overhead_tokens, 0)
        self.assertEqual(
            without.usable_budget - with_tools.usable_budget,
            with_tools.tool_schemas_tokens
            + with_tools.formatter_overhead_tokens
            - without.formatter_overhead_tokens,
        )

    def test_near_window_tools_do_not_overflow_post_format_ceiling(self) -> None:
        """F4-028: usable_budget + tools + overhead stay inside the window."""
        calc = BudgetCalculator(_tiny_catalog(context_window=2000, max_output=500))
        tools = ["x" * 800]  # ~200 tokens under chars_div_4
        budget = calc.calculate(
            "tiny-model",
            [Message(role="user", content="hi")],
            directive="be careful",
            tool_schemas=tools,
        )
        accounted = (
            budget.response_reserve
            + budget.safety_buffer
            + budget.directive_tokens
            + budget.messages_tokens
            + budget.tool_schemas_tokens
            + budget.formatter_overhead_tokens
            + budget.usable_budget
        )
        self.assertLessEqual(accounted, budget.context_window)


if __name__ == "__main__":
    unittest.main()
