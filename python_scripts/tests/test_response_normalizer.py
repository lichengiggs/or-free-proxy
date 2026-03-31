from __future__ import annotations

import json
import unittest

from python_scripts.response_normalizer import normalize_json_success, normalize_stream_success


class ResponseNormalizerTests(unittest.TestCase):
    def test_wraps_json_body_as_sse_when_stream_requested(self) -> None:
        body = json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode('utf-8')
        response = normalize_stream_success(provider='openrouter', model='m1', body=body, content_type='application/json')
        self.assertIsNone(response.body)
        self.assertIsNotNone(response.stream_chunks)
        self.assertEqual(list(response.stream_chunks)[-1], b'data: [DONE]\n\n')

    def test_keeps_json_success_as_openai_json(self) -> None:
        response = normalize_json_success(provider='openrouter', model='m1', content='hello')
        parsed = json.loads(response.body.decode('utf-8'))
        self.assertEqual(parsed['choices'][0]['message']['content'], 'hello')
