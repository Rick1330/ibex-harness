"""Token estimate bound tests."""

from __future__ import annotations

import math
import unittest

from app.capability_catalog import TokenizerFamilyPolicy
from app.estimate import (
    ESTIMATE_CHARS_DIV_4,
    ESTIMATE_RUNES_DIV_3_5,
    estimate_tokens,
)


class EstimateTests(unittest.TestCase):
    def test_estimate_bounds_chars_div_4(self) -> None:
        policy = TokenizerFamilyPolicy(ESTIMATE_CHARS_DIV_4, 0.02)
        self.assertEqual(estimate_tokens("", policy), (0, ESTIMATE_CHARS_DIV_4))
        text = "abcd"  # 4 chars → 1
        self.assertEqual(estimate_tokens(text, policy), (1, ESTIMATE_CHARS_DIV_4))
        text5 = "abcde"
        self.assertEqual(estimate_tokens(text5, policy), (math.ceil(5 / 4), ESTIMATE_CHARS_DIV_4))

    def test_estimate_claude_matches_adr0043(self) -> None:
        policy = TokenizerFamilyPolicy(ESTIMATE_RUNES_DIV_3_5, 0.05)
        self.assertEqual(estimate_tokens("", policy), (0, ESTIMATE_RUNES_DIV_3_5))
        # "hello" = 5 runes → (5*2+6)//7 = 16//7 = 2
        self.assertEqual(estimate_tokens("hello", policy), (2, ESTIMATE_RUNES_DIV_3_5))
        # 7 runes → (14+6)//7 = 2; 8 runes → (16+6)//7 = 3
        self.assertEqual(estimate_tokens("abcdefg", policy), ((7 * 2 + 6) // 7, ESTIMATE_RUNES_DIV_3_5))


if __name__ == "__main__":
    unittest.main()
