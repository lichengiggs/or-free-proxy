from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DEFAULT_HEALTH_PATH = Path('data/model-health.json')


def load_health(path: Path | None = None) -> dict[str, dict[str, Any]]:
    target = path or DEFAULT_HEALTH_PATH
    if not target.exists():
        return {}
    raw = target.read_text(encoding='utf-8').strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if isinstance(data, dict):
        return data
    return {}


def save_health(data: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    target = path or DEFAULT_HEALTH_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def upsert_health(
    provider: str,
    model: str,
    ok: bool,
    reason: str | None = None,
    *,
    path: Path | None = None,
    now_ts: int | None = None,
) -> None:
    state = load_health(path)
    key = f'{provider}/{model}'
    state[key] = {
        'ok': ok,
        'reason': reason,
        'checked_at': int(time.time()) if now_ts is None else int(now_ts),
    }
    save_health(state, path)
