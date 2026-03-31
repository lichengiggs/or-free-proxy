from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolProtocolResult:
    tool_calls: list[dict[str, object]]
    fallback_text: str | None = None


_LONGCAT_TOOL_BLOCK_PATTERN = re.compile(r'<longcat_tool_call>(?P<body>.*?)</longcat_tool_call>', re.S)
_LONGCAT_ARG_PATTERN = re.compile(
    r'<longcat_arg_key>(?P<key>.*?)</longcat_arg_key>\s*<longcat_arg_value>(?P<value>.*?)</longcat_arg_value>',
    re.S,
)


def _parse_json_value(raw: str) -> object:
    text = raw.strip().rstrip(',')
    if not text:
        return ''
    if not text.startswith('[') and not text.startswith('{'):
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _build_tool_call(provider: str, index: int, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        'id': f'call_{provider}_{index}',
        'type': 'function',
        'function': {
            'name': name,
            'arguments': json.dumps(arguments, ensure_ascii=False),
        },
    }


def parse_provider_tool_protocol(provider: str, text: str) -> ToolProtocolResult | None:
    if provider != 'longcat':
        return None
    if '<longcat_tool_call>' not in text or '<longcat_arg_key>' not in text:
        return None

    prefix = text.split('<longcat_tool_call>', 1)[0].strip()
    tool_name = prefix.splitlines()[0].strip() if prefix else 'tool'
    if not tool_name:
        tool_name = 'tool'

    tool_calls: list[dict[str, object]] = []
    for index, block in enumerate(_LONGCAT_TOOL_BLOCK_PATTERN.finditer(text), start=1):
        body = block.group('body')
        arguments: dict[str, object] = {}
        for arg_match in _LONGCAT_ARG_PATTERN.finditer(body):
            key = arg_match.group('key').strip()
            if not key:
                continue
            arguments[key] = _parse_json_value(arg_match.group('value'))
        if arguments:
            tool_calls.append(_build_tool_call(provider, index, tool_name, arguments))

    if not tool_calls:
        return None

    fallback_text = prefix if prefix and prefix.lower() != tool_name.lower() else None
    return ToolProtocolResult(tool_calls=tool_calls, fallback_text=fallback_text)
