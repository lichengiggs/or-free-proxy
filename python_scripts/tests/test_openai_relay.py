from __future__ import annotations

import unittest

from python_scripts.openai_relay import OpenAIRelay
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
        relay = OpenAIRelay(
            adapter_factory=lambda provider: LazyAdapter(provider, tracker),
            health_loader=lambda: {},
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

    def test_relay_preserves_upstream_sse_chunks_without_buffering(self) -> None:
        class StreamingAdapter:
            def forward_chat(self, payload: dict[str, object]):
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'text/event-stream; charset=utf-8'},
                        'body': None,
                        'stream': iter([
                            b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
                            b'data: [DONE]\n\n',
                        ]),
                        'content_type': 'text/event-stream; charset=utf-8',
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
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})
        response = relay.handle_chat(request)
        self.assertIsNotNone(response.stream_chunks)
        self.assertEqual(
            list(response.stream_chunks or []),
            [
                b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
                b'data: [DONE]\n\n',
            ],
        )
