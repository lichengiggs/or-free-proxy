from __future__ import annotations

import json
import unittest

from python_scripts.response_normalizer import normalize_json_success


class ResponseNormalizerTests(unittest.TestCase):
    def test_keeps_json_success_as_openai_json(self) -> None:
        response = normalize_json_success(provider='openrouter', model='m1', content='hello')
        parsed = json.loads(response.body.decode('utf-8'))
        self.assertEqual(parsed['choices'][0]['message']['content'], 'hello')
