from __future__ import annotations

import unittest

from python_scripts.fallback_policy import FallbackContext, decide_next_action


class RelayAttemptResult:
    def __init__(self, ok: bool, category: str | None) -> None:
        self.ok = ok
        self.category = category


class FallbackPolicyTests(unittest.TestCase):
    def test_rate_limit_moves_to_next_candidate_with_backoff(self) -> None:
        context = FallbackContext(attempt_count=1, same_provider_attempts=1)
        decision = decide_next_action(context, RelayAttemptResult(False, 'rate_limit'))
        self.assertEqual(decision.action, 'next_candidate')
        self.assertGreater(decision.sleep_seconds, 0.0)

    def test_token_limit_retries_same_provider_only_twice(self) -> None:
        context = FallbackContext(attempt_count=2, same_provider_attempts=2)
        decision = decide_next_action(context, RelayAttemptResult(False, 'token_limit'))
        self.assertEqual(decision.action, 'next_candidate')

    def test_auth_stops(self) -> None:
        context = FallbackContext(attempt_count=1, same_provider_attempts=0)
        decision = decide_next_action(context, RelayAttemptResult(False, 'auth'))
        self.assertEqual(decision.action, 'stop')
