from __future__ import annotations

import io
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

from python_scripts.cli import build_parser
from python_scripts.server import ApiHandler
from python_scripts.service import OpenAIForwardResult, ProxyService


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
        self._old_service = ApiHandler.service
        self._old_openclaw_test_dir = os.environ.get('OPENCLAW_TEST_DIR')
        self._old_opencode_test_dir = os.environ.get('OPENCODE_TEST_DIR')
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['OPENCLAW_TEST_DIR'] = self.tmp.name
        ApiHandler.service = FakeService()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), ApiHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        ApiHandler.service = self._old_service
        if self._old_openclaw_test_dir is None:
            os.environ.pop('OPENCLAW_TEST_DIR', None)
        else:
            os.environ['OPENCLAW_TEST_DIR'] = self._old_openclaw_test_dir
        if self._old_opencode_test_dir is None:
            os.environ.pop('OPENCODE_TEST_DIR', None)
        else:
            os.environ['OPENCODE_TEST_DIR'] = self._old_opencode_test_dir
        self.tmp.cleanup()

    def _request(self, method: str, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        body = b''
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode('utf-8')
        conn.close()
        return resp.status, json.loads(data) if data else {}

    def _request_raw(self, method: str, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, str], str]:
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        body = b''
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        resp_headers = {key.lower(): value for key, value in resp.getheaders()}
        data = resp.read().decode('utf-8')
        conn.close()
        return status, resp_headers, data

    def _request_raw_prefix(self, method: str, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, str], str]:
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        body = b''
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        resp_headers = {key.lower(): value for key, value in resp.getheaders()}
        parts: list[str] = []
        for _ in range(4):
            line = resp.readline().decode('utf-8', errors='ignore')
            if not line:
                break
            parts.append(line)
        data = ''.join(parts)
        conn.close()
        return status, resp_headers, data

    def test_index_page_uses_new_validation_flow_and_updated_examples(self) -> None:
        status, headers, body = self._request_raw('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers.get('content-type', ''))
        self.assertIn('free-proxy 控制台', body)
        self.assertIn('3. 模型验证', body)
        self.assertIn('探测模型', body)
        self.assertIn('http://127.0.0.1:8765/v1', body)

    def test_serve_parser_accepts_debug_flag(self) -> None:
        args = build_parser().parse_args(['serve', '--debug'])
        self.assertEqual(args.command, 'serve')
        self.assertTrue(args.debug)

    def test_debug_mode_logs_request_and_route(self) -> None:
        old_debug_enabled = getattr(ApiHandler, 'debug_enabled', False)
        ApiHandler.debug_enabled = True
        buffer = io.StringIO()
        try:
            with redirect_stderr(buffer):
                status, body = self._request(
                    'POST',
                    '/v1/chat/completions',
                    {'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'hello'}]},
                )
        finally:
            ApiHandler.debug_enabled = old_debug_enabled

        self.assertEqual(status, 200)
        output = buffer.getvalue()
        self.assertIn('event=request_received', output)
        self.assertIn('event=route_resolved', output)
        self.assertIn('requested_model=free-proxy/auto', output)
        self.assertNotIn('hello', output)

    def test_health_route(self) -> None:
        status, body = self._request('GET', '/health')
        self.assertEqual(status, 200)
        self.assertEqual(body, {'ok': True})

    def test_provider_keys_status_route(self) -> None:
        status, body = self._request('GET', '/api/provider-keys')
        self.assertEqual(status, 200)
        self.assertTrue(bool(body['openrouter']['configured']))

    def test_preferred_model_route_returns_current_selection(self) -> None:
        status, body = self._request('GET', '/api/preferred-model')
        self.assertEqual(status, 200)
        self.assertEqual(body['requested_model'], 'openrouter/m1')

    def test_preferred_model_route_persists_selection(self) -> None:
        status, body = self._request('POST', '/api/preferred-model', {'provider': 'openrouter', 'model': 'm2'})
        self.assertEqual(status, 200)
        self.assertEqual(body['requested_model'], 'openrouter/m2')

    def test_openai_models_route_returns_public_aliases(self) -> None:
        status, body = self._request('GET', '/v1/models')
        self.assertEqual(status, 200)
        self.assertEqual(body['object'], 'list')
        ids = [str(item['id']) for item in body['data']]
        self.assertEqual(ids, ['free-proxy/auto'])

    def test_recommended_models_route_accepts_requested_model_query(self) -> None:
        status, body = self._request('GET', '/api/providers/openrouter/models/recommended?model=my-picked-model')
        self.assertEqual(status, 200)
        self.assertEqual(body['provider'], 'openrouter')
        self.assertEqual(body['items'][0], 'my-picked-model')

    def test_save_provider_key_requires_api_key(self) -> None:
        status, body = self._request('POST', '/api/provider-keys/openrouter', {'api_key': ''})
        self.assertEqual(status, 400)
        self.assertIn('missing api_key', str(body['error']))

    def test_openai_chat_completion_accepts_model_with_provider_prefix(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'model': 'free-proxy/auto', 'requested_model': 'openrouter/m1', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body['object'], 'chat.completion')
        self.assertEqual(body['model'], 'openrouter/openrouter/auto:free')
        self.assertEqual(body['choices'][0]['message']['content'], 'echo:hello')
        self.assertEqual(body['choices'][0]['message']['role'], 'assistant')

    def test_openai_chat_completion_supports_auto_model_for_newbies(self) -> None:
        status, headers, body = self._request_raw(
            'POST',
            '/v1/chat/completions',
            {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertIn('application/json', headers.get('content-type', ''))
        self.assertIn('openrouter/openrouter/auto:free', body)

    def test_openai_chat_completion_rejects_coding_alias_for_agents(self) -> None:
        status, headers, body = self._request_raw(
            'POST',
            '/v1/chat/completions',
            {'model': 'free-proxy/coding', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 400)
        self.assertIn('application/json', headers.get('content-type', ''))
        self.assertIn('model_deprecated', body)

    def test_openai_chat_completion_stream_mode_returns_sse_when_requested(self) -> None:
        status, headers, body = self._request_raw_prefix(
            'POST',
            '/v1/chat/completions',
            {'model': 'free-proxy/auto', 'requested_model': 'openrouter/m1', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )
        self.assertEqual(status, 200)
        self.assertIn('text/event-stream', headers.get('content-type', ''))
        self.assertIn('chat.completion.chunk', body)
        self.assertIn('data: ', body)

    def test_legacy_chat_completion_stream_mode_returns_sse(self) -> None:
        status, headers, body = self._request_raw_prefix(
            'POST',
            '/chat/completions',
            {'provider': 'openrouter', 'model': 'm1', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )
        self.assertEqual(status, 200)
        self.assertIn('text/event-stream', headers.get('content-type', ''))
        self.assertIn('data: ', body)

    def test_legacy_chat_completion_stream_mode_wraps_json_fallback_as_json(self) -> None:
        old_service = ApiHandler.service
        old_longcat_key = os.environ.get('LONGCAT_API_KEY')

        class LongcatJsonTransport:
            def stream_request(
                self,
                method: str,
                url: str,
                headers: dict[str, str] | None = None,
                body: bytes | None = None,
                timeout: int = 30,
            ) -> tuple[int, dict[str, str], object]:
                del headers, body, timeout
                if method == 'GET' and url.endswith('/models'):
                    return 200, {}, iter([])
                return 200, {'Content-Type': 'application/json; charset=utf-8'}, iter([
                    json.dumps({
                        'id': 'chatcmpl-test',
                        'object': 'chat.completion',
                        'created': 1,
                        'model': 'LongCat-Flash-Thinking-2601',
                        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'answer-1'}, 'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                    }).encode('utf-8')
                ])

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
                    return 200, {}, json.dumps({'data': [{'id': 'LongCat-Flash-Thinking-2601'}]}).encode('utf-8')
                return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({
                    'id': 'chatcmpl-test',
                    'object': 'chat.completion',
                    'created': 1,
                    'model': 'LongCat-Flash-Thinking-2601',
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'answer-1'}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                }).encode('utf-8')

        tmp = tempfile.TemporaryDirectory()
        try:
            os.environ['LONGCAT_API_KEY'] = 'test-longcat'
            ApiHandler.service = ProxyService(
                transport=LongcatJsonTransport(),
                health_path=Path(tmp.name) / 'health.json',
                token_limit_path=Path(tmp.name) / 'token-limits.json',
            )
            status, headers, body = self._request_raw(
                'POST',
                '/chat/completions',
                {'provider': 'longcat', 'model': 'LongCat-Flash-Thinking-2601', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
            )
        finally:
            ApiHandler.service = old_service
            if old_longcat_key is None:
                os.environ.pop('LONGCAT_API_KEY', None)
            else:
                os.environ['LONGCAT_API_KEY'] = old_longcat_key
            tmp.cleanup()

        self.assertEqual(status, 200)
        self.assertIn('application/json', headers.get('content-type', ''))
        self.assertIn('answer-1', body)

    def test_legacy_chat_completion_stream_mode_wraps_non_openai_provider_as_json(self) -> None:
        old_service = ApiHandler.service
        old_gemini_key = os.environ.get('GEMINI_API_KEY')

        class GeminiTransport:
            def stream_request(
                self,
                method: str,
                url: str,
                headers: dict[str, str] | None = None,
                body: bytes | None = None,
                timeout: int = 30,
            ) -> tuple[int, dict[str, str], object]:
                del headers, body, timeout
                if method == 'GET' and url.endswith('/models'):
                    return 200, {}, iter([])
                return 200, {'Content-Type': 'application/json; charset=utf-8'}, iter([
                    json.dumps({'candidates': [{'content': {'parts': [{'text': 'gemini-ok'}]}}]}).encode('utf-8')
                ])

            def request(
                self,
                method: str,
                url: str,
                headers: dict[str, str] | None = None,
                body: bytes | None = None,
                timeout: int = 30,
            ) -> tuple[int, dict[str, str], bytes]:
                del headers, body, timeout
                if method == 'GET' and url.endswith('/models'):
                    return 200, {}, json.dumps({'models': [{'id': 'models/gemini-2.0-flash'}]}).encode('utf-8')
                return 200, {}, json.dumps({'candidates': [{'content': {'parts': [{'text': 'gemini-ok'}]}}]}).encode('utf-8')

        tmp = tempfile.TemporaryDirectory()
        try:
            os.environ['GEMINI_API_KEY'] = 'test-gemini'
            ApiHandler.service = ProxyService(
                transport=GeminiTransport(),
                health_path=Path(tmp.name) / 'health.json',
                token_limit_path=Path(tmp.name) / 'token-limits.json',
            )
            status, headers, body = self._request_raw(
                'POST',
                '/chat/completions',
                {'provider': 'gemini', 'model': 'gemini-2.0-flash', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
            )
        finally:
            ApiHandler.service = old_service
            if old_gemini_key is None:
                os.environ.pop('GEMINI_API_KEY', None)
            else:
                os.environ['GEMINI_API_KEY'] = old_gemini_key
            tmp.cleanup()

        self.assertEqual(status, 200)
        self.assertIn('application/json', headers.get('content-type', ''))
        self.assertIn('gemini-ok', body)

    def test_openai_chat_completion_wraps_gemini_text_result(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'model': 'free-proxy/auto', 'requested_model': 'gemini/gemini-2.0-flash', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body['model'], 'openrouter/openrouter/auto:free')
        self.assertEqual(body['choices'][0]['message']['content'], 'echo:hello')

    def test_openai_chat_completion_returns_openai_style_error_when_model_missing(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 400)
        self.assertIn('error', body)
        self.assertIn('missing model', str(body['error']['message']))

    def test_legacy_chat_completion_route_keeps_old_custom_shape(self) -> None:
        status, body = self._request(
            'POST',
            '/chat/completions',
            {'provider': 'openrouter', 'model': 'm1', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertTrue(bool(body['ok']))
        self.assertEqual(body['actual_model'], 'm1')
        self.assertEqual(body['content'], 'echo:hello')

    def test_configure_openclaw_rejects_invalid_mode(self) -> None:
        status, body = self._request('POST', '/api/configure-openclaw', {'mode': 'invalid'})
        self.assertEqual(status, 400)
        self.assertFalse(bool(body['success']))

    def test_configure_opencode_writes_free_proxy_provider(self) -> None:
        os.environ['OPENCODE_TEST_DIR'] = self.tmp.name
        status, body = self._request('POST', '/api/configure-opencode', {})
        self.assertEqual(status, 200)
        self.assertTrue(bool(body['success']))

        content = json.loads(Path(self.tmp.name, 'opencode.json').read_text(encoding='utf-8'))
        provider = content['provider']['free-proxy']
        self.assertEqual(provider['options']['baseURL'], 'http://127.0.0.1:8765/v1')
        self.assertEqual(sorted(provider['models'].keys()), ['auto'])


if __name__ == '__main__':
    unittest.main()
