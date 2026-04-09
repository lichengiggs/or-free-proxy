from __future__ import annotations

import os
import unittest

from python_scripts.provider_catalog import PROVIDERS, configured_provider_names, get_model_capabilities, get_provider, list_providers


class ProviderCatalogTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop('LONGCAT_API_KEY', None)
        os.environ.pop('GEMINI_API_KEY', None)
        os.environ.pop('OFOX_API_KEY', None)

    def test_get_provider_returns_catalog_item(self) -> None:
        provider = get_provider('openrouter')
        self.assertEqual(provider.name, 'openrouter')
        self.assertEqual(provider.api_key_env, 'OPENROUTER_API_KEY')

    def test_get_provider_returns_ofox_catalog_item(self) -> None:
        provider = get_provider('ofox')
        self.assertEqual(provider.name, 'ofox')
        self.assertEqual(provider.base_url, 'https://api.ofox.ai/v1')
        self.assertEqual(provider.api_key_env, 'OFOX_API_KEY')

    def test_list_providers_keeps_declared_order(self) -> None:
        names = [item.name for item in list_providers()]
        self.assertEqual(names, [item.name for item in PROVIDERS])

    def test_configured_provider_names_reads_env_from_catalog(self) -> None:
        os.environ['LONGCAT_API_KEY'] = 'x'
        os.environ['GEMINI_API_KEY'] = 'y'
        names = configured_provider_names()
        self.assertIn('longcat', names)
        self.assertIn('gemini', names)

    def test_get_model_capabilities_returns_model_specific_overrides(self) -> None:
        provider = get_provider('longcat')
        self.assertIsInstance(provider.model_capabilities, dict)
        thinking = get_model_capabilities('longcat', 'LongCat-Flash-Thinking-2601')
        chat = get_model_capabilities('longcat', 'LongCat-Flash-Chat')
        self.assertNotEqual(thinking, chat)
        self.assertTrue(thinking['reasoning'])
        self.assertFalse(chat['reasoning'])
        self.assertEqual(thinking['default_output_tokens'], 1024)
        self.assertEqual(thinking['default_timeout_seconds'], 120)

    def test_all_providers_have_required_fields(self) -> None:
        for p in PROVIDERS:
            self.assertTrue(p.name, f'{p} missing name')
            self.assertTrue(p.base_url, f'{p} missing base_url')
            self.assertTrue(p.api_key_env, f'{p} missing api_key_env')
            self.assertTrue(p.model_hints, f'{p} missing model_hints')

    def test_thinking_model_has_long_running_flag(self) -> None:
        caps = get_model_capabilities('longcat', 'LongCat-Flash-Thinking-2601')
        self.assertTrue(caps.get('long_running'))

    def test_non_thinking_model_has_no_long_running_flag(self) -> None:
        caps = get_model_capabilities('longcat', 'LongCat-Flash-Chat')
        self.assertFalse(caps.get('long_running', False))

    def test_model_hints_returns_list(self) -> None:
        from python_scripts.provider_catalog import get_provider_model_hints
        hints = get_provider_model_hints('longcat')
        self.assertIsInstance(hints, list)
        self.assertGreater(len(hints), 0)
