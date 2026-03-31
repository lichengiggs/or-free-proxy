from __future__ import annotations

from collections.abc import Iterable
import json
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RelayResponse:
    status: int
    headers: dict[str, str]
    body: bytes | None
    stream_chunks: object | None


def _sse_json_line(payload: dict[str, object] | str) -> bytes:
    if isinstance(payload, str):
        return f'data: {payload}\n\n'.encode('utf-8')
    return f'data: {json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}\n\n'.encode('utf-8')


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


def wrap_openai_body_as_sse(*, fallback_model: str, body: bytes) -> Iterable[bytes]:
    parsed = json.loads(body.decode('utf-8'))
    if not isinstance(parsed, dict):
        return [_sse_json_line('[DONE]')]
    choices = parsed.get('choices')
    first_choice = choices[0] if isinstance(choices, list) and choices else {}
    chunk_id = str(parsed.get('id', f'chatcmpl-{int(time.time())}'))
    created_raw = parsed.get('created')
    created = created_raw if isinstance(created_raw, int) else int(time.time())
    actual_model = str(parsed.get('model') or fallback_model)
    delta = _stream_text_delta(first_choice)
    chunks: list[bytes] = []
    if delta:
        chunks.append(
            _sse_json_line(
                {
                    'id': chunk_id,
                    'object': 'chat.completion.chunk',
                    'created': created,
                    'model': actual_model,
                    'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}],
                }
            )
        )
    finish_reason = 'stop'
    if isinstance(first_choice, dict):
        raw_finish_reason = first_choice.get('finish_reason')
        if isinstance(raw_finish_reason, str) and raw_finish_reason:
            finish_reason = raw_finish_reason
    chunks.append(
        _sse_json_line(
            {
                'id': chunk_id,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': actual_model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}],
            }
        )
    )
    chunks.append(_sse_json_line('[DONE]'))
    return chunks


def normalize_json_success(*, provider: str, model: str, content: str) -> RelayResponse:
    now = int(time.time())
    body = json.dumps(
        {
            'id': f'chatcmpl-{now}',
            'object': 'chat.completion',
            'created': now,
            'model': f'{provider}/{model}',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
        },
        ensure_ascii=False,
    ).encode('utf-8')
    return RelayResponse(200, {'Content-Type': 'application/json; charset=utf-8'}, body, None)


def normalize_sse_success(*, provider: str, model: str, body: bytes) -> RelayResponse:
    return RelayResponse(
        200,
        {'Content-Type': 'text/event-stream; charset=utf-8'},
        None,
        wrap_openai_body_as_sse(fallback_model=f'{provider}/{model}', body=body),
    )
