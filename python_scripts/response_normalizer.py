from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RelayResponse:
    status: int
    headers: dict[str, str]
    body: bytes | None
    stream_chunks: Iterable[bytes] | None


def _sse_json_line(payload: dict[str, object] | str) -> bytes:
    if isinstance(payload, str):
        return f'data: {payload}\n\n'.encode('utf-8')
    return f'data: {json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}\n\n'.encode('utf-8')


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


def normalize_stream_success(*, provider: str, model: str, body: bytes, content_type: str) -> RelayResponse:
    if 'text/event-stream' in content_type.lower():
        return RelayResponse(200, {'Content-Type': 'text/event-stream; charset=utf-8'}, None, [body])
    parsed = json.loads(body.decode('utf-8'))
    content = ''
    choices = parsed.get('choices')
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get('message')
            if isinstance(message, dict):
                raw_content = message.get('content')
                if isinstance(raw_content, str):
                    content = raw_content
    return RelayResponse(
        200,
        {'Content-Type': 'text/event-stream; charset=utf-8'},
        None,
        [
            _sse_json_line(
                {
                    'id': 'chatcmpl-free-proxy',
                    'object': 'chat.completion.chunk',
                    'created': 1,
                    'model': f'{provider}/{model}',
                    'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': content}, 'finish_reason': None}],
                }
            ),
            _sse_json_line(
                {
                    'id': 'chatcmpl-free-proxy',
                    'object': 'chat.completion.chunk',
                    'created': 1,
                    'model': f'{provider}/{model}',
                    'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
                }
            ),
            b'data: [DONE]\n\n',
        ],
    )
