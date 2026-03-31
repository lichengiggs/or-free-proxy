from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from collections.abc import Callable, Iterable
from pathlib import Path

from .config import DOTENV_PATH, hydrate_env, load_dotenv
from .env_store import upsert_env
from .errors import classify_error, remediation_suggestion
from .health_store import load_health, upsert_health
from .openai_relay import OpenAIRelay
from .provider_adapter import ProviderAdapter
from .provider_catalog import configured_provider_names, get_model_capabilities, get_provider, get_provider_model_hints, list_providers
from .provider_errors import ProviderError, ProviderHTTPError
from .provider_routing import AliasName, PUBLIC_MODEL_ALIASES, ResolvedModelRequest, choose_candidates, resolve_alias_candidates, resolve_model_request
from .provider_transport import Transport
from .token_budgeting import resolve_token_budget, shrink_budget_after_limit_error
from .token_limit_store import load_token_limits, upsert_token_limit
from .token_policy import model_default_output_tokens, model_default_timeout_seconds, probe_output_tokens, response_token_budget, trim_prompt

JsonObject = dict[str, object]


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class ResolvedOpenAIRequest:
    provider: str | None
    model: str
    alias: AliasName | None


@dataclass(frozen=True)
class OpenAIForwardResult:
    ok: bool
    provider: str
    model: str
    status: int
    headers: dict[str, str]
    body: bytes
    content: str | None = None
    error: str | None = None
    category: str | None = None
    suggestion: str | None = None
    stream_chunks: Iterable[bytes] | None = None


