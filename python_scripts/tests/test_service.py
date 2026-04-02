from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from python_scripts.health_store import load_health
from python_scripts.provider_errors import ProviderError
from python_scripts.service import OpenAIForwardResult, ProxyService, ResolvedOpenAIRequest


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.timeouts: list[int] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, body
        self.calls.append((method, url))
        self.timeouts.append(timeout)
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'ok-model', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class GeminiTransport:
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


class FallbackTransport:
    def __init__(self) -> None:
        self.chat_models: list[str] = []
        self.last_prompt: str = ''
        self.max_tokens: list[int] = []

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
            return 200, {}, json.dumps({'data': [{'id': 'model-a', 'pricing': {'prompt': '0', 'completion': '0'}}, {'id': 'model-b', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()

        payload = json.loads((body or b'{}').decode('utf-8'))
        model = str(payload.get('model', ''))
        self.chat_models.append(model)
        self.last_prompt = str(payload.get('messages', [{}])[0].get('content', ''))
        self.max_tokens.append(int(payload.get('max_tokens', 0) or 0))

        if model == 'model-a':
            return 429, {}, json.dumps({'error': {'message': 'rate limit'}}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class StreamTransport(FallbackTransport):
    def __init__(self) -> None:
        super().__init__()
        self.stream_payloads: list[dict[str, object]] = []

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        del method, url, headers, timeout
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.stream_payloads.append(payload)
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
            b'data: [DONE]\n\n',
        ])


class VerifyTransport:
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
            return 200, {}, json.dumps({'data': [{'id': 'v-model', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class AuthFailTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del method, url, headers, body, timeout
        return 401, {}, json.dumps({'error': {'message': 'invalid api key'}}).encode()


class ListOkChatFailTransport:
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
            return 200, {}, json.dumps({'data': [{'id': 'model-can-list', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        return 429, {}, json.dumps({'error': {'message': 'rate limit'}}).encode()


class SslVerifyFailTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del method, url, headers, body, timeout
        raise ProviderError('网络连接失败: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1002)')


class TokenLimitRetryTransport:
    def __init__(self) -> None:
        self.calls = 0
        self.max_tokens: list[int] = []
        self.prompts: list[str] = []

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
            return 200, {}, json.dumps({'data': [{'id': 'model-a', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.max_tokens.append(int(payload.get('max_tokens', 0) or 0))
        self.prompts.append(str(payload.get('messages', [{}])[0].get('content', '')))
        self.calls += 1
        if self.calls == 1:
            return 400, {}, json.dumps({'error': {'message': 'maximum context length is 8192 tokens'}}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class RawTransport:
    def __init__(self) -> None:
        self.last_payload: dict[str, object] | None = None

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
            return 200, {}, json.dumps({'data': [{'id': 'model-a', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.last_payload = payload
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({'model': payload.get('model'), 'ok': True}).encode()


class ChunkedStreamTransport(RawTransport):
    def __init__(self) -> None:
        self.last_payload: dict[str, object] | None = None

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        del method, url, headers, timeout
        self.last_payload = json.loads((body or b'{}').decode('utf-8'))
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            b'data: {"choices":[{"delta":{"reasoning_content":"think-1"},"index":0}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"answer-1"},"index":0}]}\n\n',
            b'data: [DONE]\n\n',
        ])


class StreamHttpTransport:
    def __init__(self) -> None:
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
        del timeout
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode('utf-8')

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        self.requests.append((method, url, headers, body, timeout))
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            b'data: {"choices":[{"delta":{"reasoning_content":"think-1"},"index":0}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"answer-1"},"index":0}]}\n\n',
            b'data: [DONE]\n\n',
        ])


class LongcatThinkingTransport(StreamHttpTransport):
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests.append((method, url, headers, body, timeout))
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({
            'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}],
        }).encode('utf-8')


class LongcatFallbackTransport(StreamHttpTransport):
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests.append((method, url, headers, body, timeout))
        del timeout
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.last_payload = payload
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({
            'id': 'chatcmpl-test',
            'object': 'chat.completion',
            'created': 1,
            'model': 'LongCat-Flash-Thinking-2601',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'answer-1'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
        }).encode('utf-8')


class JsonFallbackStreamTransport(StreamHttpTransport):
    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        self.requests.append((method, url, headers, body, timeout))
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, iter([
            json.dumps({
                'id': 'chatcmpl-stream-json',
                'object': 'chat.completion',
                'created': 2,
                'model': 'model-a',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'answer-json'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
            }).encode('utf-8')
        ])


class ErrorBodyStreamTransport(StreamHttpTransport):
    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        self.requests.append((method, url, headers, body, timeout))
        return 401, {'Content-Type': 'application/json; charset=utf-8'}, iter([
            json.dumps({'error': {'message': 'invalid api key'}}).encode('utf-8')
        ])


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_keys = [
            'OPENROUTER_API_KEY',
            'LONGCAT_API_KEY',
            'GEMINI_API_KEY',
            'SAMBANOVA_API_KEY',
        ]
        self.old_values = {key: os.environ.get(key) for key in self.env_keys}
        os.environ['OPENROUTER_API_KEY'] = 'test'
        self.tmp = tempfile.TemporaryDirectory()
        self.health_path = Path(self.tmp.name) / 'default-health.json'
        self.token_limit_path = Path(self.tmp.name) / 'default-token-limits.json'

    def tearDown(self) -> None:
        for key, value in self.old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def make_service(
        self,
        transport: object,
        *,
        dotenv_path: Path | None = None,
        health_path: Path | None = None,
        token_limit_path: Path | None = None,
        request_timeout_seconds: int = 12,
    ) -> ProxyService:
        return ProxyService(
            transport=transport,
            dotenv_path=dotenv_path,
            health_path=self.health_path if health_path is None else health_path,
            token_limit_path=self.token_limit_path if token_limit_path is None else token_limit_path,
            request_timeout_seconds=request_timeout_seconds,
        )

    def test_probe_returns_ok(self) -> None:
        service = self.make_service(FakeTransport())
        result = service.probe('openrouter', 'ok-model')
        self.assertTrue(result.ok)
        self.assertEqual(result.content, 'ok')
        self.assertEqual(result.actual_model, 'ok-model')

    def test_request_timeout_is_propagated_to_adapter_transport(self) -> None:
        transport = FakeTransport()
        service = self.make_service(transport, request_timeout_seconds=7)
        service.probe('openrouter', 'ok-model')
        self.assertTrue(any(value == 7 for value in transport.timeouts))

    def test_chat_is_strict_for_explicit_model(self) -> None:
        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.chat('openrouter', 'model-a', prompt='x' * 20000)

            self.assertFalse(result.ok)
            self.assertEqual(result.model, 'model-a')
            self.assertEqual(result.status, 429)
            self.assertEqual(result.category, 'rate_limit')
            self.assertEqual(result.actual_model, None)
            self.assertEqual(transport.chat_models[0], 'model-a')
            self.assertIn('...[内容已截断]...', transport.last_prompt)
            self.assertEqual(transport.max_tokens[0], 512)

    def test_stream_chat_ignores_stream_and_wraps_prompt_into_messages_for_openai_payloads(self) -> None:
        transport = RawTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.forward_direct_chat('openrouter', 'model-a', {'model': 'model-a', 'prompt': 'hello', 'stream': True})

            self.assertTrue(result.ok)
            self.assertIsNone(result.stream_chunks)
            self.assertIsNotNone(result.body)
            parsed = json.loads((result.body or b'{}').decode('utf-8'))
            self.assertTrue(bool(parsed.get('ok')))
            self.assertEqual(transport.last_payload and transport.last_payload.get('stream'), False)
            self.assertEqual(transport.last_payload and transport.last_payload.get('messages'), [{'role': 'user', 'content': 'hello'}])

    def test_longcat_thinking_probe_uses_larger_output_budget(self) -> None:
        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.probe('longcat', 'LongCat-Flash-Thinking-2601')

            self.assertTrue(result.ok)
            self.assertEqual(transport.max_tokens[0], 256)

    def test_probe_keeps_small_output_budget_for_non_thinking_models(self) -> None:
        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.probe('openrouter', 'model-a')

            self.assertFalse(result.ok)
            self.assertEqual(transport.chat_models, ['model-a'])
            self.assertEqual(transport.max_tokens[0], 32)

    def test_provider_key_status_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(VerifyTransport(), dotenv_path=env_path)

            before = service.provider_key_statuses()
            self.assertFalse(before['openrouter']['configured'])
            self.assertFalse(before['longcat']['configured'])

            service.save_provider_key('openrouter', 'sk-example-123456')
            service.save_provider_key('longcat', 'lc-example-123456')
            after = service.provider_key_statuses()
            self.assertTrue(after['openrouter']['configured'])
            self.assertIn('***', after['openrouter']['masked'])
            self.assertTrue(after['longcat']['configured'])
            self.assertEqual(after['longcat']['env'], 'LONGCAT_API_KEY')

    def test_save_and_load_preferred_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preferred_path = Path(tmp) / 'preferred-model.json'
            service = ProxyService(
                transport=VerifyTransport(),
                health_path=self.health_path,
                preferred_model_path=preferred_path,
                token_limit_path=self.token_limit_path,
            )

            result = service.save_preferred_model('longcat', 'LongCat-Flash-Chat')
            self.assertTrue(result['ok'])
            self.assertEqual(service.preferred_model(), 'longcat/LongCat-Flash-Chat')

    def test_verify_provider_key_and_recommended_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(VerifyTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertTrue(verify['ok'])
            self.assertEqual(verify['provider'], 'openrouter')

            recommended = service.recommended_models('openrouter')
            self.assertTrue(len(recommended) >= 1)

    def test_verify_provider_key_returns_error_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(AuthFailTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'auth')

    def test_verify_provider_key_fails_when_model_list_ok_but_not_callable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(ListOkChatFailTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'rate_limit')
            self.assertTrue(bool(verify.get('suggestion')))

    def test_verify_provider_key_classifies_ssl_certificate_failure_as_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(SslVerifyFailTransport(), dotenv_path=env_path)
            service.save_provider_key('longcat', 'lc-example-123456')

            verify = service.verify_provider_key('longcat')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'network')
            self.assertIn('检查网络', verify['suggestion'])

    def test_public_models_exposes_auto_alias_only(self) -> None:
        service = self.make_service(FakeTransport())
        models = service.public_models()
        ids = [item['id'] for item in models]
        self.assertEqual(ids, ['free-proxy/auto'])

    def test_service_exposes_openai_relay_accessor(self) -> None:
        service = self.make_service(FakeTransport())
        relay = service.openai_relay()
        self.assertIsNotNone(relay)

    def test_execute_openai_target_returns_raw_forward_result_for_openai_provider(self) -> None:
        service = self.make_service(RawTransport())
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored'})
        self.assertEqual(
            result,
            OpenAIForwardResult(
                ok=True,
                provider='openrouter',
                model='model-a',
                status=200,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                body=b'{"model": "model-a", "ok": true}',
                content=None,
                error=None,
                category=None,
                suggestion=None,
            ),
        )

    def test_forward_direct_chat_strips_local_provider_field_before_upstream_request(self) -> None:
        transport = RawTransport()
        service = self.make_service(transport)

        result = service.forward_direct_chat(
            'openrouter',
            'model-a',
            {'provider': 'openrouter', 'model': 'model-a', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(transport.last_payload)
        self.assertNotIn('provider', transport.last_payload or {})
        self.assertEqual(transport.last_payload and transport.last_payload.get('model'), 'model-a')

    def test_forward_direct_chat_strips_duplicate_provider_prefix_from_model_before_upstream_request(self) -> None:
        transport = RawTransport()
        service = self.make_service(transport)

        result = service.forward_direct_chat(
            'openrouter',
            'openrouter/stepfun/step-3.5-flash:free',
            {
                'provider': 'openrouter',
                'model': 'openrouter/stepfun/step-3.5-flash:free',
                'messages': [{'role': 'user', 'content': 'hello'}],
            },
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(transport.last_payload)
        self.assertEqual(transport.last_payload and transport.last_payload.get('model'), 'stepfun/step-3.5-flash:free')

    def test_forward_direct_chat_persists_successful_model_health(self) -> None:
        transport = RawTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(
                transport=transport,
                health_path=Path(tmp) / 'health.json',
                token_limit_path=self.token_limit_path,
            )

            result = service.forward_direct_chat(
                'openrouter',
                'model-a',
                {'provider': 'openrouter', 'model': 'model-a', 'messages': [{'role': 'user', 'content': 'hello'}]},
            )

            self.assertTrue(result.ok)
            health = load_health(Path(tmp) / 'health.json')
            self.assertEqual(health['openrouter/model-a']['ok'], True)

    def test_execute_openai_target_ignores_stream_flag_for_openai_provider(self) -> None:
        transport = ChunkedStreamTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertIsNone(result.stream_chunks)
        self.assertEqual(transport.last_payload and transport.last_payload.get('stream'), False)
        self.assertIsNotNone(result.body)

    def test_execute_openai_target_clamps_longcat_thinking_output_budget(self) -> None:
        transport = StreamHttpTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='longcat', model='LongCat-Flash-Thinking-2601', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored', 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertEqual(len(transport.requests), 1)
        payload = transport.requests[0][3]
        self.assertIsInstance(payload, (bytes, bytearray))
        body = json.loads(bytes(payload).decode('utf-8'))
        self.assertLessEqual(int(body['max_tokens']), 1024)

    def test_execute_openai_target_ignores_stream_flag_for_longcat_thinking(self) -> None:
        transport = StreamHttpTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='longcat', model='LongCat-Flash-Thinking-2601', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertIsNone(result.stream_chunks)
        self.assertEqual(len(transport.requests), 1)
        payload = transport.requests[0][3]
        self.assertIsInstance(payload, (bytes, bytearray))
        body = json.loads(bytes(payload).decode('utf-8'))
        self.assertEqual(body['stream'], False)

    def test_execute_openai_target_uses_non_stream_transport_when_stream_requested(self) -> None:
        transport = StreamHttpTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='longcat', model='LongCat-Flash-Thinking-2601', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertIsNone(result.stream_chunks)
        self.assertEqual(len(transport.requests), 1)

    def test_execute_openai_target_uses_extended_timeout_for_longcat_thinking(self) -> None:
        transport = LongcatThinkingTransport()
        service = self.make_service(transport, request_timeout_seconds=12)
        target = ResolvedOpenAIRequest(provider='longcat', model='LongCat-Flash-Thinking-2601', alias=None)

        result = service.execute_openai_target(target, {'model': 'ignored', 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertEqual(len(transport.requests), 1)
        self.assertGreaterEqual(transport.requests[0][4], 60)

    def test_execute_openai_target_ignores_stream_flag_for_non_openai_provider(self) -> None:
        transport = GeminiTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='gemini', model='gemini-2.0-flash', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertIsNone(result.stream_chunks)
        self.assertEqual(result.content, 'gemini-ok')

    def test_chat_retries_once_after_token_limit_and_persists_learned_limit(self) -> None:
        transport = TokenLimitRetryTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(
                transport=transport,
                health_path=Path(tmp) / 'health.json',
                token_limit_path=Path(tmp) / 'token-limits.json',
            )
            result = service.chat('openrouter', 'model-a', prompt='x' * 60000, max_output_tokens=4096)

            self.assertTrue(result.ok)
            self.assertEqual(transport.calls, 2)
            self.assertLess(transport.max_tokens[-1], transport.max_tokens[0])
            token_limits = json.loads((Path(tmp) / 'token-limits.json').read_text(encoding='utf-8'))
            self.assertEqual(token_limits['openrouter/model-a']['input_tokens_limit'], 8192)

    def test_provider_adapter_logs_upstream_request_and_response_safely(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []

        def debug_log(event: str, **fields: object) -> None:
            logs.append((event, fields))

        transport = RawTransport()
        service = ProxyService(transport=transport, debug_log=debug_log)
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        service.execute_openai_target(target, {'model': 'model-a', 'messages': [{'role': 'user', 'content': 'hello'}]})

        events = [event for event, _ in logs]
        self.assertIn('upstream_request', events)
        self.assertIn('upstream_response', events)
        first = logs[0][1]
        self.assertEqual(first['auth_present'], True)
        self.assertEqual(first['auth_scheme'], 'Bearer')
        self.assertNotIn('Authorization', str(logs))
        self.assertNotIn('hello', str(logs))

    def test_execute_openai_target_logs_missing_provider_as_request_failure(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []

        def debug_log(event: str, **fields: object) -> None:
            logs.append((event, fields))

        class FailTransport(RawTransport):
            def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
                del method, headers, body, timeout
                return 403, {'cf-ray': 'ray-1'}, b'{"error":{"message":"error code: 1010"}}'

        service = ProxyService(transport=FailTransport(), debug_log=debug_log)
        result = service.execute_openai_target(ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None), {'model': 'model-a'})

        self.assertFalse(result.ok)
        self.assertTrue(any(event == 'request_failed' for event, _ in logs))

    def test_forward_direct_chat_keeps_upstream_error_body_for_stream_failures(self) -> None:
        os.environ['LONGCAT_API_KEY'] = 'test'
        service = self.make_service(ErrorBodyStreamTransport())

        result = service.forward_direct_chat(
            'longcat',
            'LongCat-Flash-Chat',
            {'provider': 'longcat', 'model': 'LongCat-Flash-Chat', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]},
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, 401)
        self.assertEqual(result.category, 'auth')
        self.assertIn('invalid api key', result.error or '')
