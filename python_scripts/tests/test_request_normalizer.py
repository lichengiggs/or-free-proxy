from __future__ import annotations

import unittest

from python_scripts.request_normalizer import normalize_chat_request


class RequestNormalizerAliasTests(unittest.TestCase):
    def test_rejects_coding_alias(self) -> None:
        payload = {
            'model': 'free-proxy/coding',
            'messages': [{'role': 'user', 'content': 'hi'}],
        }
        with self.assertRaises(ValueError) as ctx:
            normalize_chat_request(payload)
        self.assertEqual(
            str(ctx.exception),
            "model 'coding' is no longer supported. Use 'free-proxy/auto' instead.",
        )

    def test_accepts_auto_alias(self) -> None:
        payload = {
            'model': 'free-proxy/auto',
            'messages': [{'role': 'user', 'content': 'hi'}],
        }
        request = normalize_chat_request(payload)
        self.assertEqual(request.public_model, 'free-proxy/auto')


class RequestNormalizerFieldTests(unittest.TestCase):
    def test_extracts_requested_model_and_normalizes_max_tokens(self) -> None:
        payload = {
            'model': 'auto',
            'requested_model': 'longcat/LongCat-Flash-Lite',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'max_completion_tokens': 321,
            'temperature': 0.2,
            'stream': True,
        }
        request = normalize_chat_request(payload)
        self.assertEqual(request.requested_model, 'longcat/LongCat-Flash-Lite')
        self.assertEqual(request.max_output_tokens, 321)
        self.assertEqual(request.temperature, 0.2)
        self.assertTrue(request.stream)

    def test_rejects_empty_messages(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_chat_request({'model': 'auto', 'messages': []})
        self.assertEqual(str(ctx.exception), 'messages must not be empty')
