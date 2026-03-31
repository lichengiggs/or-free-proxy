from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .provider_catalog import get_provider_model_hints


AliasName = Literal['auto']
CandidateSource = Literal['user_requested', 'health_boosted', 'provider_default', 'static_fallback_order']
HealthState = dict[str, dict[str, object]]

PUBLIC_MODEL_ALIASES: tuple[dict[str, str], ...] = (
    {'id': 'free-proxy/auto', 'object': 'model', 'owned_by': 'free-proxy'},
)

STATIC_AUTO_FALLBACK: tuple[tuple[str, str], ...] = (
    ('longcat', 'LongCat-Flash-Lite'),
    ('gemini', 'gemini-3.1-flash-lite-preview'),
    ('github', 'gpt-4o-mini'),
    ('mistral', 'mistral-large-latest'),
    ('sambanova', 'DeepSeek-V3.1-Terminus'),
    ('openrouter', 'openrouter/auto:free'),
    ('groq', 'llama-3.3-70b-versatile'),
    ('nvidia', 'meta/llama-3.1-70b-instruct'),
)


@dataclass(frozen=True)
class ResolvedModelRequest:
    provider: str | None
    model: str
    alias: AliasName | None


@dataclass(frozen=True)
class CandidateTarget:
    provider: str
    model: str
    source: CandidateSource
    rank: int


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
    if '/' in normalized_model:
        maybe_provider, maybe_model = normalized_model.split('/', 1)
        if maybe_provider in known_providers and maybe_model:
            return ResolvedModelRequest(provider=maybe_provider, model=maybe_model, alias=None)

    if configured:
        return ResolvedModelRequest(provider=configured[0], model=normalized_model, alias=None)

    raise ValueError('no configured providers found, please save at least one API key first')


def resolve_alias_candidates(alias: AliasName, configured: list[str]) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    for provider_name, model_id in STATIC_AUTO_FALLBACK:
        if provider_name not in configured:
            continue
        pair = (provider_name, model_id)
        if pair not in ordered:
            ordered.append(pair)
    return ordered


def build_auto_candidates(*, requested_model: str | None, configured: list[str], health: HealthState, now_ts: int, ttl_seconds: int) -> list[CandidateTarget]:
    ordered: list[CandidateTarget] = []
    seen: set[tuple[str, str]] = set()

    def push(provider: str, model: str, source: CandidateSource) -> None:
        key = (provider, model)
        if provider not in configured or key in seen:
            return
        seen.add(key)
        ordered.append(CandidateTarget(provider, model, source, len(ordered)))

    if requested_model and '/' in requested_model:
        provider_name, model_id = requested_model.split('/', 1)
        push(provider_name, model_id, 'user_requested')

    for key, value in health.items():
        if value.get('ok') is not True or not isinstance(value.get('checked_at'), int):
            continue
        checked_at = int(value['checked_at'])
        if now_ts - checked_at > ttl_seconds:
            continue
        provider_name, model_id = key.split('/', 1)
        push(provider_name, model_id, 'health_boosted')

    for provider_name in configured:
        hints = get_provider_model_hints(provider_name)
        if hints:
            push(provider_name, hints[0], 'provider_default')

    for provider_name, model_id in STATIC_AUTO_FALLBACK:
        push(provider_name, model_id, 'static_fallback_order')

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
