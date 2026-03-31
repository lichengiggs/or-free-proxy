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
from .response_normalizer import RelayResponse, normalize_provider_response, sanitize_model_text
from .token_policy import model_default_output_tokens, response_token_budget, trim_prompt


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
    def __init__(
        self,
        *,
        adapter_factory,
        health_loader,
        health_updater=None,
        health_ttl_seconds: int,
        configured_providers_loader=configured_provider_names,
    ) -> None:
        self.adapter_factory = adapter_factory
        self.health_loader = health_loader
        self.health_updater = health_updater
        self.health_ttl_seconds = health_ttl_seconds
        self.configured_providers_loader = configured_providers_loader

    def normalize(self, payload: dict[str, object]) -> ChatRequest:
        return normalize_chat_request(payload)

    @staticmethod
    def _prompt_from_messages(messages: list[dict[str, object]]) -> str:
        parts: list[str] = []
        for item in messages:
            content = item.get('content')
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
                continue
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get('text')
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
        merged = '\n'.join(parts).strip()
        return merged or 'ok'

    @staticmethod
    def _trim_message_content(provider: str, message: dict[str, object]) -> dict[str, object]:
        trimmed = dict(message)
        content = trimmed.get('content')
        if isinstance(content, str) and content.strip():
            trimmed['content'] = trim_prompt(provider, content.strip())
        elif isinstance(content, list):
            blocks: list[dict[str, object]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                copied = dict(block)
                text = copied.get('text')
                if isinstance(text, str) and text.strip():
                    copied['text'] = trim_prompt(provider, text.strip())
                blocks.append(copied)
            if blocks:
                trimmed['content'] = blocks
        return trimmed

    def _payload_for_candidate(self, provider: str, model: str, request: ChatRequest) -> dict[str, object]:
        payload = dict(request.raw_payload)
        payload.pop('requested_model', None)
        payload['model'] = model
        payload['stream'] = False
        payload['messages'] = [self._trim_message_content(provider, message) for message in request.messages]
        default_output = model_default_output_tokens(provider, model, response_token_budget(provider))
        requested_output = request.max_output_tokens if isinstance(request.max_output_tokens, int) and request.max_output_tokens > 0 else default_output
        payload['max_tokens'] = min(requested_output, default_output)
        return payload

    def _adapter_response(self, provider: str, model: str, request: ChatRequest):
        adapter = self.adapter_factory(provider)
        payload = self._payload_for_candidate(provider, model, request)
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

    def _record_health(self, provider: str, model: str, ok: bool, reason: str | None = None) -> None:
        if self.health_updater is None:
            return
        self.health_updater(provider, model, ok, reason)

    @staticmethod
    def _prioritize_interactive_clients(candidates: list[CandidateTarget], request: ChatRequest) -> list[CandidateTarget]:
        client_hint = str(request.raw_payload.get('client_hint', '')).strip().lower()
        if client_hint not in {'opencode', 'openclaw'}:
            return candidates
        provider_priority = {'longcat': 0}
        return sorted(
            candidates,
            key=lambda item: (provider_priority.get(item.provider, 1), item.rank),
        )

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
                return sanitize_model_text(raw_content.strip())
            reasoning = message.get('reasoning_content')
            if isinstance(reasoning, str) and reasoning.strip():
                return sanitize_model_text(reasoning.strip())
            if isinstance(raw_content, list):
                chunks: list[str] = []
                for item in raw_content:
                    if isinstance(item, dict):
                        text = item.get('text')
                        if isinstance(text, str) and text.strip():
                            chunks.append(sanitize_model_text(text.strip()))
                merged = '\n'.join(chunks).strip()
                if merged:
                    return merged
        text = first.get('text')
        if isinstance(text, str) and text.strip():
            return sanitize_model_text(text.strip())
        return ''

    def handle_chat(self, request: ChatRequest) -> RelayResponse:
        candidates = self._prioritize_interactive_clients(
            build_auto_candidates(
            requested_model=request.requested_model,
            configured=self.configured_providers_loader(),
            health=self.health_loader(),
            now_ts=int(time.time()),
            ttl_seconds=self.health_ttl_seconds,
            ),
            request,
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
                self._record_health(candidate.provider, candidate.model, False, failure.category)
                decision = decide_next_action(FallbackContext(index, same_provider_attempts), RelayAttemptResult(False, candidate.provider, candidate.model, failure.category, None, None, str(exc)))
                if decision.action == 'stop':
                    break
                continue
            if adapter_response.status < 400:
                self._record_health(candidate.provider, candidate.model, True, None)
                if adapter_response.body is None:
                    return RelayResponse(200, {'Content-Type': 'application/json; charset=utf-8'}, b'', None)
                return normalize_provider_response(
                    provider=candidate.provider,
                    model=candidate.model,
                    body=adapter_response.body,
                    stream=request.stream,
                )
            failure = classify_error(adapter_response.status, (adapter_response.body or b'').decode('utf-8', errors='ignore'))
            self._record_health(candidate.provider, candidate.model, False, failure.category)
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
