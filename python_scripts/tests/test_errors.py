from __future__ import annotations

import unittest

from python_scripts.errors import classify_error, remediation_suggestion


class ErrorTests(unittest.TestCase):
    def test_classify_error_by_text_without_status(self) -> None:
        self.assertEqual(classify_error(0, 'invalid api key').category, 'auth')
        self.assertEqual(classify_error(0, 'quota exceeded').category, 'quota')
        self.assertEqual(classify_error(0, 'model not found').category, 'model_not_found')

    def test_remediation_suggestion_returns_actionable_text(self) -> None:
        self.assertIn('API Key', remediation_suggestion('auth', 'groq'))
        self.assertIn('额度', remediation_suggestion('quota', 'openrouter'))
        self.assertIn('模型', remediation_suggestion('model_not_found', 'sambanova'))
