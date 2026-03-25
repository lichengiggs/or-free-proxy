from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPolicy:
    max_input_chars: int
    reserve_output_tokens: int


DEFAULT_POLICY = {
    'github': TokenPolicy(max_input_chars=6000, reserve_output_tokens=256),
    'groq': TokenPolicy(max_input_chars=12000, reserve_output_tokens=384),
    'openrouter': TokenPolicy(max_input_chars=16000, reserve_output_tokens=512),
}


def trim_prompt(provider: str, text: str) -> str:
    policy = DEFAULT_POLICY.get(provider, TokenPolicy(max_input_chars=8000, reserve_output_tokens=256))
    if len(text) <= policy.max_input_chars:
        return text

    head = int(policy.max_input_chars * 0.7)
    tail = policy.max_input_chars - head
    return text[:head] + '\n\n...[内容已截断]...\n\n' + text[-tail:]
