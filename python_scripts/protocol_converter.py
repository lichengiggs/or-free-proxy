from __future__ import annotations

import json
import time


def _extract_gemini_text(payload: dict[str, object]) -> str:
    candidates = payload.get('candidates')
    if not isinstance(candidates, list) or not candidates:
        return ''
    first = candidates[0]
    if not isinstance(first, dict):
        return ''
    content = first.get('content')
    if not isinstance(content, dict):
        return ''
    parts = content.get('parts')
    if not isinstance(parts, list):
        return ''
    chunks: list[str] = []
    for item in parts:
        if isinstance(item, dict):
            text = item.get('text')
            if isinstance(text, str):
                chunks.append(text)
    return ''.join(chunks)


def gemini_json_to_openai_chat(provider: str, model: str, payload: dict[str, object]) -> bytes:
    now = int(time.time())
    return json.dumps(
        {
            'id': f'chatcmpl-{now}',
            'object': 'chat.completion',
            'created': now,
            'model': f'{provider}/{model}',
            'choices': [
                {
                    'index': 0,
                    'message': {'role': 'assistant', 'content': _extract_gemini_text(payload)},
                    'finish_reason': 'stop',
                }
            ],
            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
        },
        ensure_ascii=False,
    ).encode('utf-8')
