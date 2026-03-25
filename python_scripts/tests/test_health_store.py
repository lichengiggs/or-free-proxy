from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_scripts import health_store


class HealthStoreTests(unittest.TestCase):
    def test_load_health_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing-health.json'
            self.assertEqual(health_store.load_health(path), {})

    def test_upsert_health_persists_provider_model_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model-health.json'
            health_store.upsert_health('openrouter', 'm1', True, path=path, now_ts=100)
            health_store.upsert_health('openrouter', 'm2', False, reason='rate_limit', path=path, now_ts=101)

            data = health_store.load_health(path)
            self.assertEqual(data['openrouter/m1']['ok'], True)
            self.assertEqual(data['openrouter/m1']['checked_at'], 100)
            self.assertEqual(data['openrouter/m2']['ok'], False)
            self.assertEqual(data['openrouter/m2']['reason'], 'rate_limit')
