from __future__ import annotations

import unittest

from python_scripts.token_policy import LONGCAT_THINKING_PROBE_OUTPUT_TOKENS, model_default_output_tokens, model_default_timeout_seconds, probe_output_tokens, response_token_budget, trim_prompt


class TokenPolicyTests(unittest.TestCase):
    def test_trim_prompt_keeps_short_text(self) -> None:
        text = 'hello world'
        self.assertEqual(trim_prompt('github', text), text)

    def test_trim_prompt_truncates_long_text(self) -> None:
        text = 'a' * 7000
        trimmed = trim_prompt('github', text)
        self.assertNotEqual(trimmed, text)
        self.assertIn('...[内容已截断]...', trimmed)
        self.assertTrue(trimmed.startswith('a'))
        self.assertTrue(trimmed.endswith('a'))

    def test_response_token_budget_uses_updated_default(self) -> None:
        self.assertEqual(response_token_budget('unknown-provider'), 4096)

    def test_probe_output_tokens_uses_longcat_thinking_budget(self) -> None:
        self.assertEqual(probe_output_tokens('longcat', 'LongCat-Flash-Thinking-2601'), LONGCAT_THINKING_PROBE_OUTPUT_TOKENS)

    def test_model_defaults_use_capabilities_for_longcat_thinking(self) -> None:
        self.assertEqual(model_default_output_tokens('longcat', 'LongCat-Flash-Thinking-2601', 4096), 1024)
        self.assertEqual(model_default_timeout_seconds('longcat', 'LongCat-Flash-Thinking-2601', 12), 120)
