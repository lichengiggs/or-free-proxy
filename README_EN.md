# free-proxy

[中文](README.md) | [English](README_EN.md)

It combines the free tiers of multiple providers into one usable token pool for daily development.

One-line overview: free, easy to use, and enough for everyday OpenClaw usage.

### Free-tier overview

| Option | Stability | Quota | Cost |
|---|---|---|---|
| `free-proxy` | Medium | Estimate ~3.3k requests/day<br>~100k requests/month<br>~300USD/month equivalent | Free |
| US paid coding plan | High | About 200–10,000 requests/month | 20-200USD/month |
| China paid coding plan | High | Lite 18,000 requests/month<br>Pro 90,000 requests/month | 20-200RMB/month |

Note: [Longcat](https://longcat.chat/platform/api-keys) currently offers about 50 million tokens/day on `LongCat-Flash-Lite`, so it is a strong first choice.

## Core features

- Aggregates 9 providers: OpenRouter / Groq / OpenCode / Longcat / Gemini / GitHub Models / Mistral / Cerebras / SambaNova
- Automatic fallback when a model fails or gets rate-limited
- Manual model add with `provider+modelId`
- Local web UI with card-style settings, model selection, and OpenClaw config updates
- OpenAI-compatible endpoint: `http://localhost:8765/v1`

## Quick start

1) First install: clone the repository

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

If you already cloned this repo before, updating is just:

```bash
cd free-proxy
git pull --ff-only
```

2) Install [uv](https://docs.astral.sh/uv/) (if you don't have it yet)

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Homebrew:

```bash
brew install uv
```

3) Go back to the repo root

The next step must run inside the `free-proxy` repo root, where `pyproject.toml` is present.

```bash
cd free-proxy
```

If you are not sure whether you are in the right directory, run this first:

```bash
pwd
ls pyproject.toml
```

If the second command says the file is missing, you are not in the repo root yet. Go back to `free-proxy` first.

4) Sync dependencies

```bash
uv sync
```

If you see `No pyproject.toml found in current directory or any parent directory`, the project is not broken. You are just running the command outside the repo root.

If you are updating from an older version, run `uv sync` again after `git pull --ff-only`.

5) Start the service

```bash
uv run free-proxy serve
```

For beginners: keep this terminal open after startup.

6) Open the setup page and save at least one provider API key

- Visit: `http://localhost:8765`
- After saving a key, start with a recommended model, then click verify or send a quick test request.

## Common integrations

- OpenAI-compatible clients / Python SDK
  - Base URL: `http://127.0.0.1:8765/v1`
  - Model: `free-proxy/auto` for the easiest default
  - If your main use case is coding, switch to `free-proxy/coding`
  - Minimal example:

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

- OpenClaw
  - Provider ID: `free-proxy`
  - Base URL: `http://localhost:8765/v1`
  - Models: `auto`, `coding`
  - Default first choice: `free-proxy/auto`
  - Switch to `free-proxy/coding` if you mainly use it for coding

- Opencode
  - Provider ID: `free-proxy`
  - Config path is usually: `~/.config/opencode/opencode.json`
  - Base URL: `http://localhost:8765/v1`
  - Default command: `opencode run -m free-proxy/auto "Reply with exactly OK"`
  - Coding command: `opencode run -m free-proxy/coding "Reply with exactly OK"`

## Current external behavior

- Standard OpenAI-compatible routes:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- Stable public model aliases:
  - `free-proxy/auto`
  - `free-proxy/coding`
- OpenClaw config writer creates:
  - provider: `free-proxy`
  - models: `auto`, `coding`
- Opencode config writer creates:
  - provider: `free-proxy`
  - models: `auto`, `coding`

If you only want the shortest path:

1. When you are not sure which model to use, start with `free-proxy/auto`
2. If you mainly use it for coding, switch to `free-proxy/coding`

## FAQ

- Network error: make sure `uv run free-proxy serve` is still running, then open `http://localhost:8765`
- Update issues after pulling: run `git pull --ff-only`, then `uv sync`
- `uv sync` says it cannot find `pyproject.toml`: you are in the wrong directory; run `cd free-proxy` first, then confirm with `ls pyproject.toml`
- zsh errors after using GitHub's copy button: copy only the commands inside the code block, not the explanatory text outside it
- No available model: free models may be rate-limited temporarily; click **Refresh model list** first, then try another recommended model
- Where keys are stored: local `.env` file only (not uploaded)
- If an older Opencode config still contains `free_proxy`
  - That is the legacy name
  - The unified name is now `free-proxy`
  - Re-run config writing and use `free-proxy/...`

## Dev commands

Start backend:

```bash
uv run free-proxy serve
```

List subcommands:

```bash
uv run free-proxy --help
```

List models:

```bash
uv run free-proxy models --provider sambanova
```

Probe one model:

```bash
uv run free-proxy probe --provider sambanova --model DeepSeek-V3-0324
```

Run Python tests:

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
```

Frontend / legacy static tests (run `npm install` first if needed):

```bash
npm test
```

## Legacy implementation

- The TypeScript implementation is no longer part of the runtime path; Python is the only active runtime entry now.
- See: `docs/typescript-legacy.md`
- Migration notes: `docs/migration-python-mainline.md`

## License

MIT
