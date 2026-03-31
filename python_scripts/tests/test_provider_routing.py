from __future__ import annotations

import unittest

from python_scripts.provider_routing import CandidateTarget, build_auto_candidates, choose_candidates, resolve_alias_candidates, resolve_model_request


class ProviderRoutingTests(unittest.TestCase):
    def test_resolve_model_request_supports_public_aliases(self) -> None:
        target = resolve_model_request(
            model='free-proxy/auto',
            provider=None,
            configured=['longcat', 'gemini'],
            known_providers={'longcat', 'gemini', 'openrouter'},
        )
        self.assertEqual(target.alias, 'auto')
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
        candidates = resolve_alias_candidates('auto', configured=['longcat', 'gemini', 'openrouter'])
        self.assertEqual(candidates[:2], [('longcat', 'LongCat-Flash-Lite'), ('gemini', 'gemini-3.1-flash-lite-preview')])

    def test_auto_candidates_start_with_longcat_when_available(self) -> None:
        target = resolve_model_request(
            model='free-proxy/auto',
            provider=None,
            configured=['longcat', 'gemini', 'github'],
            known_providers={'longcat', 'gemini', 'github'},
        )
        self.assertEqual(target.alias, 'auto')

        items = build_auto_candidates(
            requested_model=target.model,
            configured=['longcat', 'gemini', 'github'],
            health={},
            now_ts=150,
            ttl_seconds=60,
        )

        self.assertGreaterEqual(len(items), 3)
        self.assertEqual(
            [(item.provider, item.model) for item in items[:3]],
            [
                ('longcat', 'LongCat-Flash-Lite'),
                ('gemini', 'gemini-3.1-flash-lite-preview'),
                ('github', 'gpt-4o-mini'),
            ],
        )

    def test_build_auto_candidates_prefers_requested_then_health_then_hints(self) -> None:
        health = {
            'longcat/LongCat-Flash-Lite': {'ok': True, 'checked_at': 120},
        }
        items = build_auto_candidates(
            requested_model='longcat/LongCat-Flash-Chat',
            configured=['longcat', 'openrouter'],
            health=health,
            now_ts=150,
            ttl_seconds=60,
        )
        self.assertEqual(
            items[:3],
            [
                CandidateTarget('longcat', 'LongCat-Flash-Chat', 'user_requested', 0),
                CandidateTarget('longcat', 'LongCat-Flash-Lite', 'health_boosted', 1),
                CandidateTarget('openrouter', 'openrouter/auto:free', 'static_fallback_order', 2),
            ],
        )

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
