from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from python_scripts.config import get_provider_spec, get_provider_specs, load_dotenv


class ConfigTests(unittest.TestCase):
    def test_load_dotenv_parses_key_value_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('OPENROUTER_API_KEY="abc"\n# comment\nPORT=8765\n', encoding='utf-8')
            values = load_dotenv(path)
            self.assertEqual(values['OPENROUTER_API_KEY'], 'abc')
            self.assertEqual(values['PORT'], '8765')

    def test_load_dotenv_missing_file(self) -> None:
        values = load_dotenv(Path('/no/such/file'))
        self.assertEqual(values, {})

    def test_provider_specs_are_backed_by_catalog(self) -> None:
        specs = get_provider_specs()
        self.assertGreaterEqual(len(specs), 8)

        names = {spec.name for spec in specs}
        self.assertIn('openrouter', names)
        self.assertIn('gemini', names)

        github = get_provider_spec('github')
        self.assertEqual(github.base_url, 'https://models.github.ai/inference')
        self.assertEqual(github.api_key_env, 'GITHUB_MODELS_API_KEY')
