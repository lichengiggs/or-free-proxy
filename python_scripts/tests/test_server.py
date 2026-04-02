from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from python_scripts.cli import build_parser
from python_scripts.service import OpenAIForwardResult, ProxyService
from python_scripts.server_fastapi import app, get_service, _service


@dataclass
class FakeResult:
    ok: bool
    actual_model: str | None = None
    content: str | None = None
    error: str | None = None
    category: str | None = None
    status: int | None = None
    suggestion: str | None = None


class FakeService:
    def __init__(self) -> None:
        self.saved_keys: list[tuple[str, str]] = []

    def provider_key_statuses(self) -> dict[str, dict[str, object]]:
        return {
            'openrouter': {'configured': True, 'masked': 'sk-o***1234', 'env': 'OPENROUTER_API_KEY'},
            'longcat': {'configured': False, 'masked': '', 'env': 'LONGCAT_API_KEY'},
        }

    def available_providers(self) -> list[str]:
        return ['openrouter']

    def list_models(self, provider: str) -> list[str]:
        return ['m1'] if provider == 'openrouter' else []

    def recommended_models(self, provider: str, requested_model: str | None = None) -> list[str]:
        ordered: list[str] = []
        if requested_model:
            ordered.append(requested_model)
        return ordered + ['m1', 'm2']

    def public_models(self) -> list[dict[str, str]]:
        return [
            {'id': 'free-proxy/auto', 'object': 'model', 'owned_by': 'free-proxy'},
        ]

    class _Relay:
        def normalize(self, payload: dict[str, object]):
            model = str(payload.get('model', '')).strip()
            if not model:
                raise ValueError('missing model')
            if model in {'coding', 'free-proxy/coding', 'free_proxy/coding'}:
                raise ValueError("model 'coding' is no longer supported. Use 'free-proxy/auto' instead.")
            if model not in {'auto', 'free-proxy/auto', 'free_proxy/auto'}:
                raise ValueError("model must be 'free-proxy/auto'")
            return type('Request', (), {'public_model': 'free-proxy/auto', 'stream': bool(payload.get('stream'))})()

        def handle_chat(self, request):
            if bool(getattr(request, 'stream', False)):
                return type(
                    'RelayResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'text/event-stream; charset=utf-8'},
                        'body': None,
                        'stream_chunks': [
                            b'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","model":"openrouter/openrouter/auto:free","choices":[{"index":0,"delta":{"role":"assistant","content":"echo:hello"},"finish_reason":null}]}\n\n',
                            b'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","model":"openrouter/openrouter/auto:free","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n',
                            b'data: [DONE]\n\n',
                        ],
                    },
                )()
            return type(
                'RelayResponse',
                (),
                {
                    'status': 200,
                    'headers': {'Content-Type': 'application/json; charset=utf-8'},
                    'body': json.dumps(
                        {
                            'id': 'chatcmpl-test',
                            'object': 'chat.completion',
                            'model': 'openrouter/openrouter/auto:free',
                            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'echo:hello'}, 'finish_reason': 'stop'}],
                            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                        }
                    ).encode('utf-8'),
                    'stream_chunks': None,
                },
            )()

    def openai_relay(self):
        return self._Relay()

    def verify_provider_key(self, provider: str) -> dict[str, object]:
        return {'ok': True, 'provider': provider, 'verified_model': 'm1'}

    def preferred_model(self) -> str | None:
        return 'openrouter/m1'

    def save_preferred_model(self, provider: str, model: str) -> dict[str, object]:
        self.saved_keys.append((provider, model))
        return {'ok': True, 'provider': provider, 'model': model, 'requested_model': f'{provider}/{model}'}

    def save_provider_key(self, provider: str, api_key: str) -> dict[str, object]:
        self.saved_keys.append((provider, api_key))
        return {'ok': True, 'provider': provider, 'masked': 'sk-o***1234'}

    def probe(self, provider: str, model: str) -> FakeResult:
        return FakeResult(provider == 'openrouter', actual_model=model, content='ok', error='fail', category='server', status=500, suggestion='retry')

    def chat(self, provider: str, model: str, prompt: str) -> FakeResult:
        if provider == 'openrouter':
            return FakeResult(ok=True, actual_model=model, content=f'echo:{prompt}')
        return FakeResult(ok=False, error='provider not available', category='auth', status=401, suggestion='set key')

    def forward_direct_chat(self, provider: str, model: str, payload: dict[str, object]) -> OpenAIForwardResult:
        if payload.get('stream'):
            return OpenAIForwardResult(ok=True, provider=provider, model=model, status=200, headers={'Content-Type': 'text/event-stream; charset=utf-8'}, body=b'', stream_chunks=[
                b'data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"echo:hello"},"index":0}]}\n\n',
                b'data: [DONE]\n\n',
            ])
        return OpenAIForwardResult(ok=True, provider=provider, model=model, status=200, headers={'Content-Type': 'application/json; charset=utf-8'}, body=json.dumps({'choices': [{'message': {'role': 'assistant', 'content': 'echo:hello'}}]}).encode('utf-8'))


class ServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_service = _service
        self._old_openclaw_test_dir = os.environ.get('OPENCLAW_TEST_DIR')
        self._old_opencode_test_dir = os.environ.get('OPENCODE_TEST_DIR')
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['OPENCLAW_TEST_DIR'] = self.tmp.name
        import python_scripts.server_fastapi as sf
        sf._service = FakeService()

    def tearDown(self) -> None:
        import python_scripts.server_fastapi as sf
        sf._service = self._old_service
        if self._old_openclaw_test_dir is None:
            os.environ.pop('OPENCLAW_TEST_DIR', None)
        else:
            os.environ['OPENCLAW_TEST_DIR'] = self._old_openclaw_test_dir
        if self._old_opencode_test_dir is None:
            os.environ.pop('OPENCODE_TEST_DIR', None)
        else:
            os.environ['OPENCODE_TEST_DIR'] = self._old_opencode_test_dir
        self.tmp.cleanup()

    def test_index_page_returns_html(self) -> None:
        client = TestClient(app)
        resp = client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/html', resp.headers.get('content-type', ''))
        self.assertIn('free-proxy 控制台', resp.text)

    def test_serve_parser_accepts_debug_flag(self) -> None:
        args = build_parser().parse_args(['serve', '--debug'])
        self.assertEqual(args.command, 'serve')
        self.assertTrue(args.debug)

    def test_health_route(self) -> None:
        client = TestClient(app)
        resp = client.get('/health')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'ok': True})

    def test_provider_keys_status_route(self) -> None:
        client = TestClient(app)
        resp = client.get('/api/provider-keys')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(bool(body['openrouter']['configured']))

    def test_preferred_model_route_returns_current_selection(self) -> None:
        client = TestClient(app)
        resp = client.get('/api/preferred-model')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['requested_model'], 'openrouter/m1')

    def test_preferred_model_route_persists_selection(self) -> None:
        client = TestClient(app)
        resp = client.post('/api/preferred-model', json={'provider': 'openrouter', 'model': 'm2'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['requested_model'], 'openrouter/m2')

    def test_openai_models_route_returns_public_aliases(self) -> None:
        client = TestClient(app)
        resp = client.get('/v1/models')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['object'], 'list')
        ids = [str(item['id']) for item in body['data']]
        self.assertEqual(ids, ['free-proxy/auto'])

    def test_recommended_models_route_accepts_requested_model_query(self) -> None:
        client = TestClient(app)
        resp = client.get('/api/providers/openrouter/models/recommended', params={'model': 'my-picked-model'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['provider'], 'openrouter')
        self.assertEqual(body['items'][0], 'my-picked-model')

    def test_save_provider_key_requires_api_key(self) -> None:
        client = TestClient(app)
        resp = client.post('/api/provider-keys/openrouter', json={'api_key': ''})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('missing api_key', str(resp.json()['error']))

    def test_openai_chat_completion_accepts_model_with_provider_prefix(self) -> None:
        client = TestClient(app)
        resp = client.post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/auto', 'requested_model': 'openrouter/m1', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['object'], 'chat.completion')
        self.assertEqual(body['model'], 'openrouter/openrouter/auto:free')
        self.assertEqual(body['choices'][0]['message']['content'], 'echo:hello')
        self.assertEqual(body['choices'][0]['message']['role'], 'assistant')

    def test_openai_chat_completion_supports_auto_model_for_newbies(self) -> None:
        client = TestClient(app)
        resp = client.post(
            '/v1/chat/completions',
            json={'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp.headers.get('content-type', ''))
        self.assertIn('openrouter/openrouter/auto:free', resp.text)

    def test_openai_chat_completion_rejects_coding_alias_for_agents(self) -> None:
        client = TestClient(app)
        resp = client.post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/coding', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('application/json', resp.headers.get('content-type', ''))
        self.assertIn('model_deprecated', resp.text)

    def test_openai_chat_completion_stream_mode_returns_sse_when_requested(self) -> None:
        client = TestClient(app)
        resp = client.post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/auto', 'requested_model': 'openrouter/m1', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/event-stream', resp.headers.get('content-type', ''))
        self.assertIn('chat.completion.chunk', resp.text)
        self.assertIn('data: ', resp.text)

    def test_legacy_chat_completion_stream_mode_returns_sse(self) -> None:
        client = TestClient(app)
        resp = client.post(
            '/chat/completions',
            json={'provider': 'openrouter', 'model': 'm1', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/event-stream', resp.headers.get('content-type', ''))
        self.assertIn('data: ', resp.text)

    def test_openai_chat_completion_returns_openai_style_error_when_model_missing(self) -> None:
        client = TestClient(app)
        resp = client.post(
            '/v1/chat/completions',
            json={'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn('error', body)
        self.assertIn('missing model', str(body['error']['message']))

    def test_legacy_chat_completion_route_keeps_old_custom_shape(self) -> None:
        client = TestClient(app)
        resp = client.post(
            '/chat/completions',
            json={'provider': 'openrouter', 'model': 'm1', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(bool(body['ok']))
        self.assertEqual(body['actual_model'], 'm1')
        self.assertEqual(body['content'], 'echo:hello')

    def test_configure_openclaw_rejects_invalid_mode(self) -> None:
        client = TestClient(app)
        resp = client.post('/api/configure-openclaw', json={'mode': 'invalid'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(bool(resp.json()['success']))

    def test_configure_opencode_writes_free_proxy_provider(self) -> None:
        os.environ['OPENCODE_TEST_DIR'] = self.tmp.name
        client = TestClient(app)
        resp = client.post('/api/configure-opencode', json={})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(bool(resp.json()['success']))

        content = json.loads(Path(self.tmp.name, 'opencode.json').read_text(encoding='utf-8'))
        provider = content['provider']['free-proxy']
        self.assertEqual(provider['options']['baseURL'], 'http://127.0.0.1:8765/v1')
        self.assertEqual(sorted(provider['models'].keys()), ['auto'])

    def test_v1_models_returns_correct_structure(self) -> None:
        """Contract: GET /v1/models must return {object: 'list', data: [{id, object, owned_by}]}"""
        client = TestClient(app)
        resp = client.get('/v1/models')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['object'], 'list')
        self.assertIsInstance(body['data'], list)
        for item in body['data']:
            self.assertIn('id', item)
            self.assertIn('object', item)
            self.assertIn('owned_by', item)

    def test_v1_chat_completions_json_structure(self) -> None:
        """Contract: POST /v1/chat/completions (non-stream) must return {id, object, model, choices, usage}"""
        client = TestClient(app)
        resp = client.post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('id', body)
        self.assertIn('object', body)
        self.assertEqual(body['object'], 'chat.completion')
        self.assertIn('model', body)
        self.assertIn('choices', body)
        self.assertIsInstance(body['choices'], list)
        self.assertIn('usage', body)
        self.assertIn('message', body['choices'][0])
        self.assertIn('content', body['choices'][0]['message'])
        self.assertIn('role', body['choices'][0]['message'])

    def test_v1_chat_completions_sse_termination(self) -> None:
        """Contract: POST /v1/chat/completions (stream) must end with data: [DONE]"""
        client = TestClient(app)
        resp = client.post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/event-stream', resp.headers.get('content-type', ''))
        self.assertIn('[DONE]', resp.text)


if __name__ == '__main__':
    unittest.main()
