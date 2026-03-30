from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AliasName = Literal['auto', 'coding']
HealthState = dict[str, dict[str, object]]

PUBLIC_MODEL_ALIASES: tuple[dict[str, str], ...] = (
    {'id': 'free-proxy/auto', 'object': 'model', 'owned_by': 'free-proxy'},
    {'id': 'free-proxy/coding', 'object': 'model', 'owned_by': 'free-proxy'},
)

ALIAS_PROVIDER_ORDER: dict[AliasName, tuple[tuple[str, str], ...]] = {
    'auto': (
        ('longcat', 'LongCat-Flash-Lite'),
        ('gemini', 'gemini-3.1-flash-lite-preview'),
        ('github', 'gpt-4o-mini'),
        ('mistral', 'mistral-large-latest'),
        ('sambanova', 'DeepSeek-V3.1-Terminus'),
        ('openrouter', 'openrouter/auto:free'),
        ('groq', 'llama-3.3-70b-versatile'),
        ('nvidia', 'meta/llama-3.1-70b-instruct'),
    ),
    'coding': (
        ('longcat', 'LongCat-Flash-Lite'),
        ('gemini', 'gemini-3.1-flash-lite-preview'),
        ('github', 'gpt-4o'),
        ('mistral', 'mistral-large-latest'),
        ('sambanova', 'DeepSeek-V3.1-Terminus'),
        ('openrouter', 'openrouter/auto:free'),
        ('groq', 'llama-3.3-70b-versatile'),
        ('nvidia', 'meta/llama-3.1-70b-instruct'),
    ),
}


@dataclass(frozen=True)
class ResolvedModelRequest:
    provider: str | None
    model: str
    alias: AliasName | None


def resolve_model_request(
    *,
    model: str,
    provider: str | None,
    configured: list[str],
    known_providers: set[str],
) -> ResolvedModelRequest:
    normalized_provider = (provider or '').strip() or None
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError('missing model')

    if normalized_provider is not None:
        return ResolvedModelRequest(provider=normalized_provider, model=normalized_model, alias=None)

    if normalized_model in {'auto', 'free-proxy/auto', 'free_proxy/auto'}:
        return ResolvedModelRequest(provider=None, model='auto', alias='auto')
    if normalized_model in {'coding', 'free-proxy/coding', 'free_proxy/coding'}:
        return ResolvedModelRequest(provider=None, model='coding', alias='coding')

    if '/' in normalized_model:
        maybe_provider, maybe_model = normalized_model.split('/', 1)
        if maybe_provider in known_providers and maybe_model:
            return ResolvedModelRequest(provider=maybe_provider, model=maybe_model, alias=None)

    if configured:
        return ResolvedModelRequest(provider=configured[0], model=normalized_model, alias=None)

    raise ValueError('no configured providers found, please save at least one API key first')


def resolve_alias_candidates(alias: AliasName, configured: list[str]) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    for provider_name, model_id in ALIAS_PROVIDER_ORDER[alias]:
        if provider_name not in configured:
            continue
        pair = (provider_name, model_id)
        if pair not in ordered:
            ordered.append(pair)
    return ordered


def choose_candidates(
    *,
    provider: str,
    requested_model: str | None,
    health: HealthState,
    hints: list[str],
    now_ts: int,
    ttl_seconds: int,
) -> list[str]:
    ordered: list[str] = []
    if requested_model:
        ordered.append(requested_model)

    healthy_models: list[tuple[int, str]] = []
    for key, value in health.items():
        if not key.startswith(f'{provider}/'):
            continue
        ok_value = value.get('ok')
        checked_at_value = value.get('checked_at')
        if ok_value is not True or not isinstance(checked_at_value, int):
            continue
        if now_ts - checked_at_value > ttl_seconds:
            continue
        model_id = key.split('/', 1)[1]
        healthy_models.append((checked_at_value, model_id))

    for _, model_id in sorted(healthy_models, key=lambda item: item[0], reverse=True):
        if model_id not in ordered:
            ordered.append(model_id)

    for hint in hints:
        if hint not in ordered:
            ordered.append(hint)

    return ordered
