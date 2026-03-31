from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FallbackAction = Literal['stop', 'retry_same_provider', 'next_candidate']


@dataclass(frozen=True)
class FallbackContext:
    attempt_count: int
    same_provider_attempts: int
    max_same_provider_attempts: int = 2
    max_total_attempts: int = 5
    backoff_multiplier: float = 1.5


@dataclass(frozen=True)
class FallbackDecision:
    action: FallbackAction
    sleep_seconds: float = 0.0


def decide_next_action(context: FallbackContext, attempt) -> FallbackDecision:
    if attempt.ok:
        return FallbackDecision('stop')
    if context.attempt_count >= context.max_total_attempts:
        return FallbackDecision('stop')
    if attempt.category == 'auth':
        return FallbackDecision('stop')
    if attempt.category == 'token_limit':
        if context.same_provider_attempts < context.max_same_provider_attempts:
            return FallbackDecision('retry_same_provider')
        return FallbackDecision('next_candidate')
    if attempt.category == 'rate_limit':
        return FallbackDecision('next_candidate', 0.5 * (context.backoff_multiplier ** context.attempt_count))
    if attempt.category in {'quota', 'model_not_found', 'network', 'server'}:
        return FallbackDecision('next_candidate')
    return FallbackDecision('stop')
