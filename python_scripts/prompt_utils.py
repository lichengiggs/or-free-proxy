from __future__ import annotations


def message_to_text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get('text')
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        merged = '\n'.join(parts).strip()
        if merged:
            return merged
    return ''


def extract_prompt(payload: dict[str, object]) -> str:
    messages = payload.get('messages')
    if isinstance(messages, list) and messages:
        parts: list[str] = []
        for item in messages:
            if isinstance(item, dict):
                content = item.get('content')
                text = message_to_text(content)
                if text:
                    parts.append(text)
        merged = '\n'.join(parts).strip()
        if merged:
            return merged
    prompt = payload.get('prompt')
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()
    return 'ok'
