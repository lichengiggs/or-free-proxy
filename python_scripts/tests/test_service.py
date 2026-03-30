from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

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
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({'model': payload.get('model'), 'ok': True}).encode()


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

    def test_chat_uses_trim_and_model_fallback(self) -> None:
        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.chat('openrouter', 'model-a', prompt='x' * 20000)

            self.assertTrue(result.ok)
            self.assertNotEqual(result.actual_model, 'model-a')
            self.assertEqual(transport.chat_models[0], 'model-a')
            self.assertGreaterEqual(len(transport.chat_models), 2)
            self.assertIn('...[内容已截断]...', transport.last_prompt)
            self.assertEqual(transport.max_tokens[0], 512)

    def test_probe_keeps_small_output_budget(self) -> None:
        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.probe('openrouter', 'model-a')

            self.assertTrue(result.ok)
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

    def test_public_models_exposes_auto_and_coding_aliases(self) -> None:
        service = self.make_service(FakeTransport())
        models = service.public_models()
        ids = [item['id'] for item in models]
        self.assertIn('free-proxy/auto', ids)
        self.assertIn('free-proxy/coding', ids)

    def test_resolve_openai_target_supports_public_alias(self) -> None:
        os.environ['LONGCAT_API_KEY'] = 'test-longcat'
        os.environ['GEMINI_API_KEY'] = 'test-gemini'
        service = self.make_service(FakeTransport())
        target = service.resolve_openai_target({'model': 'free-proxy/coding'})
        self.assertEqual(target, ResolvedOpenAIRequest(provider=None, model='coding', alias='coding'))

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
