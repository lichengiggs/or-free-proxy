from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_scripts.env_store import upsert_env


class EnvStoreTests(unittest.TestCase):
    def test_upsert_env_appends_when_key_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('A=1\n', encoding='utf-8')
            upsert_env(path, 'B', '2')
            self.assertEqual(path.read_text(encoding='utf-8'), 'A=1\nB=2\n')

    def test_upsert_env_replaces_existing_key_and_keeps_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('# comment\nOPENROUTER_API_KEY=old\nA=1\n', encoding='utf-8')
            upsert_env(path, 'OPENROUTER_API_KEY', 'new-key')
            self.assertEqual(
                path.read_text(encoding='utf-8'),
                '# comment\nOPENROUTER_API_KEY=new-key\nA=1\n',
            )
