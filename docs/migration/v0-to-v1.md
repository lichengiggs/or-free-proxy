# free-proxy v0 to v1 Migration Guide

## Model Alias Changes

- Removed: `free-proxy/coding`
- Use instead: `free-proxy/auto`
- `coding` / `free-proxy/coding` / `free_proxy/coding` will now return HTTP 400 with `code="model_deprecated"`

## Public API

- Stable endpoints remain:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- `GET /v1/models` now returns only `free-proxy/auto`
- `/chat/completions` is a UI debug route and should not be used as the public integration target

## OpenAI / Python SDK

Replace:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="sk-not-needed")
resp = client.chat.completions.create(
    model="free-proxy/coding",
    messages=[{"role": "user", "content": "Hello"}],
)
```

With:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="sk-not-needed")
resp = client.chat.completions.create(
    model="free-proxy/auto",
    messages=[{"role": "user", "content": "Hello"}],
)
```

## OpenCode

Replace:

```json
{"model":"free-proxy/coding"}
```

With:

```json
{"model":"free-proxy/auto"}
```

When `python_scripts/opencode_config.py` rewrites local config, it now keeps only `auto` and removes legacy `coding` entries.

## OpenClaw

Replace default or fallback values that point to `free-proxy/coding` with `free-proxy/auto`.

When `python_scripts/openclaw_config.py` rewrites local config, it now keeps only `auto` and removes legacy `coding` entries from defaults and fallbacks.

## SDK

Replace:

```python
model="free-proxy/coding"
```

With:

```python
model="free-proxy/auto"
```

## Common Error

If you still send `coding`, the API returns:

```json
{
  "error": {
    "message": "model 'coding' is no longer supported. Use 'free-proxy/auto' instead.",
    "type": "invalid_request_error",
    "param": null,
    "code": "model_deprecated"
  }
}
```

## Local Streaming Verification

If your shell sets `http_proxy` or `https_proxy`, also set:

```bash
NO_PROXY=127.0.0.1,localhost
```

or temporarily clear proxy variables before validating localhost SSE.

Otherwise tools like `curl` or `opencode` may go through a local proxy, receive injected keep-alive headers, and look like the stream never finished even when the relay already sent `data: [DONE]` and closed correctly.

## Beginner Notes

- Start with `free-proxy/auto` if you do not know which model to pick.
- Longcat is usually the easiest first try.
- If Gemini fails, try the Gemini model listed in the README and verify once first.
