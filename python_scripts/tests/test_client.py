from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from python_scripts.client import ProviderClient, UrlLibTransport, build_url
from python_scripts.config import get_provider_spec
from python_scripts.errors import classify_error


class FakeTransport:
    def __init__(self, responses: dict[tuple[str, str], tuple[int, dict[str, str], bytes]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, str] | None, bytes | None]] = []

    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 30):
        self.requests.append((method, url, headers, body))
        return self.responses[(method, url)]


class ClientTests(unittest.TestCase):
    def test_build_url_handles_slashes_and_query(self) -> None:
        self.assertEqual(
            build_url('https://openrouter.ai/api/v1/', '/chat/completions'),
            'https://openrouter.ai/api/v1/chat/completions',
        )
        self.assertEqual(
            build_url('https://models.github.ai/inference', 'chat/completions', {'api-version': '2024-12-01-preview'}),
            'https://models.github.ai/inference/chat/completions?api-version=2024-12-01-preview',
        )

    def test_classify_error_maps_core_categories(self) -> None:
        self.assertEqual(classify_error(401, '').category, 'auth')
        self.assertEqual(classify_error(404, '').category, 'model_not_found')
        self.assertEqual(classify_error(429, '').category, 'rate_limit')
        self.assertEqual(classify_error(402, 'insufficient credits').category, 'quota')
        self.assertEqual(classify_error(503, 'service unavailable').category, 'server')
        self.assertEqual(
            classify_error(0, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate').category,
            'network',
        )

    def test_urllib_transport_uses_certifi_ssl_context(self) -> None:
        fake_response = unittest.mock.MagicMock()
        fake_response.__enter__.return_value = fake_response
        fake_response.status = 200
        fake_response.headers.items.return_value = [('content-type', 'application/json')]
        fake_response.read.return_value = b'{}'

        with patch('python_scripts.client.certifi.where', return_value='/tmp/test-cert.pem') as where_mock, \
             patch('python_scripts.client.ssl.create_default_context', return_value='ssl-context') as context_mock, \
             patch('python_scripts.client.urlopen', return_value=fake_response) as urlopen_mock:
            transport = UrlLibTransport()
            status, headers, body = transport.request('GET', 'https://example.com/models')

        self.assertEqual(status, 200)
        self.assertEqual(headers, {'content-type': 'application/json'})
        self.assertEqual(body, b'{}')
        where_mock.assert_called_once_with()
        context_mock.assert_called_once_with(cafile='/tmp/test-cert.pem')
        self.assertEqual(urlopen_mock.call_args.kwargs['context'], 'ssl-context')

    def test_openai_list_models_and_chat(self) -> None:
        spec = get_provider_spec('openrouter')
        transport = FakeTransport({
            ('GET', 'https://openrouter.ai/api/v1/models'): (200, {}, json.dumps({'data': [{'id': 'a'}, {'id': 'b'}]}).encode()),
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['a', 'b'])
        self.assertEqual(client.chat('a', 'ok'), 'ok')

    def test_openai_chat_uses_requested_max_tokens(self) -> None:
        spec = get_provider_spec('openrouter')
        transport = FakeTransport({
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.chat('a', 'hello', max_tokens=256), 'ok')

        _, _, _, body = transport.requests[-1]
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.assertEqual(payload['max_tokens'], 256)

    def test_openai_chat_raises_when_content_is_null(self) -> None:
        spec = get_provider_spec('openrouter')
        transport = FakeTransport({
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': None}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        with self.assertRaises(Exception):
            client.chat('a', 'ok')

    def test_openrouter_only_keeps_free_or_zero_cost_models(self) -> None:
        spec = get_provider_spec('openrouter')
        transport = FakeTransport({
            ('GET', 'https://openrouter.ai/api/v1/models'): (
                200,
                {},
                json.dumps(
                    {
                        'data': [
                            {'id': 'openrouter/auto:free', 'pricing': {'prompt': '0.10', 'completion': '0.20'}},
                            {'id': 'zero-cost', 'pricing': {'prompt': '0', 'completion': '0'}},
                            {'id': 'paid-model', 'pricing': {'prompt': '0.01', 'completion': '0'}},
                        ]
                    }
                ).encode(),
            )
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['openrouter/auto:free', 'zero-cost'])

    def test_github_uses_preview_version(self) -> None:
        spec = get_provider_spec('github')
        transport = FakeTransport({
            ('GET', 'https://models.github.ai/inference/models'): (404, {}, b'not found'),
            ('POST', 'https://models.github.ai/inference/chat/completions?api-version=2024-12-01-preview'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['gpt-4o-mini', 'gpt-4o', 'DeepSeek-V3-0324', 'Llama-3.3-70B-Instruct'])
        self.assertEqual(client.chat('gpt-4o-mini', 'ok'), 'ok')

    def test_cerebras_model_hint_fallback(self) -> None:
        spec = get_provider_spec('cerebras')
        transport = FakeTransport({
            ('GET', 'https://api.cerebras.ai/v1/models'): (403, {}, b'error code: 1010'),
            ('POST', 'https://api.cerebras.ai/v1/chat/completions'): (403, {}, b'error code: 1010'),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['gpt-oss-120b', 'llama-3.1-8b'])
        with self.assertRaises(Exception):
            client.chat('llama-3.3-70b', 'ok')

    def test_groq_model_hint_fallback_on_list_error(self) -> None:
        spec = get_provider_spec('groq')
        transport = FakeTransport({
            ('GET', 'https://api.groq.com/openai/v1/models'): (403, {}, json.dumps({'error': {'message': 'forbidden'}}).encode()),
            ('POST', 'https://api.groq.com/openai/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['llama-3.1-8b-instant', 'llama-3.3-70b-versatile'])
        self.assertEqual(client.chat('llama-3.1-8b-instant', 'ok'), 'ok')

    def test_longcat_model_hint_fallback_on_list_error(self) -> None:
        spec = get_provider_spec('longcat')
        transport = FakeTransport({
            ('GET', 'https://api.longcat.chat/openai/models'): (404, {}, json.dumps({'error': {'message': 'not found'}}).encode()),
            ('POST', 'https://api.longcat.chat/openai/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(
            client.list_models(),
            ['LongCat-Flash-Chat', 'LongCat-Flash-Thinking', 'LongCat-Flash-Thinking-2601', 'LongCat-Flash-Lite'],
        )
        self.assertEqual(client.chat('LongCat-Flash-Chat', 'ok'), 'ok')

    def test_gemini_normalizes_models_and_chat(self) -> None:
        spec = get_provider_spec('gemini')
        transport = FakeTransport({
            ('GET', 'https://generativelanguage.googleapis.com/v1beta/models'): (200, {}, json.dumps({'models': [{'id': 'models/gemini-2.0-flash'}]}).encode()),
            ('POST', 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'): (200, {}, json.dumps({'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['gemini-2.0-flash'])
        self.assertEqual(client.chat('models/gemini-2.0-flash', 'ok'), 'ok')
