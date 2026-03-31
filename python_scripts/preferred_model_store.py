from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


DEFAULT_PREFERRED_MODEL_PATH = Path('data/preferred-model.json')
PreferredModelState = dict[str, object]


def _clone_state(data: PreferredModelState) -> PreferredModelState:
    return deepcopy(data)


def load_preferred_model(path: Path | None = None) -> str | None:
    target = path or DEFAULT_PREFERRED_MODEL_PATH
    if not target.exists():
        return None
    raw = target.read_text(encoding='utf-8').strip()
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    provider = str(data.get('provider', '')).strip()
    model = str(data.get('model', '')).strip()
    if not provider or not model:
        return None
    return f'{provider}/{model}'


def save_preferred_model(provider: str, model: str, path: Path | None = None) -> None:
    target = path or DEFAULT_PREFERRED_MODEL_PATH
    state: PreferredModelState = _clone_state(
        {
            'provider': provider.strip(),
            'model': model.strip(),
        }
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
