from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

FREE_PROXY_PROVIDER_ID = 'free-proxy'
LEGACY_FREE_PROXY_PROVIDER_ID = 'free_proxy'
FREE_PROXY_MODEL_ID = 'auto'
FREE_PROXY_AGENT_MODEL = 'free-proxy/auto'
LEGACY_FREE_PROXY_AGENT_MODEL = 'free_proxy/auto'


def _openclaw_dir() -> Path:
    testing = os.environ.get('OPENCLAW_TEST_DIR', '').strip()
    if testing:
        return Path(testing)
    return Path.home() / '.openclaw'


def _openclaw_config_path() -> Path:
    return _openclaw_dir() / 'openclaw.json'


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _get_next_backup_path() -> Path:
    root = _openclaw_dir()
    files = [p.name for p in root.iterdir()] if root.exists() else []
    nums: list[int] = []
    for name in files:
        if not name.startswith('openclaw.bak'):
            continue
        suffix = name.removeprefix('openclaw.bak')
        if suffix.isdigit():
            nums.append(int(suffix))
    next_num = (max(nums) + 1) if nums else 1
    return root / f'openclaw.bak{next_num}'


def _ensure_root(config: dict[str, Any]) -> dict[str, Any]:
    models = config.get('models')
    if not _is_dict(models):
        models = {}
        config['models'] = models

    providers = models.get('providers')
    if not _is_dict(providers):
        providers = {}
        models['providers'] = providers

    agents = config.get('agents')
    if not _is_dict(agents):
        agents = {}
        config['agents'] = agents

    defaults = agents.get('defaults')
    if not _is_dict(defaults):
        defaults = {}
        agents['defaults'] = defaults

    allow_models = defaults.get('models')
    if not _is_dict(allow_models):
        allow_models = {}
        defaults['models'] = allow_models

    return config


def _normalize_legacy_names(config: dict[str, Any]) -> None:
    with_root = _ensure_root(config)
    providers = with_root['models']['providers']
    if LEGACY_FREE_PROXY_PROVIDER_ID in providers and FREE_PROXY_PROVIDER_ID not in providers:
        providers[FREE_PROXY_PROVIDER_ID] = providers[LEGACY_FREE_PROXY_PROVIDER_ID]
    providers.pop(LEGACY_FREE_PROXY_PROVIDER_ID, None)

    defaults = with_root['agents']['defaults']
    allow_models = defaults['models']
    if LEGACY_FREE_PROXY_AGENT_MODEL in allow_models and FREE_PROXY_AGENT_MODEL not in allow_models:
        allow_models[FREE_PROXY_AGENT_MODEL] = allow_models[LEGACY_FREE_PROXY_AGENT_MODEL]
    allow_models.pop(LEGACY_FREE_PROXY_AGENT_MODEL, None)

    current = defaults.get('model')
    if isinstance(current, str):
        defaults['model'] = FREE_PROXY_AGENT_MODEL if current == LEGACY_FREE_PROXY_AGENT_MODEL else current
        return

    if not _is_dict(current):
        return

    primary = current.get('primary')
    if isinstance(primary, str) and primary == LEGACY_FREE_PROXY_AGENT_MODEL:
        current['primary'] = FREE_PROXY_AGENT_MODEL

    fallbacks = current.get('fallbacks')
    if isinstance(fallbacks, list):
        current['fallbacks'] = [
            FREE_PROXY_AGENT_MODEL if (isinstance(item, str) and item == LEGACY_FREE_PROXY_AGENT_MODEL) else item
            for item in fallbacks
            if isinstance(item, str)
        ]


def _ensure_free_proxy_provider(config: dict[str, Any], port: int) -> None:
    with_root = _ensure_root(config)
    providers = with_root['models']['providers']
    providers[FREE_PROXY_PROVIDER_ID] = {
        'baseUrl': f'http://localhost:{port}/v1',
        'apiKey': 'any_string',
        'api': 'openai-completions',
        'models': [{'id': FREE_PROXY_MODEL_ID, 'name': FREE_PROXY_MODEL_ID}],
    }


