from __future__ import annotations

import json
import os
import unittest

from python_scripts.provider_adapter import ProviderAdapter
from python_scripts.provider_catalog import get_provider, list_providers


class MatrixTransport:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, timeout
        if method == 'GET' and url.endswith('/models'):
            if self.provider_name == 'gemini':
                return 200, {}, json.dumps({'models': [{'id': 'models/gemini-2.0-flash'}]}).encode()
            return 200, {}, json.dumps({'data': [{'id': f'{self.provider_name}-model', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        if self.provider_name == 'gemini':
            return 200, {}, json.dumps({'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}).encode()
        payload = json.loads((body or b'{}').decode('utf-8'))
        return 200, {}, json.dumps({'choices': [{'message': {'content': f"ok:{payload.get('model', '')}"}}]}).encode()


class ProviderMatrixTests(unittest.TestCase):
    def test_every_provider_can_list_and_chat(self) -> None:
        for provider in list_providers():
            with self.subTest(provider=provider.name):
                os.environ[provider.api_key_env] = 'test-key'
                adapter = ProviderAdapter(provider=get_provider(provider.name), api_key='test-key', transport=MatrixTransport(provider.name))
                models = adapter.list_models()
                self.assertTrue(models)
                self.assertTrue(adapter.chat_text(models[0], 'ok').startswith('ok'))
