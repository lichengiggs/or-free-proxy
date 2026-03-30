from __future__ import annotations

import unittest

from python_scripts.provider_routing import choose_candidates, resolve_alias_candidates, resolve_model_request


class ProviderRoutingTests(unittest.TestCase):
    def test_resolve_model_request_supports_public_aliases(self) -> None:
        target = resolve_model_request(
            model='free-proxy/coding',
            provider=None,
            configured=['longcat', 'gemini'],
            known_providers={'longcat', 'gemini', 'openrouter'},
        )
        self.assertEqual(target.alias, 'coding')
        self.assertIsNone(target.provider)

    def test_resolve_model_request_supports_provider_prefixed_model(self) -> None:
        target = resolve_model_request(
            model='openrouter/m1',
            provider=None,
            configured=['openrouter'],
            known_providers={'openrouter'},
        )
        self.assertEqual(target.provider, 'openrouter')
        self.assertEqual(target.model, 'm1')

    def test_resolve_alias_candidates_keeps_declared_priority(self) -> None:
        candidates = resolve_alias_candidates('coding', configured=['longcat', 'gemini', 'openrouter'])
        self.assertEqual(candidates[:2], [('longcat', 'LongCat-Flash-Lite'), ('gemini', 'gemini-3.1-flash-lite-preview')])

    def test_choose_candidates_prefers_requested_then_healthy_then_hints(self) -> None:
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
