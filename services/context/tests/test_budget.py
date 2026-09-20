"""Unit tests for BudgetCalculator."""

from __future__ import annotations

import secrets
import unittest
from collections.abc import Sequence
from unittest.mock import patch

from app.budget import (
    MAX_NONCE_BYTES,
    MIN_VIABLE_MEMORY_BUDGET,
    BudgetCalculator,
    BudgetRequest,
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
        budget = calc.calculate(BudgetRequest(model="gpt-4o", messages=(), directive=""))
        self.assertEqual(budget.context_window, 128_000)
        self.assertEqual(budget.estimate_kind, ESTIMATE_CHARS_DIV_4)

    def test_calculate_gpt4o_happy_path(self) -> None:
        request = BudgetRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="hello world")],
            directive="be helpful",
        )
        budget = self.calc.calculate(request)
        self.assertEqual(budget.context_window, 128_000)
        self.assertEqual(budget.response_reserve, 4096)  # min(0.15*128k, 16384, 4096)
        self.assertEqual(budget.safety_buffer, int(128_000 * 0.02))
        self.assertEqual(budget.estimate_kind, ESTIMATE_CHARS_DIV_4)
        self.assertGreater(budget.usable_budget, MIN_VIABLE_MEMORY_BUDGET)
        self.assertFalse(budget.is_constrained)

    def test_unknown_model_raises(self) -> None:
        request = BudgetRequest(model="not-a-real-model", messages=(), directive="")
        with self.assertRaises(UnknownModelError):
            self.calc.calculate(request)

    def test_family_buffers_differ(self) -> None:
        gpt = self.calc.calculate(BudgetRequest(model="gpt-4o", messages=(), directive=""))
        claude = self.calc.calculate(
            BudgetRequest(model="claude-sonnet-4-5", messages=(), directive="")
        )
        self.assertEqual(gpt.safety_buffer, int(128_000 * 0.02))
        self.assertEqual(claude.safety_buffer, int(200_000 * 0.05))
        self.assertNotEqual(gpt.safety_buffer, claude.safety_buffer)
        self.assertEqual(gpt.estimate_kind, ESTIMATE_CHARS_DIV_4)
        self.assertEqual(claude.estimate_kind, ESTIMATE_RUNES_DIV_3_5)

    def test_is_constrained_when_prompt_huge(self) -> None:
        huge = "x" * 600_000  # chars_div_4 → 150_000 tokens > gpt-4o usable
        request = BudgetRequest(
            model="gpt-4o",
            messages=[Message(role="user", content=huge)],
            directive="",
        )
        budget = self.calc.calculate(request)
        self.assertEqual(budget.usable_budget, 0)
        self.assertTrue(budget.is_constrained)

    def test_response_reserve_floor_on_small_window(self) -> None:
        # 0.15 * 1000 = 150 < floor 500 → reserve clamps to 500
        calc = BudgetCalculator(_tiny_catalog(context_window=1000, max_output=8000))
        budget = calc.calculate(
            BudgetRequest(model="tiny-model", messages=(), directive="")
        )
        self.assertEqual(budget.response_reserve, 500)
        self.assertEqual(budget.safety_buffer, int(1000 * 0.02))
        # usable = 1000 - 500 - 20 - 0 - 0 = 480 >= 256
        self.assertEqual(budget.usable_budget, 480)
        self.assertFalse(budget.is_constrained)

    def test_multi_message_concat_counts(self) -> None:
        request = BudgetRequest(
            model="gpt-4o",
            messages=[
                Message(role="system", content="a"),
                Message(role="user", content="bcde"),
            ],
            directive="",
        )
        budget = self.calc.calculate(request)
        # "system: a\nuser: bcde" = 20 chars → ceil(20/4)=5
        self.assertEqual(budget.messages_tokens, 5)
        self.assertEqual(budget.directive_tokens, 0)

    def test_estimate_kind_mismatch_fails_closed(self) -> None:
        """Defensive: every estimate_tokens stage must share one labeled kind."""
        cases: list[tuple[list[tuple[int, str]], Sequence[str], str]] = [
            (
                [(1, ESTIMATE_CHARS_DIV_4), (1, ESTIMATE_RUNES_DIV_3_5)],
                (),
                "directive and messages",
            ),
            (
                [
                    (1, ESTIMATE_CHARS_DIV_4),
                    (1, ESTIMATE_CHARS_DIV_4),
                    (1, ESTIMATE_RUNES_DIV_3_5),
                ],
                ['{"n":1}'],
                "tool_schemas",
            ),
            (
                [
                    (1, ESTIMATE_CHARS_DIV_4),
                    (1, ESTIMATE_CHARS_DIV_4),
                    (0, ESTIMATE_CHARS_DIV_4),
                    (1, ESTIMATE_RUNES_DIV_3_5),
                ],
                (),
                "formatter overhead",
            ),
        ]
        for side_effect, tools, needle in cases:
            with self.subTest(needle=needle):
                request = BudgetRequest(
                    model="gpt-4o",
                    messages=[Message(role="user", content="x")],
                    directive="y",
                    tool_schemas=tools,
                )
                with (
                    patch("app.budget.estimate_tokens", side_effect=side_effect),
                    self.assertRaises(RuntimeError) as ctx,
                ):
                    self.calc.calculate(request)
                self.assertIn(needle, str(ctx.exception))

    def test_representative_nonce_matches_token_urlsafe_length(self) -> None:
        for nbytes in (1, 16, 32, MAX_NONCE_BYTES):
            placeholder = representative_nonce(nbytes)
            actual = secrets.token_urlsafe(nbytes)
            self.assertEqual(len(placeholder), len(actual), msg=f"nbytes={nbytes}")
        self.assertEqual(
            len(representative_nonce(MAX_NONCE_BYTES + 10)),
            len(secrets.token_urlsafe(MAX_NONCE_BYTES)),
        )

    def test_larger_nonce_bytes_increases_formatter_overhead(self) -> None:
        small = self.calc.calculate(
            BudgetRequest(
                model="gpt-4o", messages=(), directive="be helpful", nonce_bytes=16
            )
        )
        large = self.calc.calculate(
            BudgetRequest(
                model="gpt-4o", messages=(), directive="be helpful", nonce_bytes=64
            )
        )
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
        without = self.calc.calculate(
            BudgetRequest(model="gpt-4o", messages=(), directive="be helpful")
        )
        tools = ['{"name":"search","parameters":{"type":"object"}}' * 40]
        with_tools = self.calc.calculate(
            BudgetRequest(
                model="gpt-4o",
                messages=(),
                directive="be helpful",
                tool_schemas=tools,
            )
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
        request = BudgetRequest(
            model="tiny-model",
            messages=[Message(role="user", content="hi")],
            directive="be careful",
            tool_schemas=tools,
        )
        budget = calc.calculate(request)
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
