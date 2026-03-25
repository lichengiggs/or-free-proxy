from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import ProviderSpec, get_provider_model_hints, get_provider_required_query
from .errors import classify_error


def build_url(base_url: str, path: str, query: dict[str, str] | None = None) -> str:
    base = base_url.rstrip('/')
    normalized_path = path if path.startswith('/') else f'/{path}'
    if not query:
        return f'{base}{normalized_path}'
    return f'{base}{normalized_path}?{urlencode(query)}'


class Transport(Protocol):
    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
        ...


class UrlLibTransport:
    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
        request = Request(url=url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read()
        except URLError as exc:  # pragma: no cover - network layer
            raise ProviderError(f'网络连接失败: {exc.reason}') from exc


@dataclass
class ProviderClient:
    spec: ProviderSpec
    api_key: str
    transport: Transport | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            self.transport = UrlLibTransport()

    def _headers(self) -> dict[str, str]:
        if self.spec.format == 'gemini':
            return {
                'Content-Type': 'application/json',
                'x-goog-api-key': self.api_key,
            }
        if self.spec.name == 'github':
            return {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
                'X-GitHub-Api-Version': '2024-12-01-preview',
            }
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None, query: dict[str, str] | None = None) -> tuple[int, dict[str, str], Any]:
        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        status, headers, raw = self.transport.request(method, build_url(self.spec.base_url, path, query), self._headers(), body)
        text = raw.decode('utf-8') if raw else ''
        data: Any = None
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = text
        return status, headers, data

    def list_models(self) -> list[str]:
        status, _, data = self._request_json('GET', '/models')
        if status >= 400:
            if self.spec.name in {'github', 'cerebras', 'groq'}:
                return get_provider_model_hints(self.spec.name)
            self._raise_http_error(status, data, '获取模型失败')

        if self.spec.name in {'github', 'cerebras', 'groq'} and (not data or not isinstance(data, (dict, list))):
            return get_provider_model_hints(self.spec.name)

        models: list[dict[str, Any]] = []
        if isinstance(data, dict):
            for key in ('data', 'models', 'items'):
                value = data.get(key)
                if isinstance(value, list):
                    models = [item for item in value if isinstance(item, dict)]
                    break
        elif isinstance(data, list):
            models = [item for item in data if isinstance(item, dict)]

        ids: list[str] = []
        for item in models:
            model_id = item.get('id') or item.get('name')
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            if self.spec.name == 'openrouter' and not self._is_openrouter_free_model(item, model_id):
                continue
            ids.append(self.normalize_model_id(model_id))
        return ids

    @staticmethod
    def _is_openrouter_free_model(item: dict[str, Any], model_id: str) -> bool:
        if model_id.endswith(':free'):
            return True

        pricing = item.get('pricing')
        if not isinstance(pricing, dict):
            pricing = {}

        prompt_raw = pricing.get('prompt', '0')
        completion_raw = pricing.get('completion', '0')
        try:
            prompt_cost = float(str(prompt_raw))
            completion_cost = float(str(completion_raw))
        except (TypeError, ValueError):
            return False
        return prompt_cost == 0 and completion_cost == 0

    def chat(self, model_id: str, prompt: str = 'ok') -> str:
        if self.spec.format == 'gemini':
            return self._chat_gemini(model_id, prompt)
        return self._chat_openai(model_id, prompt)

    def probe(self, model_id: str) -> dict[str, Any]:
        content = self.chat(model_id, 'ok')
        return {'ok': True, 'content': content}

    def _chat_openai(self, model_id: str, prompt: str) -> str:
        payload = {
            'model': model_id,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0,
            'max_tokens': 8,
        }
        query = get_provider_required_query(self.spec.name)
        status, _, data = self._request_json('POST', '/chat/completions', payload, query=query)
        if status >= 400:
            self._raise_http_error(status, data, '连通失败')
        try:
            return str(data['choices'][0]['message']['content']).strip()
        except Exception as exc:  # pragma: no cover - defensive
            raise ProviderError('返回内容格式不正确') from exc

    def _chat_gemini(self, model_id: str, prompt: str) -> str:
        payload = {
            'contents': [{
                'role': 'user',
                'parts': [{'text': prompt}],
            }],
            'generationConfig': {'temperature': 0, 'maxOutputTokens': 32},
        }
        path = f'/models/{self.normalize_model_id(model_id)}:generateContent'
        status, _, data = self._request_json('POST', path, payload)
        if status >= 400:
            self._raise_http_error(status, data, '连通失败')
        try:
            candidates = data['candidates']
            parts = candidates[0]['content'].get('parts') or []
            text = ''.join(str(part.get('text', '')) for part in parts if isinstance(part, dict)).strip()
            if not text:
                raise KeyError('missing text')
            return text
        except Exception as exc:  # pragma: no cover - defensive
            raise ProviderError('返回内容格式不正确') from exc

    def normalize_model_id(self, model_id: str) -> str:
        if self.spec.format == 'gemini' and model_id.startswith('models/'):
            return model_id.removeprefix('models/')
        return model_id

    @staticmethod
    def _error_message(data: Any, fallback: str) -> str:
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

    def _raise_http_error(self, status: int, data: Any, fallback: str) -> None:
        message = self._error_message(data, fallback)
        failure = classify_error(status, message)
        raise ProviderHTTPError(message=message, status=status, category=failure.category)


class ProviderError(RuntimeError):
    pass


class ProviderHTTPError(ProviderError):
    def __init__(self, *, message: str, status: int, category: str) -> None:
        super().__init__(message)
        self.status = status
        self.category = category
