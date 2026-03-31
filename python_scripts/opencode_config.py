from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


FREE_PROXY_PROVIDER_ID = 'free-proxy'
LEGACY_FREE_PROXY_PROVIDER_ID = 'free_proxy'


def _opencode_dir() -> Path:
    testing = os.environ.get('OPENCODE_TEST_DIR', '').strip()
    if testing:
        return Path(testing)
    return Path.home() / '.config' / 'opencode'


def _opencode_config_path() -> Path:
    return _opencode_dir() / 'opencode.json'


def _migration_log_path() -> Path:
    return _opencode_dir() / 'migration.log'


def _get_next_backup_path() -> Path:
    root = _opencode_dir()
    files = [p.name for p in root.iterdir()] if root.exists() else []
    nums: list[int] = []
    for name in files:
        if not name.startswith('opencode.json.bak'):
            continue
        suffix = name.removeprefix('opencode.json.bak')
        if suffix.isdigit():
            nums.append(int(suffix))
    next_num = (max(nums) + 1) if nums else 1
    return root / f'opencode.json.bak{next_num}'


def detect_opencode_config() -> dict[str, Any]:
    path = _opencode_config_path()
    result: dict[str, Any] = {'exists': False, 'isValid': False, 'path': str(path)}
    if not path.exists():
        return result

    result['exists'] = True
    try:
        result['content'] = json.loads(path.read_text(encoding='utf-8'))
        result['isValid'] = True
    except Exception:
        result['isValid'] = False
    return result


def configure_opencode_provider(*, port: int) -> dict[str, Any]:
    status = detect_opencode_config()
    path = _opencode_config_path()
    root = _opencode_dir()

    if status['exists'] and not status['isValid']:
        return {'success': False, 'error': 'Invalid JSON'}

    existing: dict[str, Any] = {}
    if status['exists'] and isinstance(status.get('content'), dict):
        existing = status['content']

    backup_path = _get_next_backup_path()
    root.mkdir(parents=True, exist_ok=True)
    if status['exists']:
        backup_path.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')

    new_config = json.loads(json.dumps(existing))
    provider_map = new_config.get('provider')
    if not isinstance(provider_map, dict):
        provider_map = {}
        new_config['provider'] = provider_map

    legacy = provider_map.get(LEGACY_FREE_PROXY_PROVIDER_ID)
    if isinstance(legacy, dict) and FREE_PROXY_PROVIDER_ID not in provider_map:
        provider_map[FREE_PROXY_PROVIDER_ID] = legacy
    provider_map.pop(LEGACY_FREE_PROXY_PROVIDER_ID, None)

    current = provider_map.get(FREE_PROXY_PROVIDER_ID)
    migrated = False
    if isinstance(current, dict):
        models = current.get('models')
        if isinstance(models, dict) and 'coding' in models:
            models.pop('coding', None)
            migrated = True

    provider_map[FREE_PROXY_PROVIDER_ID] = {
        'name': FREE_PROXY_PROVIDER_ID,
        'options': {
            'baseURL': f'http://localhost:{port}/v1',
            'apiKey': 'sk-not-needed',
            'api': 'openai-completions',
        },
        'models': {
            'auto': {'name': 'auto'},
        },
    }

    path.write_text(json.dumps(new_config, indent=2, ensure_ascii=False), encoding='utf-8')
    if migrated:
        _migration_log_path().write_text('[DEPRECATED] free-proxy/coding is removed, migrating to free-proxy/auto\n', encoding='utf-8')
    return {'success': True, 'backup': str(backup_path) if status['exists'] else None}
