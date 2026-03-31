from __future__ import annotations

import json
import time
from dataclasses import dataclass

from .errors import classify_error
from .fallback_policy import FallbackContext, decide_next_action
from .provider_catalog import configured_provider_names, get_provider
from .provider_errors import ProviderError
from .provider_routing import CandidateTarget, build_auto_candidates
from .protocol_converter import gemini_json_to_openai_chat
from .request_normalizer import ChatRequest, normalize_chat_request
from .response_normalizer import RelayResponse, normalize_json_success, normalize_sse_success


@dataclass(frozen=True)
class RelayAttemptResult:
    ok: bool
    provider: str
    model: str
    category: str | None
    status: int | None
    response: RelayResponse | None
    error: str | None


class OpenAIRelay:
    def __init__(self, *, adapter_factory, health_loader, health_ttl_seconds: int, configured_providers_loader=configured_provider_names) -> None:
        self.adapter_factory = adapter_factory
        self.health_loader = health_loader
        self.health_ttl_seconds = health_ttl_seconds
        self.configured_providers_loader = configured_providers_loader

    def normalize(self, payload: dict[str, object]) -> ChatRequest:
        return normalize_chat_request(payload)

    def _adapter_response(self, provider: str, model: str, request: ChatRequest):
        adapter = self.adapter_factory(provider)
        payload = dict(request.raw_payload)
        payload.pop('requested_model', None)
        payload['model'] = model
        payload['stream'] = False
        adapter_response = adapter.forward_chat(payload)
        if get_provider(provider).format == 'gemini' and adapter_response.status < 400 and adapter_response.body is not None:
            body = adapter_response.body or b''
            parsed = json.loads(body.decode('utf-8'))
            return type(
                'AdapterResponse',
                (),
                {
                    'status': adapter_response.status,
                    'headers': {'Content-Type': 'application/json; charset=utf-8'},
                    'body': gemini_json_to_openai_chat(provider, model, parsed),
                    'stream': None,
                    'content_type': 'application/json; charset=utf-8',
                },
            )()
        return adapter_response

    def _append_provider_listed_candidate(self, candidates: list[CandidateTarget], provider: str, insert_at: int) -> list[CandidateTarget]:
        ordered = list(candidates)
        seen = {(item.provider, item.model) for item in ordered}
        adapter = self.adapter_factory(provider)
        list_models = getattr(adapter, 'list_models', None)
        if not callable(list_models):
            return ordered
        try:
            models = list_models()
        except Exception:
            return ordered
        if not models:
            return ordered
        listed_model = models[0]
        key = (provider, listed_model)
        if key in seen:
            return ordered
        ordered.insert(insert_at, CandidateTarget(provider, listed_model, 'provider_default', insert_at))
        return [CandidateTarget(item.provider, item.model, item.source, rank) for rank, item in enumerate(ordered)]

    @staticmethod
    def _extract_openai_text(parsed: object) -> str:
        if not isinstance(parsed, dict):
            return ''
        choices = parsed.get('choices')
        if not isinstance(choices, list) or not choices:
            return ''
        first = choices[0]
        if not isinstance(first, dict):
            return ''
        message = first.get('message')
        if isinstance(message, dict):
            raw_content = message.get('content')
            if isinstance(raw_content, str) and raw_content.strip():
                return raw_content.strip()
            reasoning = message.get('reasoning_content')
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning.strip()
            if isinstance(raw_content, list):
                chunks: list[str] = []
                for item in raw_content:
                    if isinstance(item, dict):
                        text = item.get('text')
                        if isinstance(text, str) and text.strip():
                            chunks.append(text.strip())
                merged = '\n'.join(chunks).strip()
                if merged:
                    return merged
        text = first.get('text')
        if isinstance(text, str) and text.strip():
            return text.strip()
        return ''

    def handle_chat(self, request: ChatRequest) -> RelayResponse:
        candidates = build_auto_candidates(
            requested_model=request.requested_model,
            configured=self.configured_providers_loader(),
            health=self.health_loader(),
            now_ts=int(time.time()),
            ttl_seconds=self.health_ttl_seconds,
        )
        same_provider_attempts = 0
        current_provider = ''
        listed_loaded: set[str] = set()
        index = 0
        while index < len(candidates):
            candidate = candidates[index]
            index += 1
            if candidate.provider == current_provider:
                same_provider_attempts += 1
            else:
                same_provider_attempts = 0
                current_provider = candidate.provider
            try:
                adapter_response = self._adapter_response(candidate.provider, candidate.model, request)
            except ProviderError as exc:
                failure = classify_error(0, str(exc))
                decision = decide_next_action(FallbackContext(index, same_provider_attempts), RelayAttemptResult(False, candidate.provider, candidate.model, failure.category, None, None, str(exc)))
                if decision.action == 'stop':
                    break
                continue
            if adapter_response.status < 400:
                parsed = json.loads((adapter_response.body or b'{}').decode('utf-8'))
                content = self._extract_openai_text(parsed)
                if request.stream and adapter_response.body is not None:
                    return normalize_sse_success(provider=candidate.provider, model=candidate.model, body=adapter_response.body)
                return normalize_json_success(provider=candidate.provider, model=candidate.model, content=content)
            failure = classify_error(adapter_response.status, (adapter_response.body or b'').decode('utf-8', errors='ignore'))
            if candidate.provider not in listed_loaded:
                listed_loaded.add(candidate.provider)
                candidates = self._append_provider_listed_candidate(candidates, candidate.provider, index)
            decision = decide_next_action(FallbackContext(index, same_provider_attempts), RelayAttemptResult(False, candidate.provider, candidate.model, failure.category, adapter_response.status, None, failure.message))
            if decision.action == 'stop':
                break
        error_body = json.dumps(
            {
                'error': {
                    'message': 'all candidates failed',
                    'type': 'server_error',
                    'param': None,
                    'code': '502',
                }
            },
            ensure_ascii=False,
        ).encode('utf-8')
        return RelayResponse(502, {'Content-Type': 'application/json; charset=utf-8'}, error_body, None)
