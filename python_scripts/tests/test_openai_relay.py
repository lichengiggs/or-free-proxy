from __future__ import annotations

import time
import unittest

from python_scripts.openai_relay import OpenAIRelay
from python_scripts.provider_errors import ProviderError
from python_scripts.request_normalizer import ChatRequest


class FakeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def forward_chat(self, payload: dict[str, object]):
        self.calls += 1
        if self.calls == 1:
            return type('AdapterResponse', (), {'status': 429, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"rate limit"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
        return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()


class OpenAIRelayTests(unittest.TestCase):
    def test_relay_falls_back_to_second_candidate(self) -> None:
        adapter = FakeAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter', 'longcat'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertEqual(response.status, 200)
        self.assertIsNotNone(response.body)

    def test_relay_uses_provider_listed_model_after_static_default_fails(self) -> None:
        class ProviderAwareAdapter:
            def __init__(self) -> None:
                self.payloads: list[dict[str, object]] = []
                self.list_calls: list[str] = []

            def forward_chat(self, payload: dict[str, object]):
                self.payloads.append(payload)
                model = str(payload.get('model', ''))
                if model == 'openrouter/auto:free':
                    return type('AdapterResponse', (), {'status': 402, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"insufficient credits"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-listed"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

            def list_models(self) -> list[str]:
                self.list_calls.append('called')
                return ['qwen/qwen3.6-plus-preview:free']

        adapter = ProviderAwareAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertEqual(response.status, 200)
        self.assertEqual(adapter.payloads[0]['model'], 'openrouter/auto:free')
        self.assertEqual(adapter.payloads[1]['model'], 'qwen/qwen3.6-plus-preview:free')

    def test_relay_loads_listed_models_lazily_after_provider_failure(self) -> None:
        class LazyAdapter:
            def __init__(self, provider: str, tracker: dict[str, list[str]]) -> None:
                self.provider = provider
                self.tracker = tracker

            def forward_chat(self, payload: dict[str, object]):
                self.tracker['payloads'].append(f'{self.provider}:{payload.get("model")}')
                if self.provider == 'openrouter' and payload.get('model') == 'openrouter/auto:free':
                    return type('AdapterResponse', (), {'status': 402, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"insufficient credits"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-listed"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

            def list_models(self) -> list[str]:
                self.tracker['lists'].append(self.provider)
                if self.provider == 'openrouter':
                    return ['qwen/qwen3.6-plus-preview:free']
                return ['LongCat-Flash-Lite']

        tracker = {'payloads': [], 'lists': []}
        checked_at = int(time.time())
        relay = OpenAIRelay(
            adapter_factory=lambda provider: LazyAdapter(provider, tracker),
            health_loader=lambda: {'openrouter/openrouter/auto:free': {'ok': True, 'checked_at': checked_at}},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter', 'longcat'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertEqual(response.status, 200)
        self.assertEqual(tracker['lists'], ['openrouter'])
        self.assertEqual(
            tracker['payloads'][:2],
            ['openrouter:openrouter/auto:free', 'openrouter:qwen/qwen3.6-plus-preview:free'],
        )

    def test_relay_returns_json_when_stream_is_not_requested(self) -> None:
        class StreamingAdapter:
            def forward_chat(self, payload: dict[str, object]):
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"content":"ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

            def list_models(self) -> list[str]:
                return ['qwen/qwen3.6-plus-preview:free']

        relay = OpenAIRelay(
            adapter_factory=lambda provider: StreamingAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertIsNone(response.stream_chunks)
        self.assertIsNotNone(response.body)
        self.assertEqual(response.headers['Content-Type'], 'application/json; charset=utf-8')

    def test_relay_wraps_success_as_sse_when_client_requests_stream(self) -> None:
        class JsonAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"id":"chatcmpl-test","object":"chat.completion","created":1,"model":"longcat/LongCat-Flash-Lite","choices":[{"index":0,"message":{"role":"assistant","content":"ok-stream"},"finish_reason":"stop"}],"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: JsonAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['longcat'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertIsNone(response.body)
        self.assertIsNotNone(response.stream_chunks)
        self.assertEqual(response.headers['Content-Type'], 'text/event-stream; charset=utf-8')
        chunks = list(response.stream_chunks or [])
        self.assertIn(b'chat.completion.chunk', chunks[0])
        self.assertIn(b'ok-stream', chunks[0])
        self.assertEqual(chunks[-1], b'data: [DONE]\n\n')

    def test_relay_forces_non_stream_upstream_even_when_client_requests_stream(self) -> None:
        class StreamSensitiveAdapter:
            def __init__(self) -> None:
                self.stream_values: list[bool] = []

            def forward_chat(self, payload: dict[str, object]):
                stream_value = bool(payload.get('stream'))
                self.stream_values.append(stream_value)
                if stream_value:
                    return type(
                        'AdapterResponse',
                        (),
                        {
                            'status': 200,
                            'headers': {'Content-Type': 'text/event-stream; charset=utf-8'},
                            'body': None,
                            'stream': iter([b'data: {"choices":[{"delta":{"content":"ignored"}}]}\n\n', b'data: [DONE]\n\n']),
                            'content_type': 'text/event-stream; charset=utf-8',
                        },
                    )()
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"content":"ok-non-stream"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        adapter = StreamSensitiveAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['longcat'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(adapter.stream_values, [False])
        self.assertIsNone(response.body)
        self.assertIsNotNone(response.stream_chunks)
        chunks = list(response.stream_chunks or [])
        self.assertIn(b'ok-non-stream', chunks[0])

    def test_relay_attempts_candidates_in_priority_order(self) -> None:
        calls: list[tuple[str, str]] = []

        class OrderedAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                model = str(payload.get('model', ''))
                calls.append((self.provider, model))
                if self.provider == 'longcat':
                    return type('AdapterResponse', (), {'status': 500, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"server error"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: OrderedAdapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['longcat', 'gemini', 'github'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], ('longcat', 'LongCat-Flash-Lite'))
        self.assertEqual(calls[1], ('gemini', 'gemini-3.1-flash-lite-preview'))

    def test_relay_uses_reasoning_content_when_content_is_missing(self) -> None:
        class ReasoningOnlyAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"role":"assistant","reasoning_content":"think-ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: ReasoningOnlyAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['longcat'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertIsNotNone(response.body)
        self.assertIn(b'think-ok', response.body or b'')

    def test_relay_falls_back_when_adapter_raises_provider_error(self) -> None:
        calls: list[str] = []

        class TimeoutAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                calls.append('gemini')
                raise ProviderError('网络连接失败: The read operation timed out')

        class SuccessAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                calls.append('github')
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-fallback"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: TimeoutAdapter() if provider == 'gemini' else SuccessAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['gemini', 'github'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[:2], ['gemini', 'github'])
        self.assertIn(b'ok-fallback', response.body or b'')

    def test_relay_prefers_static_auto_provider_order_over_configured_provider_order(self) -> None:
        calls: list[tuple[str, str]] = []

        class OrderedAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                model = str(payload.get('model', ''))
                calls.append((self.provider, model))
                if self.provider == 'longcat':
                    return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-longcat"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 402, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"insufficient credits"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: OrderedAdapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter', 'groq', 'longcat', 'gemini', 'github'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], ('longcat', 'LongCat-Flash-Lite'))
        self.assertIsNone(response.body)
        self.assertIsNotNone(response.stream_chunks)
        chunks = list(response.stream_chunks or [])
        self.assertIn(b'ok-longcat', chunks[0])
