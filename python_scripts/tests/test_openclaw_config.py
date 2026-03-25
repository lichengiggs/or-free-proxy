from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from python_scripts.openclaw_config import configure_openclaw_model, detect_openclaw_config, list_backups, restore_backup


class OpenClawConfigTests(unittest.TestCase):
    def test_configure_default_creates_openclaw_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get('OPENCLAW_TEST_DIR')
            os.environ['OPENCLAW_TEST_DIR'] = tmp
            try:
                result = configure_openclaw_model('default', port=8765)
                self.assertTrue(result['success'])
                self.assertIsNone(result['backup'])

                status = detect_openclaw_config()
                self.assertTrue(status['exists'])
                self.assertTrue(status['isValid'])

                content = status.get('content') or {}
                providers = content.get('models', {}).get('providers', {})
                self.assertIn('free-proxy', providers)
                self.assertEqual(providers['free-proxy']['baseUrl'], 'http://localhost:8765/v1')
            finally:
                if old is None:
                    os.environ.pop('OPENCLAW_TEST_DIR', None)
                else:
                    os.environ['OPENCLAW_TEST_DIR'] = old

    def test_restore_backup_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get('OPENCLAW_TEST_DIR')
            os.environ['OPENCLAW_TEST_DIR'] = tmp
            try:
                root = Path(tmp)
                config_path = root / 'openclaw.json'
                root.mkdir(parents=True, exist_ok=True)
                config_path.write_text(json.dumps({'agents': {'defaults': {'model': 'origin/model'}}}), encoding='utf-8')

                first = configure_openclaw_model('fallback', port=8765)
                self.assertTrue(first['success'])
                self.assertTrue(first['backup'])

                backups = list_backups()
                self.assertGreaterEqual(len(backups), 1)

                restored = restore_backup(backups[0])
                self.assertTrue(restored['success'])

                final = json.loads(config_path.read_text(encoding='utf-8'))
                self.assertEqual(final.get('agents', {}).get('defaults', {}).get('model'), 'origin/model')
            finally:
                if old is None:
                    os.environ.pop('OPENCLAW_TEST_DIR', None)
                else:
                    os.environ['OPENCLAW_TEST_DIR'] = old
