from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Literal


FormatType = Literal['openai', 'gemini', 'anthropic']


@dataclass(frozen=True)
class ProviderMeta:
    name: str
    base_url: str
    api_key_env: str
    format: FormatType
    model_hints: tuple[str, ...] = field(default_factory=tuple)
    required_query: tuple[tuple[str, str], ...] = field(default_factory=tuple)


PROVIDERS: tuple[ProviderMeta, ...] = (
    ProviderMeta(
        'openrouter',
        'https://openrouter.ai/api/v1',
        'OPENROUTER_API_KEY',
        'openai',
        model_hints=('openrouter/auto:free',),
    ),
    ProviderMeta(
        'groq',
        'https://api.groq.com/openai/v1',
        'GROQ_API_KEY',
        'openai',
        model_hints=('llama-3.1-8b-instant', 'llama-3.3-70b-versatile'),
    ),
    ProviderMeta(
        'longcat',
        'https://api.longcat.chat/openai',
        'LONGCAT_API_KEY',
        'openai',
        model_hints=('LongCat-Flash-Lite', 'LongCat-Flash-Chat', 'LongCat-Flash-Thinking', 'LongCat-Flash-Thinking-2601'),
    ),
    ProviderMeta(
        'gemini',
        'https://generativelanguage.googleapis.com/v1beta',
        'GEMINI_API_KEY',
        'gemini',
        model_hints=('gemini-3.1-flash-lite-preview', 'gemini-2.0-flash'),
    ),
    ProviderMeta(
        'github',
        'https://models.github.ai/inference',
        'GITHUB_MODELS_API_KEY',
        'openai',
        model_hints=('gpt-4o', 'gpt-4o-mini', 'gpt-4.1-mini', 'DeepSeek-V3-0324'),
        required_query=(('api-version', '2024-12-01-preview'),),
    ),
    ProviderMeta(
        'mistral',
        'https://api.mistral.ai/v1',
        'MISTRAL_API_KEY',
        'openai',
        model_hints=('mistral-large-latest', 'mistral-medium-latest', 'mistral-small-latest'),
    ),
    ProviderMeta(
        'sambanova',
        'https://api.sambanova.ai/v1',
        'SAMBANOVA_API_KEY',
        'openai',
        model_hints=('DeepSeek-V3.1-Terminus', 'Qwen3-235B', 'Meta-Llama-3.1-8B-Instruct'),
    ),
    ProviderMeta(
        'nvidia',
        'https://integrate.api.nvidia.com/v1',
        'NVIDIA_API_KEY',
        'openai',
        model_hints=('meta/llama-3.1-70b-instruct',),
    ),
)

PROVIDER_MAP: dict[str, ProviderMeta] = {provider.name: provider for provider in PROVIDERS}


def get_provider(name: str) -> ProviderMeta:
    provider = PROVIDER_MAP.get(name)
    if provider is None:
        raise KeyError(f'unknown provider: {name}')
    return provider


def list_providers(names: Iterable[str] | None = None) -> list[ProviderMeta]:
    if names is None:
        return list(PROVIDERS)
    wanted = set(names)
    return [provider for provider in PROVIDERS if provider.name in wanted]


def configured_provider_names(env: dict[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    return [provider.name for provider in PROVIDERS if str(source.get(provider.api_key_env, '')).strip()]


def get_provider_model_hints(name: str) -> list[str]:
    return list(get_provider(name).model_hints)


def get_provider_required_query(name: str) -> dict[str, str]:
    return dict(get_provider(name).required_query)