def _ensure_agent_allowlist(config: dict[str, Any]) -> None:
    with_root = _ensure_root(config)
    allow_models = with_root['agents']['defaults']['models']
    allow_models[FREE_PROXY_AGENT_MODEL] = allow_models.get(FREE_PROXY_AGENT_MODEL, {})


def _apply_default_mode(config: dict[str, Any]) -> None:
    with_root = _ensure_root(config)
    defaults = with_root['agents']['defaults']
    model = defaults.get('model')
    if not _is_dict(model):
        defaults['model'] = {'primary': FREE_PROXY_AGENT_MODEL}
        return

    fallbacks = model.get('fallbacks')
    normalized_fallbacks = [item for item in fallbacks if isinstance(item, str)] if isinstance(fallbacks, list) else None
    next_model = dict(model)
    next_model['primary'] = FREE_PROXY_AGENT_MODEL
    if normalized_fallbacks is not None:
        next_model['fallbacks'] = normalized_fallbacks
    defaults['model'] = next_model


def _apply_fallback_mode(config: dict[str, Any]) -> None:
    with_root = _ensure_root(config)
    defaults = with_root['agents']['defaults']
    model = defaults.get('model')
    if not model:
        return

    if isinstance(model, str):
        defaults['model'] = {'primary': model, 'fallbacks': [FREE_PROXY_AGENT_MODEL]}
        return

    if not _is_dict(model):
        return

    fallbacks = model.get('fallbacks')
    existing = [item for item in fallbacks if isinstance(item, str)] if isinstance(fallbacks, list) else []
    merged = list(dict.fromkeys([*existing, FREE_PROXY_AGENT_MODEL]))
    next_model = dict(model)
    next_model['fallbacks'] = merged
    defaults['model'] = next_model


def detect_openclaw_config() -> dict[str, Any]:
    path = _openclaw_config_path()
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


def configure_openclaw_model(mode: str, *, port: int) -> dict[str, Any]:
    if mode not in {'default', 'fallback'}:
        return {'success': False, 'error': 'Invalid mode'}

    status = detect_openclaw_config()
    path = _openclaw_config_path()
    root = _openclaw_dir()

    if status['exists'] and not status['isValid']:
        return {'success': False, 'error': 'Invalid JSON'}

    existing: dict[str, Any] = {}
    if status['exists'] and status.get('content') and isinstance(status['content'], dict):
        existing = status['content']

    backup_path = _get_next_backup_path()
    if status['exists']:
        root.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
    else:
        root.mkdir(parents=True, exist_ok=True)

    new_config = json.loads(json.dumps(existing))
    _normalize_legacy_names(new_config)
    _ensure_free_proxy_provider(new_config, port)
    _ensure_agent_allowlist(new_config)
    if mode == 'default':
        _apply_default_mode(new_config)
    if mode == 'fallback':
        _apply_fallback_mode(new_config)

    path.write_text(json.dumps(new_config, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'success': True, 'backup': str(backup_path) if status['exists'] else None}


def list_backups() -> list[str]:
    root = _openclaw_dir()
    if not root.exists():
        return []

    names = []
    for entry in root.iterdir():
        name = entry.name
        if name.startswith('openclaw.bak') and name.removeprefix('openclaw.bak').isdigit():
            names.append(name)

    names.sort(key=lambda name: int(name.removeprefix('openclaw.bak') or '0'), reverse=True)
    return names


def restore_backup(backup_name: str) -> dict[str, Any]:
    root = _openclaw_dir()
    source = root / backup_name
    target = _openclaw_config_path()

    if not source.exists() or not source.is_file():
        return {'success': False, 'error': 'Backup file not found'}

    try:
        content = source.read_text(encoding='utf-8')
        json.loads(content)
    except Exception:
        return {'success': False, 'error': 'Invalid JSON'}

    root.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    return {'success': True}
