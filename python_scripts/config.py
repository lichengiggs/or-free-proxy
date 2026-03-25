from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .provider_catalog import PROVIDER_MAP, PROVIDERS, ProviderMeta


ROOT_DIR = Path(__file__).resolve().parents[1]
DOTENV_PATH = ROOT_DIR / '.env'

ProviderSpec = ProviderMeta
PROVIDER_SPECS: tuple[ProviderSpec, ...] = PROVIDERS


def load_dotenv(path: Path = DOTENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def hydrate_env(path: Path = DOTENV_PATH, *, overwrite: bool = False) -> dict[str, str]:
    values = load_dotenv(path)
    for key, value in values.items():
        if overwrite or key not in os.environ:
            os.environ[key] = value
    return values


def get_provider_specs() -> tuple[ProviderSpec, ...]:
    return PROVIDER_SPECS


def get_provider_spec(name: str) -> ProviderSpec:
    spec = PROVIDER_MAP.get(name)
    if spec is None:
        raise KeyError(f'unknown provider: {name}')
    return spec


def configured_provider_names(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    return [spec.name for spec in PROVIDER_SPECS if source.get(spec.api_key_env)]


def iter_provider_specs(names: Iterable[str] | None = None) -> list[ProviderSpec]:
    if names is None:
        return list(PROVIDER_SPECS)
    wanted = set(names)
    return [spec for spec in PROVIDER_SPECS if spec.name in wanted]


def get_provider_model_hints(name: str) -> list[str]:
    return list(get_provider_spec(name).model_hints)


def get_probe_model_candidates(name: str, requested_model: str | None = None) -> list[str]:
    candidates: list[str] = []
    if requested_model:
        candidates.append(requested_model)
    for model_id in get_provider_model_hints(name):
        if model_id not in candidates:
            candidates.append(model_id)
    return candidates


def get_provider_required_query(name: str) -> dict[str, str]:
    return dict(get_provider_spec(name).required_query)
