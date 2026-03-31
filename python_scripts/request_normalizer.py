from __future__ import annotations

from dataclasses import dataclass

AUTO_ALIASES = {'auto', 'free-proxy/auto', 'free_proxy/auto'}
CODING_ALIASES = {'coding', 'free-proxy/coding', 'free_proxy/coding'}


@dataclass(frozen=True)
class ChatRequest:
    public_model: str
    requested_model: str | None
    messages: list[dict[str, object]]
    stream: bool
    max_output_tokens: int | None
    temperature: float | None
    raw_payload: dict[str, object]


def _normalized_max_tokens(payload: dict[str, object]) -> int | None:
    for key in ('max_tokens', 'max_completion_tokens', 'max_output_tokens'):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def _normalized_messages(payload: dict[str, object]) -> list[dict[str, object]]:
    messages = payload.get('messages')
    if not isinstance(messages, list) or not messages:
        raise ValueError('messages must not be empty')
    normalized: list[dict[str, object]] = []
    for item in messages:
        if isinstance(item, dict):
            normalized.append(dict(item))
    if not normalized:
        raise ValueError('messages must not be empty')
    return normalized


def normalize_chat_request(payload: dict[str, object]) -> ChatRequest:
    model = str(payload.get('model', '')).strip()
    if model in CODING_ALIASES:
        raise ValueError("model 'coding' is no longer supported. Use 'free-proxy/auto' instead.")
    if model not in AUTO_ALIASES:
        raise ValueError("model must be 'free-proxy/auto'")
    requested_model = str(payload.get('requested_model', '')).strip() or None
    temperature = payload.get('temperature')
    return ChatRequest(
        public_model='free-proxy/auto',
        requested_model=requested_model,
        messages=_normalized_messages(payload),
        stream=bool(payload.get('stream')),
        max_output_tokens=_normalized_max_tokens(payload),
        temperature=float(temperature) if isinstance(temperature, (int, float)) else None,
        raw_payload=dict(payload),
    )