class ProxyService:
    def __init__(
        self,
        *,
        transport: Transport | None = None,
        health_path: Path | None = None,
        token_limit_path: Path | None = None,
        health_ttl_seconds: int = 600,
        dotenv_path: Path | None = None,
        request_timeout_seconds: int = 12,
        debug_log: Callable[..., None] | None = None,
    ) -> None:
        self.dotenv_path = dotenv_path or DOTENV_PATH
        hydrate_env(self.dotenv_path)
        self.transport = transport
        self.health_path = health_path
        self.token_limit_path = token_limit_path
        self.health_ttl_seconds = health_ttl_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.debug_log = debug_log

    def available_providers(self) -> list[str]:
        return configured_provider_names()

    def public_models(self) -> list[dict[str, str]]:
        return [dict(item) for item in PUBLIC_MODEL_ALIASES]

    def provider_adapter(self, provider_name: str) -> ProviderAdapter:
        provider = get_provider(provider_name)
        api_key = os.environ.get(provider.api_key_env, '').strip()
        if not api_key:
            raise ProviderError(f'{provider_name} 没有配置 API Key')
        return ProviderAdapter(
            provider=provider,
            api_key=api_key,
            transport=self.transport,
            request_timeout_seconds=self.request_timeout_seconds,
            debug_log=self.debug_log,
        )

    def openai_relay(self) -> OpenAIRelay:
        return OpenAIRelay(
            adapter_factory=self.provider_adapter,
            health_loader=lambda: load_health(self.health_path),
            health_ttl_seconds=self.health_ttl_seconds,
            configured_providers_loader=self.available_providers,
        )

    @staticmethod
    def _mask_key(value: str) -> str:
        if len(value) <= 8:
            return '***'
        return f'{value[:4]}***{value[-4:]}'

    def provider_key_statuses(self) -> dict[str, dict[str, object]]:
        values = load_dotenv(self.dotenv_path)
        statuses: dict[str, dict[str, object]] = {}
        for provider in list_providers():
            value = str(values.get(provider.api_key_env, '')).strip()
            statuses[provider.name] = {
                'configured': bool(value),
                'masked': self._mask_key(value) if value else '',
                'env': provider.api_key_env,
            }
        return statuses

    def save_provider_key(self, provider_name: str, api_key: str) -> dict[str, object]:
        provider = get_provider(provider_name)
        value = api_key.strip()
        if not value:
            raise ProviderError('api_key 不能为空')
        upsert_env(self.dotenv_path, provider.api_key_env, value)
        os.environ[provider.api_key_env] = value
        return {'ok': True, 'provider': provider_name, 'masked': self._mask_key(value)}

    def verify_provider_key(self, provider_name: str) -> dict[str, object]:
        def diagnose(exc: ProviderError) -> tuple[str, int | None, str]:
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
            first_error: ProviderError | None = exc
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
            category, status, suggestion = diagnose(first_error)
            return {
                'ok': False,
                'provider': provider_name,
                'error': str(first_error),
                'models': candidates,
                'category': category,
                'status': status,
                'suggestion': suggestion,
            }

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
        return self.provider_adapter(provider_name).list_models()

    def probe(self, provider_name: str, model_id: str) -> ProbeResult:
        return self.chat(provider_name, model_id, prompt='ok', max_output_tokens=probe_output_tokens(provider_name, model_id))

    def chat(self, provider_name: str, model_id: str, prompt: str, max_output_tokens: int | None = None) -> ProbeResult:
        adapter = self.provider_adapter(provider_name)
        trimmed = trim_prompt(provider_name, prompt)
        candidates = [model_id]

        output_tokens = max_output_tokens if max_output_tokens is not None else response_token_budget(provider_name)
        learned_limits = load_token_limits(self.token_limit_path)
        last_error: str | None = None
        last_category: str | None = None
        last_status: int | None = None

        for candidate in candidates:
            budget = resolve_token_budget(
                provider=provider_name,
                model=candidate,
                prompt=trimmed,
                requested_output_tokens=output_tokens,
                learned_limits=learned_limits,
                model_metadata=None,
            )
            try:
                content = adapter.chat_text(candidate, budget.trimmed_prompt, max_tokens=budget.output_tokens_limit)
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
                if last_category == 'token_limit':
                    learned = shrink_budget_after_limit_error(
                        provider=provider_name,
                        model=candidate,
                        prompt=budget.trimmed_prompt,
                        attempted_output_tokens=budget.output_tokens_limit,
                        error_message=last_error,
                    )
                    upsert_token_limit(
                        provider_name,
                        candidate,
                        input_tokens_limit=learned.input_tokens_limit,
                        output_tokens_limit=learned.output_tokens_limit,
                        source=learned.source,
                        path=self.token_limit_path,
                    )
                    refreshed_limits = load_token_limits(self.token_limit_path)
                    retry_budget = resolve_token_budget(
                        provider=provider_name,
                        model=candidate,
                        prompt=trimmed,
                        requested_output_tokens=output_tokens,
                        learned_limits=refreshed_limits,
                        model_metadata=None,
                    )
                    try:
                        retry_content = adapter.chat_text(candidate, retry_budget.trimmed_prompt, max_tokens=retry_budget.output_tokens_limit)
                        upsert_health(provider_name, candidate, True, path=self.health_path)
                        return ProbeResult(provider=provider_name, model=model_id, ok=True, actual_model=candidate, content=retry_content)
                    except ProviderError as retry_exc:
                        last_error = str(retry_exc)
                        if isinstance(retry_exc, ProviderHTTPError):
                            last_category = retry_exc.category
                            last_status = retry_exc.status
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

    def summary(self) -> dict[str, object]:
        providers: list[dict[str, object]] = []
        for provider_name in self.available_providers():
            try:
                models = self.list_models(provider_name)
                providers.append({'provider': provider_name, 'models': models})
            except ProviderError as exc:
                providers.append({'provider': provider_name, 'error': str(exc), 'models': []})
        return {'providers': providers}

    def resolve_openai_target(self, payload: JsonObject) -> ResolvedOpenAIRequest:
        raw_model = payload.get('model')
        raw_provider = payload.get('provider')
        resolved = resolve_model_request(
            model=str(raw_model) if isinstance(raw_model, str) else '',
            provider=str(raw_provider) if isinstance(raw_provider, str) else None,
            configured=self.available_providers(),
            known_providers={provider.name for provider in list_providers()},
        )
        return ResolvedOpenAIRequest(provider=resolved.provider, model=resolved.model, alias=resolved.alias)

    @staticmethod
    def _content_type(headers: dict[str, str]) -> str:
        return str(headers.get('Content-Type') or headers.get('content-type') or '').lower()

    @staticmethod
    def _sse_json_line(payload: JsonObject | str) -> bytes:
        if isinstance(payload, str):
            return f'data: {payload}\n\n'.encode('utf-8')
        return f'data: {json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}\n\n'.encode('utf-8')

    @staticmethod
    def _sse_done_chunk() -> Iterable[bytes]:
        yield ProxyService._sse_json_line('[DONE]')

    @staticmethod
    def _sanitize_openai_forward_payload(provider_name: str, model_id: str, payload: JsonObject) -> tuple[str, JsonObject]:
        normalized_model = model_id.strip()
        provider_prefix = f'{provider_name}/'
        if normalized_model.startswith(provider_prefix):
            normalized_model = normalized_model.removeprefix(provider_prefix)
        request_payload = dict(payload)
        request_payload.pop('provider', None)
        request_payload['model'] = normalized_model
        return normalized_model, request_payload

    @staticmethod
    def _stream_text_delta(choice: object) -> dict[str, str]:
        if not isinstance(choice, dict):
            return {}
        message = choice.get('message')
        if isinstance(message, dict):
            content = message.get('content')
            if isinstance(content, str) and content:
                return {'role': str(message.get('role') or 'assistant'), 'content': content}
            reasoning = message.get('reasoning_content')
            if isinstance(reasoning, str) and reasoning:
                return {'role': str(message.get('role') or 'assistant'), 'reasoning_content': reasoning}
            if isinstance(content, list):
                chunks: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get('text')
                        if isinstance(text, str) and text:
                            chunks.append(text)
                merged = ''.join(chunks)
                if merged:
                    return {'role': str(message.get('role') or 'assistant'), 'content': merged}
        text = choice.get('text')
        if isinstance(text, str) and text:
            return {'role': 'assistant', 'content': text}
        return {}

    def _wrap_openai_body_as_sse(self, fallback_model: str, body: bytes) -> Iterable[bytes]:
        parsed = json.loads(body.decode('utf-8'))
        if not isinstance(parsed, dict):
            yield from self._sse_done_chunk()
            return
        choices = parsed.get('choices')
        first_choice = choices[0] if isinstance(choices, list) and choices else {}
        chunk_id = str(parsed.get('id', f'chatcmpl-{int(time.time())}'))
        created_raw = parsed.get('created')
        created = created_raw if isinstance(created_raw, int) else int(time.time())
        actual_model = str(parsed.get('model') or fallback_model)
        delta = self._stream_text_delta(first_choice)
        if delta:
            yield self._sse_json_line(
                {
                    'id': chunk_id,
                    'object': 'chat.completion.chunk',
                    'created': created,
                    'model': actual_model,
                    'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}],
                }
            )
        finish_reason = 'stop'
        if isinstance(first_choice, dict):
            raw_finish_reason = first_choice.get('finish_reason')
            if isinstance(raw_finish_reason, str) and raw_finish_reason:
                finish_reason = raw_finish_reason
        yield self._sse_json_line(
            {
                'id': chunk_id,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': actual_model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}],
            }
        )
        yield from self._sse_done_chunk()

    def _wrap_text_as_sse(self, *, model: str, content: str) -> Iterable[bytes]:
        chunk_id = 'chatcmpl-free-proxy'
        created = 1
        if content:
            yield self._sse_json_line(
                {
                    'id': chunk_id,
                    'object': 'chat.completion.chunk',
                    'created': created,
                    'model': model,
                    'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': content}, 'finish_reason': None}],
                }
            )
        yield self._sse_json_line(
            {
                'id': chunk_id,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
            }
        )
        yield from self._sse_done_chunk()

    def _normalize_stream_result(
        self,
        *,
        provider: str,
        model: str,
        status: int,
        headers: dict[str, str],
        chunks: Iterable[bytes],
    ) -> OpenAIForwardResult:
        content_type = self._content_type(headers)
        if 'text/event-stream' in content_type:
            return OpenAIForwardResult(ok=True, provider=provider, model=model, status=status, headers=headers, body=b'', stream_chunks=chunks)
        body = b''.join(chunks)
        return OpenAIForwardResult(
            ok=True,
            provider=provider,
            model=model,
            status=status,
            headers={'Content-Type': 'text/event-stream; charset=utf-8'},
            body=b'',
            stream_chunks=self._wrap_openai_body_as_sse(model, body),
        )

    def execute_openai_target(self, target: ResolvedOpenAIRequest, payload: JsonObject) -> OpenAIForwardResult:
        if target.alias is not None:
            return self.forward_alias_chat(target.alias, payload)
        if target.provider is None:
            return OpenAIForwardResult(
                ok=False,
                provider='free-proxy',
                model=target.model,
                status=400,
                headers={},
                body=b'',
                error='missing provider',
                category='invalid_request_error',
            )
        return self.forward_direct_chat(target.provider, target.model, payload)

    def forward_alias_chat(self, alias: AliasName, payload: JsonObject) -> OpenAIForwardResult:
        candidates = resolve_alias_candidates(alias, self.available_providers())
        if not candidates:
            return OpenAIForwardResult(
                ok=False,
                provider='free-proxy',
                model=alias,
                status=400,
                headers={},
                body=b'',
                error='no configured providers found, please save at least one API key first',
                category='invalid_request_error',
            )
        last_result: OpenAIForwardResult | None = None
        for provider_name, model_id in candidates:
            result = self.forward_direct_chat(provider_name, model_id, payload)
            if result.ok:
                return result
            last_result = result
        if last_result is not None:
            return last_result
        return OpenAIForwardResult(
            ok=False,
            provider='free-proxy',
            model=alias,
            status=502,
            headers={},
            body=b'',
            error='no available model found from configured providers',
            category='server_error',
        )

    def forward_direct_chat(self, provider_name: str, model_id: str, payload: JsonObject) -> OpenAIForwardResult:
        provider = get_provider(provider_name)
        if provider.format != 'openai':
            prompt = self._extract_prompt(payload)
            requested_output_tokens = self._requested_output_tokens(payload)
            result = self.chat(provider_name, model_id, prompt, max_output_tokens=requested_output_tokens)
            if result.ok:
                actual_model = result.actual_model or model_id
                if bool(payload.get('stream')):
                    return OpenAIForwardResult(
                        ok=True,
                        provider=provider_name,
                        model=actual_model,
                        status=200,
                        headers={'Content-Type': 'text/event-stream; charset=utf-8'},
                        body=b'',
                        stream_chunks=self._wrap_text_as_sse(model=f'{provider_name}/{actual_model}', content=result.content or ''),
                    )
                return OpenAIForwardResult(
                    ok=True,
                    provider=provider_name,
                    model=actual_model,
                    status=200,
                    headers={},
                    body=b'',
                    content=result.content,
                )
            return OpenAIForwardResult(
                ok=False,
                provider=provider_name,
                model=model_id,
                status=result.status or 502,
                headers={},
                body=b'',
                error=result.error,
                category=result.category,
                suggestion=result.suggestion,
            )

        adapter = self.provider_adapter(provider_name)
        normalized_model_id, request_payload = self._sanitize_openai_forward_payload(provider_name, model_id, payload)
        prompt = self._extract_prompt(request_payload)
        requested_output_tokens = self._requested_output_tokens(request_payload)
        capabilities = get_model_capabilities(provider_name, normalized_model_id)
        if capabilities.get('reasoning') is True:
            requested_output_tokens = min(requested_output_tokens or model_default_output_tokens(provider_name, normalized_model_id, 1024), model_default_output_tokens(provider_name, normalized_model_id, 1024))
        budget = resolve_token_budget(
            provider=provider_name,
            model=normalized_model_id,
            prompt=prompt,
            requested_output_tokens=requested_output_tokens,
            learned_limits=load_token_limits(self.token_limit_path),
            model_metadata=None,
        )
        request_payload['max_tokens'] = budget.output_tokens_limit
        if not isinstance(request_payload.get('messages'), list) or not request_payload.get('messages'):
            request_payload['messages'] = [{'role': 'user', 'content': budget.trimmed_prompt}]
            request_payload.pop('prompt', None)
        if bool(request_payload.get('stream')):
            try:
                status, headers, chunks = adapter.chat_completions_stream(request_payload)
            except ProviderError as exc:
                category = classify_error(0, str(exc)).category
                return OpenAIForwardResult(
                    ok=False,
                    provider=provider_name,
                    model=normalized_model_id,
                    status=502,
                    headers={},
                    body=b'',
                    error=str(exc),
                    category=category,
                    suggestion=remediation_suggestion(category, provider_name),
                )

            if status < 400:
                return self._normalize_stream_result(provider=provider_name, model=normalized_model_id, status=status, headers=headers, chunks=chunks)

            text = b''.join(chunks).decode('utf-8', errors='ignore')
            failure = classify_error(status, text)
            if self.debug_log is not None:
                self.debug_log(
                    'request_failed',
                    provider=provider_name,
                    model=normalized_model_id,
                    status=status,
                    category=failure.category,
                    error=text or f'upstream status {status}',
                    suggestion=remediation_suggestion(failure.category, provider_name),
                )
            return OpenAIForwardResult(
                ok=False,
                provider=provider_name,
                model=normalized_model_id,
                status=status,
                headers=headers,
                body=b'',
                error=text or f'upstream status {status}',
                category=failure.category,
                suggestion=remediation_suggestion(failure.category, provider_name),
            )

        try:
            status, headers, body = adapter.chat_completions_raw(request_payload)
        except ProviderError as exc:
            category = classify_error(0, str(exc)).category
            return OpenAIForwardResult(
                ok=False,
                provider=provider_name,
                model=normalized_model_id,
                status=502,
                headers={},
                body=b'',
                error=str(exc),
                category=category,
                suggestion=remediation_suggestion(category, provider_name),
            )

        if status < 400:
            return OpenAIForwardResult(ok=True, provider=provider_name, model=normalized_model_id, status=status, headers=headers, body=body)

        text = body.decode('utf-8', errors='ignore')
        failure = classify_error(status, text)
        if self.debug_log is not None:
            self.debug_log(
                'request_failed',
                provider=provider_name,
                model=normalized_model_id,
                status=status,
                category=failure.category,
                error=text or f'upstream status {status}',
                suggestion=remediation_suggestion(failure.category, provider_name),
            )
        return OpenAIForwardResult(
            ok=False,
            provider=provider_name,
            model=normalized_model_id,
            status=status,
            headers=headers,
            body=b'',
            error=text or f'upstream status {status}',
            category=failure.category,
            suggestion=remediation_suggestion(failure.category, provider_name),
        )

    @staticmethod
    def _message_to_text(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            texts: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = item.get('text')
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
            return '\n'.join(texts).strip()
        return ''

    def _extract_prompt(self, payload: JsonObject) -> str:
        prompt_value = payload.get('prompt')
        if isinstance(prompt_value, str) and prompt_value.strip():
            return prompt_value.strip()
        messages = payload.get('messages')
        if isinstance(messages, list):
            chunks: list[str] = []
            for item in messages:
                if not isinstance(item, dict):
                    continue
                text = self._message_to_text(item.get('content'))
                if text:
                    chunks.append(text)
            if chunks:
                return '\n'.join(chunks).strip()
        return 'ok'

    @staticmethod
    def _requested_output_tokens(payload: JsonObject) -> int | None:
        for key in ('max_tokens', 'max_completion_tokens', 'max_output_tokens'):
            value = payload.get(key)
            if isinstance(value, int):
                return value
        return None
