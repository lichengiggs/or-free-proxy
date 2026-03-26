from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from python_scripts.client import ProviderError
from python_scripts.service import ProxyService, choose_candidates


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.timeouts: list[int] = []

    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        self.calls.append((method, url))
        self.timeouts.append(timeout)
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'ok-model'}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class FallbackTransport:
    def __init__(self) -> None:
        self.chat_models: list[str] = []
        self.last_prompt: str = ''
        self.max_tokens: list[int] = []

    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'model-a'}, {'id': 'model-b'}]}).encode()

        payload = json.loads((body or b'{}').decode('utf-8'))
        model = payload.get('model', '')
        self.chat_models.append(model)
        self.last_prompt = payload.get('messages', [{}])[0].get('content', '')
        self.max_tokens.append(int(payload.get('max_tokens', 0) or 0))

        if model == 'model-a':
            return 429, {}, json.dumps({'error': {'message': 'rate limit'}}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class VerifyTransport:
    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'v-model'}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class AuthFailTransport:
    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        if url.endswith('/models'):
            return 401, {}, json.dumps({'error': {'message': 'invalid api key'}}).encode()
        return 401, {}, json.dumps({'error': {'message': 'invalid api key'}}).encode()


class ListOkChatFailTransport:
    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'model-can-list'}]}).encode()
        return 429, {}, json.dumps({'error': {'message': 'rate limit'}}).encode()


class SslVerifyFailTransport:
    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        raise ProviderError('网络连接失败: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1002)')


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get('OPENROUTER_API_KEY')
        os.environ['OPENROUTER_API_KEY'] = 'test'

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop('OPENROUTER_API_KEY', None)
        else:
            os.environ['OPENROUTER_API_KEY'] = self._old

    def test_probe_returns_ok(self) -> None:
        service = ProxyService(transport=FakeTransport())
        result = service.probe('openrouter', 'ok-model')
        self.assertTrue(result.ok)
        self.assertEqual(result.content, 'ok')
        self.assertEqual(result.actual_model, 'ok-model')

    def test_request_timeout_is_propagated_to_client_transport(self) -> None:
        transport = FakeTransport()
        service = ProxyService(transport=transport, request_timeout_seconds=7)
        service.probe('openrouter', 'ok-model')
        self.assertTrue(any(value == 7 for value in transport.timeouts))

    def test_choose_candidates_prefers_recent_healthy_then_hints(self) -> None:
        health = {
            'openrouter/model-ok': {'ok': True, 'checked_at': 100},
            'openrouter/model-old': {'ok': True, 'checked_at': 1},
            'openrouter/model-bad': {'ok': False, 'checked_at': 100},
        }
        candidates = choose_candidates(
            provider='openrouter',
            requested_model='requested-model',
            health=health,
            hints=['model-ok', 'hint-model'],
            now_ts=120,
            ttl_seconds=30,
        )
        self.assertEqual(candidates[0], 'requested-model')
        self.assertEqual(candidates[1], 'model-ok')
        self.assertIn('hint-model', candidates)
        self.assertNotIn('model-old', candidates)

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
            service = ProxyService(transport=VerifyTransport(), dotenv_path=env_path)

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
            service = ProxyService(transport=VerifyTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertTrue(verify['ok'])
            self.assertEqual(verify['provider'], 'openrouter')

            recommended = service.recommended_models('openrouter')
            self.assertTrue(len(recommended) >= 1)

    def test_verify_provider_key_returns_error_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = ProxyService(transport=AuthFailTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'auth')

    def test_verify_provider_key_fails_when_model_list_ok_but_not_callable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = ProxyService(transport=ListOkChatFailTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'rate_limit')
            self.assertTrue(bool(verify.get('suggestion')))

    def test_verify_provider_key_classifies_ssl_certificate_failure_as_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = ProxyService(transport=SslVerifyFailTransport(), dotenv_path=env_path)
            service.save_provider_key('longcat', 'lc-example-123456')

            verify = service.verify_provider_key('longcat')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'network')
            self.assertIn('检查网络', verify['suggestion'])

    def test_public_models_exposes_auto_and_coding_aliases(self) -> None:
        service = ProxyService(transport=FakeTransport())
        models = service.public_models()
        ids = [item['id'] for item in models]
        self.assertIn('free-proxy/auto', ids)
        self.assertIn('free-proxy/coding', ids)

    def test_resolve_alias_candidates_prefers_opencode_for_coding(self) -> None:
        old_openrouter = os.environ.get('OPENROUTER_API_KEY')
        old_opencode = os.environ.get('OPENCODE_API_KEY')
        os.environ['OPENROUTER_API_KEY'] = 'test-openrouter'
        os.environ['OPENCODE_API_KEY'] = 'test-opencode'
        try:
            service = ProxyService(transport=FakeTransport())
            candidates = service.resolve_alias_candidates('coding')
            self.assertGreaterEqual(len(candidates), 2)
            self.assertEqual(candidates[0][0], 'opencode')
            self.assertEqual(candidates[0][1], 'auto')
            self.assertIn(('openrouter', 'openrouter/auto:free'), candidates)
        finally:
            if old_openrouter is None:
                os.environ.pop('OPENROUTER_API_KEY', None)
            else:
                os.environ['OPENROUTER_API_KEY'] = old_openrouter
            if old_opencode is None:
                os.environ.pop('OPENCODE_API_KEY', None)
            else:
                os.environ['OPENCODE_API_KEY'] = old_opencode
