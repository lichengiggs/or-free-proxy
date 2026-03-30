# free-proxy

[中文](README.md) | [English](README_EN.md)

A local OpenAI-compatible gateway that combines multiple free LLM providers behind one stable entrypoint.

Good fit if you want to:
- try multiple free models with less setup friction
- point OpenAI SDK / OpenClaw / Opencode to one local endpoint
- avoid maintaining separate configs for each provider

## What you get

- Local OpenAI-compatible base URL: `http://127.0.0.1:8765/v1`
- Two stable public aliases: `free-proxy/auto`, `free-proxy/coding`
- Automatic provider fallback when one model fails or is rate-limited
- Local web UI for API key setup and model selection

## Recommended starting point

If you only want the fastest path, start with Longcat.

| Provider | Recommended model | Best for | Notes |
|---|---|---|---|
| Longcat | `LongCat-Flash-Lite` | default first choice | easiest starting point, large free quota |
| Gemini | `gemini-3.1-flash-lite-preview` | backup option | stable free tier fallback |
| Mistral | `mistral-large-latest` | stable backup | strong fallback quality |
| GitHub Models | `gpt-4o` / `gpt-4o-mini` | users with Copilot access | quality is high, quota depends on account |
| SambaNova | `DeepSeek-V3.1-Terminus` | extra option | useful as another fallback |

## Quick start in 3 steps

### 1) Clone the repo

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

### 2) Install dependencies

Install [uv](https://docs.astral.sh/uv/) first.

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

or Homebrew:

```bash
brew install uv
```

Then run this inside the repo root:

```bash
uv sync
```

### 3) Start the service and configure keys

Start the service:

```bash
uv run free-proxy serve
```

Open this page:

```text
http://127.0.0.1:8765
```

Then do this in order:
1. Save at least one provider API key
2. Pick a recommended model first
3. Click verify or send a small test message

Beginner tip: keep the terminal window open while the service is running.

## How to use it after setup

### OpenAI SDK / Python

- Base URL: `http://127.0.0.1:8765/v1`
- Default model: `free-proxy/auto`
- Coding model: `free-proxy/coding`

```python
from openai import OpenAI

client = OpenAI(
    api_key="not-needed",
    base_url="http://127.0.0.1:8765/v1",
)

resp = client.chat.completions.create(
    model="free-proxy/auto",
    messages=[{"role": "user", "content": "Reply with exactly OK"}],
)

print(resp.choices[0].message.content)
```

### OpenClaw

- Provider: `free-proxy`
- Base URL: `http://127.0.0.1:8765/v1`
- Models: `auto`, `coding`
- Start with `free-proxy/auto`
- Use `free-proxy/coding` for coding-heavy tasks

### Opencode

- Provider: `free-proxy`
- Base URL: `http://127.0.0.1:8765/v1`

Default test command:

```bash
opencode run -m free-proxy/auto "Reply with exactly OK"
```

Coding command:

```bash
opencode run -m free-proxy/coding "Reply with exactly OK"
```

## Stable public interface

The current stable external surface is:
- `GET /v1/models`
- `POST /v1/chat/completions`
- `free-proxy/auto`
- `free-proxy/coding`

If you only remember one rule:
- start with `free-proxy/auto`
- switch to `free-proxy/coding` for coding work

## FAQ

### `uv sync` says `No pyproject.toml found`
You are not in the repo root.

Run:

```bash
cd free-proxy
ls pyproject.toml
```

If `pyproject.toml` exists, run:

```bash
uv sync
```

### The page does not open or requests fail
First make sure the service is still running:

```bash
uv run free-proxy serve
```

Then open:

```text
http://127.0.0.1:8765
```

### Startup fails after updating
Run these commands in order:

```bash
git pull --ff-only
uv sync
uv run free-proxy serve
```

### No model is available
Free models may be temporarily rate-limited. Refresh the model list first, then try another recommended model.

### Where are API keys stored?
They are stored in the local `.env` file at the project root and are not committed to GitHub.

### I still see `free_proxy` in an old config
That is the legacy name. Use `free-proxy` now.

## Dev commands

Start the service:

```bash
uv run free-proxy serve
```

Show commands:

```bash
uv run free-proxy --help
```

Run Python tests:

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
```

Run frontend / legacy static tests:

```bash
npm test
```

## Legacy notes

- The TypeScript backend is archived and no longer part of the runtime path; Python is the only active runtime entry now.
- Long-term technical overview: `docs/research.md`

## License

MIT
