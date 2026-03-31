from __future__ import annotations

import json
import unittest

from python_scripts.protocol_converter import gemini_json_to_openai_chat


class ProtocolConverterTests(unittest.TestCase):
    def test_gemini_json_to_openai_chat(self) -> None:
        payload = {
            'candidates': [
                {
                    'content': {
                        'parts': [{'text': 'hello from gemini'}],
                    }
                }
            ]
        }
        body = gemini_json_to_openai_chat('gemini', 'gemini-3.1-flash-lite-preview', payload)
        parsed = json.loads(body.decode('utf-8'))
        self.assertEqual(parsed['model'], 'gemini/gemini-3.1-flash-lite-preview')
        self.assertEqual(parsed['choices'][0]['message']['content'], 'hello from gemini')
