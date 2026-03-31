from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from python_scripts.errors import classify_error
from python_scripts.provider_adapter import ProviderAdapter
from python_scripts.provider_catalog import get_provider, list_providers
from python_scripts.provider_errors import ProviderError
from python_scripts.provider_transport import UrlLibTransport, build_url


class FakeTransport:
    def __init__(self, responses: dict[tuple[str, str], tuple[int, dict[str, str], bytes]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, str] | None, bytes | None, int]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests.append((method, url, headers, body, timeout))
        return self.responses[(method, url)]


class TimeoutTransport:
    def __init__(self) -> None:
        self.timeouts: list[int] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del method, url, headers, body
        self.timeouts.append(timeout)
        raise TimeoutError('The read operation timed out')


class StreamingTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, str] | None, bytes | None, int]] = []

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        self.requests.append((method, url, headers, body, timeout))
        return (
            200,
            {'content-type': 'text/event-stream; charset=utf-8'},
            iter([
                b'data: {"choices":[{"delta":{"reasoning_content":"think"},"index":0}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
                b'data: [DONE]\n\n',
            ]),
        )


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

        with patch('python_scripts.provider_transport.certifi.where', return_value='/tmp/test-cert.pem') as where_mock, \
             patch('python_scripts.provider_transport.ssl.create_default_context', return_value='ssl-context') as context_mock, \
             patch('python_scripts.provider_transport.urlopen', return_value=fake_response) as urlopen_mock:
            transport = UrlLibTransport()
            status, headers, body = transport.request('GET', 'https://example.com/models')

        self.assertEqual(status, 200)
        self.assertEqual(headers, {'content-type': 'application/json'})
        self.assertEqual(body, b'{}')
        where_mock.assert_called_once_with()
        context_mock.assert_called_once_with(cafile='/tmp/test-cert.pem')
        self.assertEqual(urlopen_mock.call_args.kwargs['context'], 'ssl-context')

    def test_urllib_transport_converts_timeout_to_provider_error(self) -> None:
        with patch('python_scripts.provider_transport.certifi.where', return_value='/tmp/test-cert.pem'), \
             patch('python_scripts.provider_transport.ssl.create_default_context', return_value='ssl-context'), \
             patch('python_scripts.provider_transport.urlopen', side_effect=TimeoutError('The read operation timed out')):
            transport = UrlLibTransport()
            with self.assertRaises(ProviderError) as ctx:
                transport.request('GET', 'https://example.com/models')
        self.assertIn('网络连接失败', str(ctx.exception))

    def test_openai_list_models_and_chat_text(self) -> None:
        provider = get_provider('openrouter')
        transport = FakeTransport({
            ('GET', 'https://openrouter.ai/api/v1/models'): (200, {}, json.dumps({'data': [{'id': 'openrouter/auto:free'}, {'id': 'b', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()),
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.list_models(), ['openrouter/auto:free', 'b'])
        self.assertEqual(adapter.chat_text('openrouter/auto:free', 'ok'), 'ok')

    def test_openai_chat_uses_requested_max_tokens(self) -> None:
        provider = get_provider('openrouter')
        transport = FakeTransport({
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.chat_text('a', 'hello', max_tokens=256), 'ok')

        _, _, _, body, _ = transport.requests[-1]
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.assertEqual(payload['max_tokens'], 256)

    def test_openai_stream_chat_uses_stream_request(self) -> None:
        provider = get_provider('openrouter')
        transport = StreamingTransport()
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)

        status, headers, chunks = adapter.chat_completions_stream({
            'model': 'm1',
            'messages': [{'role': 'user', 'content': 'hello'}],
            'stream': True,
        })

        self.assertEqual(status, 200)
        self.assertEqual(headers.get('content-type'), 'text/event-stream; charset=utf-8')
        self.assertEqual(
            list(chunks),
            [
                b'data: {"choices":[{"delta":{"reasoning_content":"think"},"index":0}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
                b'data: [DONE]\n\n',
            ],
        )
        self.assertEqual(transport.requests[0][0], 'POST')
        self.assertIn('/chat/completions', transport.requests[0][1])

    def test_chat_request_returns_adapter_response_object(self) -> None:
        provider = get_provider('openrouter')
        transport = FakeTransport({
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {'Content-Type': 'application/json; charset=utf-8'}, b'{"choices":[{"message":{"content":"ok"}}]}'),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        response = adapter.forward_chat({'model': 'openrouter/auto:free', 'messages': [{'role': 'user', 'content': 'hi'}]})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, 'application/json; charset=utf-8')

    def test_urllib_stream_request_yields_each_sse_event(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"reasoning_content":"think"},"index":0}]}\n')
                self.wfile.flush()
                time.sleep(0.1)
                self.wfile.write(b'\n')
                self.wfile.flush()
                time.sleep(0.1)
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n')
                self.wfile.flush()
                time.sleep(0.1)
                self.wfile.write(b'\n')
                self.wfile.flush()
                self.wfile.write(b'data: [DONE]\n')
                self.wfile.flush()
                time.sleep(0.1)
                self.wfile.write(b'\n')
                self.wfile.flush()

            def log_message(self, *args: object) -> None:
                return

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            transport = UrlLibTransport()
            status, headers, chunks = transport.stream_request('POST', f'http://127.0.0.1:{server.server_address[1]}/chat/completions', {'Content-Type': 'application/json'}, b'{}', timeout=5)

            self.assertEqual(status, 200)
            self.assertEqual(headers.get('Content-Type'), 'text/event-stream; charset=utf-8')
            self.assertEqual(
                list(chunks),
                [
                    b'data: {"choices":[{"delta":{"reasoning_content":"think"},"index":0}]}\n\n',
                    b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
                    b'data: [DONE]\n\n',
                ],
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_urllib_stream_request_stops_after_done_event_even_if_socket_stays_open(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n')
                self.wfile.flush()
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
                time.sleep(1.5)

            def log_message(self, *args: object) -> None:
                return

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started = time.time()
        try:
            transport = UrlLibTransport()
            status, headers, chunks = transport.stream_request('POST', f'http://127.0.0.1:{server.server_address[1]}/chat/completions', {'Content-Type': 'application/json'}, b'{}', timeout=5)
            items = list(chunks)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        elapsed = time.time() - started
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Type'), 'text/event-stream; charset=utf-8')
        self.assertEqual(items[-1], b'data: [DONE]\n\n')
        self.assertLess(elapsed, 1.0)

    def test_urllib_stream_request_stops_after_done_event_without_space_even_if_socket_stays_open(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(b'data:{"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n')
                self.wfile.flush()
                self.wfile.write(b'data:[DONE]\n\n')
                self.wfile.flush()
                time.sleep(1.5)

            def log_message(self, *args: object) -> None:
                return

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started = time.time()
        try:
            transport = UrlLibTransport()
            status, headers, chunks = transport.stream_request('POST', f'http://127.0.0.1:{server.server_address[1]}/chat/completions', {'Content-Type': 'application/json'}, b'{}', timeout=5)
            items = list(chunks)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        elapsed = time.time() - started
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Type'), 'text/event-stream; charset=utf-8')
        self.assertEqual(items[-1], b'data:[DONE]\n\n')
        self.assertLess(elapsed, 1.0)

    def test_openai_chat_raises_when_content_is_null(self) -> None:
        provider = get_provider('openrouter')
        transport = FakeTransport({
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': None}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        with self.assertRaises(ProviderError):
            adapter.chat_text('a', 'ok')

    def test_longcat_thinking_uses_reasoning_content_when_content_is_missing(self) -> None:
        provider = get_provider('longcat')
        transport = FakeTransport({
            ('POST', 'https://api.longcat.chat/openai/chat/completions'): (
                200,
                {},
                json.dumps({'choices': [{'message': {'role': 'assistant', 'reasoning_content': 'ok'}}]}).encode(),
            ),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.chat_text('LongCat-Flash-Thinking-2601', 'ok'), 'ok')

    def test_openrouter_only_keeps_free_or_zero_cost_models(self) -> None:
        provider = get_provider('openrouter')
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
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.list_models(), ['openrouter/auto:free', 'zero-cost'])

    def test_github_uses_preview_version(self) -> None:
        provider = get_provider('github')
        transport = FakeTransport({
            ('GET', 'https://models.github.ai/inference/models?api-version=2024-12-01-preview'): (404, {}, b'not found'),
            ('POST', 'https://models.github.ai/inference/chat/completions?api-version=2024-12-01-preview'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.list_models(), ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1-mini', 'DeepSeek-V3-0324'])
        self.assertEqual(adapter.chat_text('gpt-4o-mini', 'ok'), 'ok')

    def test_groq_model_hint_fallback_on_list_error(self) -> None:
        provider = get_provider('groq')
        transport = FakeTransport({
            ('GET', 'https://api.groq.com/openai/v1/models'): (403, {}, json.dumps({'error': {'message': 'forbidden'}}).encode()),
            ('POST', 'https://api.groq.com/openai/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.list_models(), ['llama-3.1-8b-instant', 'llama-3.3-70b-versatile'])
        self.assertEqual(adapter.chat_text('llama-3.1-8b-instant', 'ok'), 'ok')

    def test_longcat_model_hint_fallback_on_list_error(self) -> None:
        provider = get_provider('longcat')
        transport = FakeTransport({
            ('GET', 'https://api.longcat.chat/openai/models'): (404, {}, json.dumps({'error': {'message': 'not found'}}).encode()),
            ('POST', 'https://api.longcat.chat/openai/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(
            adapter.list_models(),
            ['LongCat-Flash-Lite', 'LongCat-Flash-Chat', 'LongCat-Flash-Thinking', 'LongCat-Flash-Thinking-2601'],
        )
        self.assertEqual(adapter.chat_text('LongCat-Flash-Chat', 'ok'), 'ok')

    def test_gemini_normalizes_models_and_chat_text(self) -> None:
        provider = get_provider('gemini')
        transport = FakeTransport({
            ('GET', 'https://generativelanguage.googleapis.com/v1beta/models'): (200, {}, json.dumps({'models': [{'id': 'models/gemini-2.0-flash'}]}).encode()),
            ('POST', 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'): (200, {}, json.dumps({'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.list_models(), ['gemini-2.0-flash'])
        self.assertEqual(adapter.chat_text('models/gemini-2.0-flash', 'ok'), 'ok')

    def test_gemini_excludes_image_vision_and_embedding_models(self) -> None:
        provider = get_provider('gemini')
        transport = FakeTransport({
            ('GET', 'https://generativelanguage.googleapis.com/v1beta/models'): (
                200,
                {},
                json.dumps(
                    {
                        'models': [
                            {'id': 'models/gemini-3.1-flash-lite-preview', 'supportedGenerationMethods': ['generateContent']},
                            {'id': 'models/gemini-2.0-flash-vision', 'supportedGenerationMethods': ['generateContent']},
                            {'id': 'models/imagen-3.0-generate-002', 'supportedGenerationMethods': ['predict']},
                            {'id': 'models/text-embedding-004', 'supportedGenerationMethods': ['embedContent']},
                        ]
                    }
                ).encode(),
            ),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.list_models(), ['gemini-3.1-flash-lite-preview'])

    def test_longcat_thinking_uses_longer_timeout(self) -> None:
        provider = get_provider('longcat')
        transport = TimeoutTransport()
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport, request_timeout_seconds=12)
        with self.assertRaises(ProviderError):
            adapter.chat_text('LongCat-Flash-Thinking-2601', 'ok')
        self.assertEqual(transport.timeouts[-1], 30)

    def test_longcat_thinking_chat_stream_keeps_reasoning_and_content_chunks(self) -> None:
        provider = get_provider('longcat')

        class StreamTransport(StreamingTransport):
            def stream_request(
                self,
                method: str,
                url: str,
                headers: dict[str, str] | None = None,
                body: bytes | None = None,
                timeout: int = 30,
            ) -> tuple[int, dict[str, str], object]:
                self.requests.append((method, url, headers, body, timeout))
                return 200, {'content-type': 'text/event-stream; charset=utf-8'}, iter([
                    b'data: {"choices":[{"delta":{"reasoning_content":"think"},"index":0}]}\n\n',
                    b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
                    b'data: [DONE]\n\n',
                ])

        transport = StreamTransport()
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        status, headers, chunks = adapter.chat_completions_stream({
            'model': 'LongCat-Flash-Thinking-2601',
            'messages': [{'role': 'user', 'content': 'hello'}],
            'stream': True,
        })

        self.assertEqual(status, 200)
        self.assertEqual(headers.get('content-type'), 'text/event-stream; charset=utf-8')
        self.assertEqual(
            list(chunks),
            [
                b'data: {"choices":[{"delta":{"reasoning_content":"think"},"index":0}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
                b'data: [DONE]\n\n',
            ],
        )

    def test_nvidia_model_hint_fallback_on_list_error(self) -> None:
        provider = get_provider('nvidia')
        transport = FakeTransport({
            ('GET', 'https://integrate.api.nvidia.com/v1/models'): (404, {}, json.dumps({'error': {'message': 'not found'}}).encode()),
            ('POST', 'https://integrate.api.nvidia.com/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=transport)
        self.assertEqual(adapter.list_models(), ['meta/llama-3.1-70b-instruct'])
        self.assertEqual(adapter.chat_text('meta/llama-3.1-70b-instruct', 'ok'), 'ok')

    def test_chat_completions_raw_only_allows_openai_format(self) -> None:
        provider = get_provider('gemini')
        adapter = ProviderAdapter(provider=provider, api_key='x', transport=FakeTransport({}))
        with self.assertRaises(ProviderError):
            adapter.chat_completions_raw({'model': 'gemini-2.0-flash'})

    def test_list_providers_matches_catalog(self) -> None:
        self.assertTrue(any(item.name == 'openrouter' for item in list_providers()))
