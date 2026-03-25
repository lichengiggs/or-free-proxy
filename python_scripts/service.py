from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import ProviderClient, ProviderError, ProviderHTTPError, Transport
from .config import DOTENV_PATH, ProviderSpec, configured_provider_names, get_probe_model_candidates, get_provider_model_hints, get_provider_spec, get_provider_specs, hydrate_env, load_dotenv
from .env_store import upsert_env
from .errors import classify_error, remediation_suggestion
from .health_store import load_health, upsert_health
from .token_policy import trim_prompt


@dataclass
class ProbeResult:
    provider: str
    model: str
    ok: bool
    actual_model: str | None = None
    content: str | None = None
    error: str | None = None
    category: str | None = None
    status: int | None = None
    suggestion: str | None = None


def choose_candidates(
    *,
    provider: str,
    requested_model: str | None,
    health: dict[str, dict[str, Any]],
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
        if not isinstance(value, dict) or not value.get('ok'):
            continue
        checked_at = int(value.get('checked_at', 0) or 0)
        if now_ts - checked_at > ttl_seconds:
            continue
        model_id = key.split('/', 1)[1]
        healthy_models.append((checked_at, model_id))

    for _, model_id in sorted(healthy_models, key=lambda item: item[0], reverse=True):
        if model_id not in ordered:
            ordered.append(model_id)

    for hint in hints:
        if hint not in ordered:
            ordered.append(hint)

    return ordered


class ProxyService:
    def __init__(self, *, transport: Transport | None = None, health_path: Path | None = None, health_ttl_seconds: int = 600, dotenv_path: Path | None = None) -> None:
        self.dotenv_path = dotenv_path or DOTENV_PATH
        hydrate_env(self.dotenv_path)
        self.transport = transport
        self.health_path = health_path
        self.health_ttl_seconds = health_ttl_seconds

    def available_providers(self) -> list[str]:
        return configured_provider_names()

    def provider_client(self, provider_name: str) -> ProviderClient:
        spec = get_provider_spec(provider_name)
        api_key = os.environ.get(spec.api_key_env, '').strip()
        if not api_key:
            raise ProviderError(f'{provider_name} 没有配置 API Key')
        return ProviderClient(spec=spec, api_key=api_key, transport=self.transport)

    @staticmethod
    def _mask_key(value: str) -> str:
        if len(value) <= 8:
            return '***'
        return f'{value[:4]}***{value[-4:]}'

    def provider_key_statuses(self) -> dict[str, dict[str, Any]]:
        values = load_dotenv(self.dotenv_path)
        statuses: dict[str, dict[str, Any]] = {}
        for spec in get_provider_specs():
            value = str(values.get(spec.api_key_env, '')).strip()
            statuses[spec.name] = {
                'configured': bool(value),
                'masked': self._mask_key(value) if value else '',
                'env': spec.api_key_env,
            }
        return statuses

    def save_provider_key(self, provider_name: str, api_key: str) -> dict[str, Any]:
        spec = get_provider_spec(provider_name)
        value = api_key.strip()
        if not value:
            raise ProviderError('api_key 不能为空')
        upsert_env(self.dotenv_path, spec.api_key_env, value)
        os.environ[spec.api_key_env] = value
        return {'ok': True, 'provider': provider_name, 'masked': self._mask_key(value)}

    def verify_provider_key(self, provider_name: str) -> dict[str, Any]:
        def _diagnose(exc: ProviderError) -> tuple[str, int | None, str]:
            if isinstance(exc, ProviderHTTPError):
                category = exc.category
                status = exc.status
            else:
                category = classify_error(0, str(exc)).category
                status = None
            suggestion = remediation_suggestion(category, provider_name)
            return category, status, suggestion

        try:
            models = self.list_models(provider_name)
        except ProviderError as exc:
            models = []
            first_error = exc
        else:
            first_error = None

        candidates: list[str] = []
        for model in models + get_provider_model_hints(provider_name):
            if model and model not in candidates:
                candidates.append(model)

        for candidate in candidates[:3]:
            result = self.probe(provider_name, candidate)
            if result.ok:
                return {
                    'ok': True,
                    'provider': provider_name,
                    'models': candidates,
                    'category': None,
                    'verified_model': result.actual_model or candidate,
                    'note': '已通过真实请求验证该 key 可调用模型',
                }

        if first_error is not None:
            category, status, suggestion = _diagnose(first_error)
            return {
                'ok': False,
                'provider': provider_name,
                'error': str(first_error),
                'models': candidates,
                'category': category,
                'status': status,
                'suggestion': suggestion,
            }

        # 列表可获取但候选模型都不可调用，统一按最后一次探测错误诊断。
        if candidates:
            failed = self.probe(provider_name, candidates[0])
            category = failed.category or classify_error(0, failed.error or '').category
            return {
                'ok': False,
                'provider': provider_name,
                'error': failed.error or '模型可列出但不可调用',
                'models': candidates,
                'category': category,
                'status': failed.status,
                'suggestion': remediation_suggestion(category, provider_name),
            }

        category = 'unknown'
        return {
            'ok': False,
            'provider': provider_name,
            'error': '没有可用于验证的候选模型',
            'models': [],
            'category': category,
            'status': None,
            'suggestion': remediation_suggestion(category, provider_name),
        }

    def recommended_models(self, provider_name: str, requested_model: str | None = None) -> list[str]:
        try:
            listed = self.list_models(provider_name)
        except ProviderError:
            listed = []

        hints = listed + get_provider_model_hints(provider_name)
        health = load_health(self.health_path)
        return choose_candidates(
            provider=provider_name,
            requested_model=requested_model,
            health=health,
            hints=hints,
            now_ts=int(time.time()),
            ttl_seconds=self.health_ttl_seconds,
        )

    def list_models(self, provider_name: str) -> list[str]:
        return self.provider_client(provider_name).list_models()

    def probe(self, provider_name: str, model_id: str) -> ProbeResult:
        return self.chat(provider_name, model_id, prompt='ok')

    def chat(self, provider_name: str, model_id: str, prompt: str) -> ProbeResult:
        client = self.provider_client(provider_name)
        health = load_health(self.health_path)

        hinted = [model for model in get_probe_model_candidates(provider_name, model_id) if model != model_id]
        if not hinted:
            try:
                hinted = [model for model in client.list_models() if model != model_id][:5]
            except ProviderError:
                hinted = get_provider_model_hints(provider_name)

        candidates = choose_candidates(
            provider=provider_name,
            requested_model=model_id,
            health=health,
            hints=hinted,
            now_ts=int(time.time()),
            ttl_seconds=self.health_ttl_seconds,
        )

        safe_prompt = trim_prompt(provider_name, prompt)
        last_error: str | None = None
        last_category: str | None = None
        last_status: int | None = None
        for candidate in candidates:
            try:
                content = client.chat(candidate, safe_prompt)
                upsert_health(provider_name, candidate, True, path=self.health_path)
                return ProbeResult(provider=provider_name, model=model_id, ok=True, actual_model=candidate, content=content)
            except ProviderError as exc:
                last_error = str(exc)
                if isinstance(exc, ProviderHTTPError):
                    last_category = exc.category
                    last_status = exc.status
                else:
                    last_category = classify_error(0, last_error).category
                    last_status = None
                upsert_health(provider_name, candidate, False, reason=last_category, path=self.health_path)

        final_category = last_category or classify_error(0, last_error or '').category
        return ProbeResult(
            provider=provider_name,
            model=model_id,
            ok=False,
            error=last_error or '探测失败',
            category=final_category,
            status=last_status,
            suggestion=remediation_suggestion(final_category, provider_name),
        )

    def summary(self) -> dict[str, Any]:
        providers = []
        for provider_name in self.available_providers():
            try:
                models = self.list_models(provider_name)
                providers.append({'provider': provider_name, 'models': models})
            except ProviderError as exc:
                providers.append({'provider': provider_name, 'error': str(exc), 'models': []})
        return {'providers': providers}
