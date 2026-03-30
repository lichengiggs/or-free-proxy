from __future__ import annotations

import os
import unittest

from python_scripts.provider_catalog import PROVIDERS, configured_provider_names, get_provider, list_providers


class ProviderCatalogTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop('LONGCAT_API_KEY', None)
        os.environ.pop('GEMINI_API_KEY', None)

    def test_get_provider_returns_catalog_item(self) -> None:
        provider = get_provider('openrouter')
        self.assertEqual(provider.name, 'openrouter')
        self.assertEqual(provider.api_key_env, 'OPENROUTER_API_KEY')

    def test_list_providers_keeps_declared_order(self) -> None:
        names = [item.name for item in list_providers()]
        self.assertEqual(names, [item.name for item in PROVIDERS])

    def test_configured_provider_names_reads_env_from_catalog(self) -> None:
        os.environ['LONGCAT_API_KEY'] = 'x'
        os.environ['GEMINI_API_KEY'] = 'y'
        names = configured_provider_names()
        self.assertIn('longcat', names)
        self.assertIn('gemini', names)
