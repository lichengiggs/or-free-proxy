from __future__ import annotations

import json
import time
from dataclasses import dataclass
from collections.abc import Callable, Iterable

from .errors import classify_error
from .provider_catalog import ProviderMeta, get_model_capabilities, get_provider_model_hints, get_provider_required_query
from .provider_errors import ProviderError, ProviderHTTPError
from .provider_transport import Transport, UrlLibTransport, build_url
from .response_normalizer import sanitize_model_text
from .request_limiter import RequestLimiterGate

JsonObject = dict[str, object]


@dataclass(frozen=True)
class AdapterResponse:
    status: int
    headers: dict[str, str]
    body: bytes | None
    stream: Iterable[bytes] | None
    content_type: str


@dataclass
class ProviderAdapter:
    provider: ProviderMeta
    api_key: str
    transport: Transport | None = None
    request_timeout_seconds: int = 12
    request_limiter: RequestLimiterGate | None = None
    debug_log: Callable[..., None] | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            self.transport = UrlLibTransport()

    def _reserve_request_slot(self) -> None:
        if self.request_limiter is None:
            return
        self.request_limiter.acquire()

    def _headers(self) -> dict[str, str]:
        if self.provider.format == 'gemini':
            return {
                'Content-Type': 'application/json',
                'x-goog-api-key': self.api_key,
            }
        if self.provider.name == 'github':
            return {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
                'X-GitHub-Api-Version': '2024-12-01-preview',
            }
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

    def _request_json(
        self,
        method: str,
        path: str,
        payload: JsonObject | None = None,
        query: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> tuple[int, dict[str, str], object]:
        raw_body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        timeout_value = timeout if timeout is not None else self._request_timeout_seconds_for_path(path)
        if self.debug_log is not None:
            self.debug_log(
                'upstream_request',
                provider=self.provider.name,
                model=payload.get('model') if isinstance(payload, dict) else 'none',
                timeout_s=timeout_value,
                auth_present=True,
                auth_scheme='Bearer',
                upstream_path=path,
                query_keys=','.join(sorted(query.keys())) if query else 'none',
            )
        started_at = time.time()
        try:
            self._reserve_request_slot()
            status, headers, raw = self.transport.request(
                method,
                build_url(self.provider.base_url, path, query),
                self._headers(),
                raw_body,
                timeout_value,
            )
        except TimeoutError as exc:
            raise ProviderError(f'网络连接失败: {exc}') from exc
        elapsed_ms = int((time.time() - started_at) * 1000)
        if self.debug_log is not None:
            self.debug_log(
                'upstream_response',
                provider=self.provider.name,
                model=payload.get('model') if isinstance(payload, dict) else 'none',
                status=status,
                elapsed_ms=elapsed_ms,
                content_type=headers.get('content-type', headers.get('Content-Type', '')) if isinstance(headers, dict) else '',
                cf_ray=headers.get('cf-ray', 'none') if isinstance(headers, dict) else 'none',
                retry_after=headers.get('retry-after', 'none') if isinstance(headers, dict) else 'none',
            )
        if not raw:
            return status, headers, None
        text = raw.decode('utf-8', errors='ignore')
        try:
            return status, headers, json.loads(text)
        except json.JSONDecodeError:
            return status, headers, text

    def list_models(self) -> list[str]:
        status, _, data = self._request_json('GET', '/models', query=get_provider_required_query(self.provider.name))
        if status >= 400:
            if self.provider.name in {'github', 'groq', 'longcat', 'nvidia', 'ofox'}:
                return get_provider_model_hints(self.provider.name)
            self._raise_http_error(status, data, '获取模型失败')

        if self.provider.name in {'github', 'groq', 'longcat', 'nvidia', 'ofox'} and not self._has_model_items(data):
            return get_provider_model_hints(self.provider.name)

        items = self._extract_model_items(data)
        ids: list[str] = []
        for item in items:
            raw_model_id = item.get('id') or item.get('name')
            if not isinstance(raw_model_id, str) or not raw_model_id.strip():
                continue
            if self.provider.name == 'openrouter' and not self._is_openrouter_free_model(item, raw_model_id):
                continue
            if self.provider.name == 'ofox' and not raw_model_id.endswith(':free'):
                continue
            if self.provider.name == 'gemini' and not self._is_supported_gemini_text_model(item, raw_model_id):
                continue
            ids.append(self.normalize_model_id(raw_model_id))
        if ids:
            return ids
        return get_provider_model_hints(self.provider.name)

    def chat_text(self, model_id: str, prompt: str, max_tokens: int = 256) -> str:
        if self.provider.format == 'gemini':
            return self._chat_gemini(model_id, prompt, max_tokens=max_tokens)
        return self._chat_openai(model_id, prompt, max_tokens=max_tokens)

    def chat_completions_raw(self, payload: JsonObject) -> tuple[int, dict[str, str], bytes]:
        if self.provider.format != 'openai':
            raise ProviderError('provider is not openai-compatible')
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        model_value = payload.get('model')
        timeout = self._request_timeout_seconds_for_model(model_value) if isinstance(model_value, str) else self.request_timeout_seconds
        if self.debug_log is not None:
            self.debug_log(
                'upstream_request',
                provider=self.provider.name,
                model=model_value if isinstance(model_value, str) else 'none',
                timeout_s=timeout,
                auth_present=True,
                auth_scheme='Bearer',
                upstream_path='/chat/completions',
                query_keys='none',
            )
        started_at = time.time()
        try:
            self._reserve_request_slot()
            status, headers, response_body = self.transport.request(
                'POST',
                build_url(self.provider.base_url, '/chat/completions', get_provider_required_query(self.provider.name)),
                self._headers(),
                body,
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise ProviderError(f'网络连接失败: {exc}') from exc
        elapsed_ms = int((time.time() - started_at) * 1000)
        if self.debug_log is not None:
            self.debug_log(
                'upstream_response',
                provider=self.provider.name,
                model=model_value if isinstance(model_value, str) else 'none',
                status=status,
                elapsed_ms=elapsed_ms,
                content_type=headers.get('content-type', headers.get('Content-Type', '')) if isinstance(headers, dict) else '',
                cf_ray=headers.get('cf-ray', 'none') if isinstance(headers, dict) else 'none',
                retry_after=headers.get('retry-after', 'none') if isinstance(headers, dict) else 'none',
            )
        return status, headers, response_body

    def chat_completions_stream(self, payload: JsonObject) -> tuple[int, dict[str, str], Iterable[bytes]]:
        if self.provider.format != 'openai':
            raise ProviderError('provider is not openai-compatible')
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        model_value = payload.get('model')
        timeout = self._request_timeout_seconds_for_model(model_value) if isinstance(model_value, str) else self.request_timeout_seconds
        if self.debug_log is not None:
            self.debug_log(
                'upstream_request',
                provider=self.provider.name,
                model=model_value if isinstance(model_value, str) else 'none',
                timeout_s=timeout,
                auth_present=True,
                auth_scheme='Bearer',
                upstream_path='/chat/completions',
                query_keys='none',
            )
        started_at = time.time()
        try:
            self._reserve_request_slot()
            status, headers, chunks = self.transport.stream_request(
                'POST',
                build_url(self.provider.base_url, '/chat/completions', get_provider_required_query(self.provider.name)),
                self._headers(),
                body,
                timeout,
            )
        except TimeoutError as exc:
            raise ProviderError(f'网络连接失败: {exc}') from exc
        elapsed_ms = int((time.time() - started_at) * 1000)
        if self.debug_log is not None:
            self.debug_log(
                'upstream_response',
                provider=self.provider.name,
                model=model_value if isinstance(model_value, str) else 'none',
                status=status,
                elapsed_ms=elapsed_ms,
                content_type=headers.get('content-type', headers.get('Content-Type', '')) if isinstance(headers, dict) else '',
                cf_ray=headers.get('cf-ray', 'none') if isinstance(headers, dict) else 'none',
                retry_after=headers.get('retry-after', 'none') if isinstance(headers, dict) else 'none',
            )
        return status, headers, chunks

    def forward_chat(self, payload: JsonObject) -> AdapterResponse:
        if self.provider.format == 'openai':
            if bool(payload.get('stream')):
                status, headers, stream = self.chat_completions_stream(payload)
                content_type = str(headers.get('Content-Type') or headers.get('content-type') or '')
                return AdapterResponse(status, headers, None, stream, content_type)
            status, headers, body = self.chat_completions_raw(payload)
            content_type = str(headers.get('Content-Type') or headers.get('content-type') or '')
            return AdapterResponse(status, headers, body, None, content_type)

        prompt = self._prompt_from_payload(payload)
        max_tokens = payload.get('max_tokens')
        token_limit = int(max_tokens) if isinstance(max_tokens, int) else 256
        if self.provider.format == 'gemini':
            request_payload: JsonObject = {
                'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                'generationConfig': {'temperature': 0, 'maxOutputTokens': token_limit},
            }
            path = f'/models/{self.normalize_model_id(str(payload.get("model", "")))}:generateContent'
            status, headers, data = self._request_json('POST', path, request_payload, timeout=self._request_timeout_seconds_for_model(str(payload.get('model', ''))))
            body = json.dumps(data, ensure_ascii=False).encode('utf-8') if not isinstance(data, str) else data.encode('utf-8')
            return AdapterResponse(status, {'Content-Type': 'application/json; charset=utf-8', **headers}, body, None, 'application/json; charset=utf-8')

        raise ProviderError('provider format is not supported')

    def normalize_model_id(self, model_id: str) -> str:
        if self.provider.format == 'gemini' and model_id.startswith('models/'):
            return model_id.removeprefix('models/')
        return model_id

    def _chat_openai(self, model_id: str, prompt: str, *, max_tokens: int) -> str:
        payload: JsonObject = {
            'model': model_id,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0,
            'max_tokens': max_tokens,
        }
        status, _, data = self._request_json(
            'POST',
            '/chat/completions',
            payload,
            query=get_provider_required_query(self.provider.name),
            timeout=self._request_timeout_seconds_for_model(model_id),
        )
        if status >= 400:
            self._raise_http_error(status, data, '连通失败')
        return self._extract_openai_text(data)

    def _chat_gemini(self, model_id: str, prompt: str, *, max_tokens: int) -> str:
        payload: JsonObject = {
            'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0, 'maxOutputTokens': max_tokens},
        }
        path = f'/models/{self.normalize_model_id(model_id)}:generateContent'
        status, _, data = self._request_json('POST', path, payload, timeout=self._request_timeout_seconds_for_model(model_id))
        if status >= 400:
            self._raise_http_error(status, data, '连通失败')
        return self._extract_gemini_text(data)

    @staticmethod
    def _prompt_from_payload(payload: JsonObject) -> str:
        prompt = payload.get('prompt')
        if isinstance(prompt, str) and prompt.strip():
            return prompt.strip()
        messages = payload.get('messages')
        if isinstance(messages, list):
            parts: list[str] = []
            for item in messages:
                if isinstance(item, dict):
                    content = item.get('content')
                    if isinstance(content, str) and content.strip():
                        parts.append(content.strip())
            if parts:
                return '\n'.join(parts)
        return 'ok'

    def _request_timeout_seconds_for_path(self, path: str) -> int:
        marker = '/models/'
        if self.provider.format == 'gemini' and marker in path and ':generateContent' in path:
            model_id = path.split(marker, 1)[1].split(':generateContent', 1)[0]
            return self._request_timeout_seconds_for_model(model_id)
        return self.request_timeout_seconds

    def _request_timeout_seconds_for_model(self, model_id: str) -> int:
        capabilities = get_model_capabilities(self.provider.name, model_id)
        timeout_value = capabilities.get('default_timeout_seconds')
        if isinstance(timeout_value, int) and timeout_value > 0:
            if capabilities.get('long_running') is True:
                return max(self.request_timeout_seconds, timeout_value * 2)
            return max(self.request_timeout_seconds, timeout_value)
        return self.request_timeout_seconds

    @staticmethod
    def _extract_model_items(data: object) -> list[JsonObject]:
        if isinstance(data, dict):
            for key in ('data', 'models', 'items'):
                raw_items = data.get(key)
                if isinstance(raw_items, list):
                    return [item for item in raw_items if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    @staticmethod
    def _has_model_items(data: object) -> bool:
        return bool(ProviderAdapter._extract_model_items(data))

    @staticmethod
    def _is_openrouter_free_model(item: JsonObject, model_id: str) -> bool:
        if model_id.endswith(':free'):
            return True
        pricing = item.get('pricing')
        if not isinstance(pricing, dict):
            return False
        prompt_raw = pricing.get('prompt', '0')
        completion_raw = pricing.get('completion', '0')
        try:
            prompt_cost = float(str(prompt_raw))
            completion_cost = float(str(completion_raw))
        except (TypeError, ValueError):
            return False
        return prompt_cost == 0 and completion_cost == 0

    @staticmethod
    def _is_supported_gemini_text_model(item: JsonObject, model_id: str) -> bool:
        methods = item.get('supportedGenerationMethods')
        if isinstance(methods, list) and methods and 'generateContent' not in methods:
            return False
        lowered = model_id.lower()
        excluded_tokens = ('image', 'imagen', 'vision', 'embedding', 'aqa')
        return not any(token in lowered for token in excluded_tokens)

    @staticmethod
    def _extract_openai_text(data: object) -> str:
        if not isinstance(data, dict):
            raise ProviderError('返回内容为空或格式不正确')
        choices = data.get('choices')
        if not isinstance(choices, list) or not choices:
            raise ProviderError('返回内容为空或格式不正确')
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ProviderError('返回内容为空或格式不正确')
        message = first_choice.get('message')
        if isinstance(message, dict):
            content = message.get('content')
            if isinstance(content, str) and content.strip():
                return sanitize_model_text(content.strip())
            reasoning_content = message.get('reasoning_content')
            if isinstance(reasoning_content, str) and reasoning_content.strip():
                return sanitize_model_text(reasoning_content.strip())
            if isinstance(content, list):
                chunks: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get('text')
                        if isinstance(text, str) and text.strip():
                            chunks.append(sanitize_model_text(text.strip()))
                merged = '\n'.join(chunks).strip()
                if merged:
                    return merged
        text = first_choice.get('text')
        if isinstance(text, str) and text.strip():
            return sanitize_model_text(text.strip())
        raise ProviderError('返回内容为空或格式不正确')

    @staticmethod
    def _extract_gemini_text(data: object) -> str:
        if not isinstance(data, dict):
            raise ProviderError('返回内容格式不正确')
        candidates = data.get('candidates')
        if not isinstance(candidates, list) or not candidates:
            raise ProviderError('返回内容格式不正确')
        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):
            raise ProviderError('返回内容格式不正确')
        content = first_candidate.get('content')
        if not isinstance(content, dict):
            raise ProviderError('返回内容格式不正确')
        parts = content.get('parts')
        if not isinstance(parts, list):
            raise ProviderError('返回内容格式不正确')
        chunks: list[str] = []
        for item in parts:
            if isinstance(item, dict):
                text = item.get('text')
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
        merged = ''.join(chunks).strip()
        if not merged:
            raise ProviderError('返回内容格式不正确')
        return merged

    @staticmethod
    def _error_message(data: object, fallback: str) -> str:
        if isinstance(data, dict):
            for key in ('error', 'message', 'detail'):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
                if isinstance(value, dict):
                    nested = value.get('message')
                    if isinstance(nested, str) and nested.strip():
                        return nested
        return fallback

    def _raise_http_error(self, status: int, data: object, fallback: str) -> None:
        message = self._error_message(data, fallback)
        failure = classify_error(status, message)
        raise ProviderHTTPError(message=message, status=status, category=failure.category)
