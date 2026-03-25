from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


FormatType = Literal['openai', 'gemini']


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
    ProviderMeta('opencode', 'https://opencode.ai/zen/v1', 'OPENCODE_API_KEY', 'openai', model_hints=('auto',)),
    ProviderMeta('gemini', 'https://generativelanguage.googleapis.com/v1beta', 'GEMINI_API_KEY', 'gemini', model_hints=('gemini-2.0-flash',)),
    ProviderMeta(
        'github',
        'https://models.github.ai/inference',
        'GITHUB_MODELS_API_KEY',
        'openai',
        model_hints=('gpt-4o-mini', 'gpt-4o', 'DeepSeek-V3-0324', 'Llama-3.3-70B-Instruct'),
        required_query=(('api-version', '2024-12-01-preview'),),
    ),
    ProviderMeta('mistral', 'https://api.mistral.ai/v1', 'MISTRAL_API_KEY', 'openai', model_hints=('mistral-small-latest',)),
    ProviderMeta(
        'cerebras',
        'https://api.cerebras.ai/v1',
        'CEREBRAS_API_KEY',
        'openai',
        model_hints=('gpt-oss-120b', 'llama-3.1-8b'),
    ),
    ProviderMeta(
        'sambanova',
        'https://api.sambanova.ai/v1',
        'SAMBANOVA_API_KEY',
        'openai',
        model_hints=('Meta-Llama-3.1-8B-Instruct', 'DeepSeek-V3-0324'),
    ),
)

PROVIDER_MAP: dict[str, ProviderMeta] = {provider.name: provider for provider in PROVIDERS}
