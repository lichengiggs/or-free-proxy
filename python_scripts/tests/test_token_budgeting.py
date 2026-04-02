from __future__ import annotations

import unittest

from python_scripts.token_budgeting import (
    DEFAULT_INPUT_TOKENS,
    DEFAULT_OUTPUT_TOKENS,
    estimate_text_tokens,
    resolve_token_budget,
    shrink_budget_after_limit_error,
)
from python_scripts.token_policy import model_default_output_tokens, model_default_timeout_seconds


class TokenBudgetingTests(unittest.TestCase):
    def test_estimate_text_tokens_uses_character_ratio(self) -> None:
        self.assertEqual(estimate_text_tokens('abcd'), 1)
        self.assertEqual(estimate_text_tokens('abcde'), 2)

    def test_resolve_uses_learned_limit_before_default(self) -> None:
        budget = resolve_token_budget(
            provider='longcat',
            model='LongCat-Flash-Lite',
            prompt='hello' * 100,
            requested_output_tokens=5000,
            learned_limits={
                'longcat/LongCat-Flash-Lite': {
                    'input_tokens_limit': 8192,
                    'output_tokens_limit': 1024,
                    'source': 'learned_from_error',
                }
            },
            model_metadata=None,
        )
        self.assertEqual(budget.output_tokens_limit, 1024)
        self.assertEqual(budget.source, 'learned_from_error')

    def test_resolve_falls_back_to_default_limits(self) -> None:
        budget = resolve_token_budget(
            provider='openrouter',
            model='openrouter/auto:free',
            prompt='hello',
            requested_output_tokens=None,
            learned_limits={},
            model_metadata=None,
        )
        self.assertEqual(budget.output_tokens_limit, DEFAULT_OUTPUT_TOKENS)
        self.assertEqual(budget.input_tokens_limit, DEFAULT_INPUT_TOKENS - DEFAULT_OUTPUT_TOKENS)

    def test_shrink_budget_parses_context_limit_error(self) -> None:
        learned = shrink_budget_after_limit_error(
            provider='openrouter',
            model='openrouter/auto:free',
            prompt='hello' * 5000,
            attempted_output_tokens=4096,
            error_message="This model's maximum context length is 8192 tokens. However, you requested 12000 tokens.",
        )
        self.assertEqual(learned.input_tokens_limit, 8192)
        self.assertEqual(learned.source, 'learned_from_error')

    def test_shrink_budget_uses_backoff_when_error_has_no_numbers(self) -> None:
        learned = shrink_budget_after_limit_error(
            provider='openrouter',
            model='openrouter/auto:free',
            prompt='a' * 20000,
            attempted_output_tokens=4096,
            error_message='prompt is too long',
        )
        self.assertLess(learned.output_tokens_limit, 4096)
        self.assertEqual(learned.source, 'learned_by_backoff')

    def test_model_defaults_align_with_capabilities_for_longcat_thinking(self) -> None:
        self.assertEqual(model_default_output_tokens('longcat', 'LongCat-Flash-Thinking-2601', 4096), 1024)
        self.assertEqual(model_default_timeout_seconds('longcat', 'LongCat-Flash-Thinking-2601', 12), 120)
