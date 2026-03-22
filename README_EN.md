# free_proxy

[中文](README.md) | [English](README_EN.md)

OpenClaw's free token pool: 8 providers, free, fast, and stable enough for daily use.

It pools the free tiers of OpenRouter / Groq / OpenCode / Gemini / GitHub Models / Mistral / Cerebras / SambaNova into one usable stack.

Available free models include `DeepSeek-V3.2`, `gemini-3.1-flash-lite`, `kimi-k2`, `GLM 4.5 Air`, `Step 3.5 Flash`, and `GPT-4o Mini`.

### Free-tier highlight

| Option | Stability | Quota | Cost |
|---|---:|---|---:|
| `free_proxy` | Medium, with fallback protection | Estimate: ~3.3k requests/day (~100k requests/month); equivalent value ~300USD/month; supports concurrent use (3–5 devs). Based on 2026-03 audit of configured providers and keys. | Free |
| US paid coding plan (OpenAI example) | High | Approx: 200–10,000 1k-token calls/month (representing ~20–200USD/month spending; estimate) | 20-200USD/month |
| China paid coding plan (Alibaba Coding Plan) | High | Lite: 18,000 requests/month; Pro: 90,000 requests/month (official plan limits) | Lite: 7.9RMB (first month); Pro: 39.9RMB (first month) |

free_proxy gives OpenClaw a free token path first, then keeps requests flowing with fallback.

Quota numbers are conservative estimates and vary by provider/region/account; free_proxy aggregates free tiers — actual results depend on upstream limits. Sources: OpenAI pricing: https://platform.openai.com/pricing, Anthropic pricing: https://www.anthropic.com/pricing, Alibaba Coding Plan reference: https://developer.aliyun.com/article/1713813

## Features

- 8 provider support: OpenRouter, Groq, OpenCode, Gemini, GitHub Models, Mistral, Cerebras, SambaNova
- Automatic fallback across available models
- Manual model add: directly save a model that is temporarily free or not marked correctly
- Local web UI with card-style provider setup, direct model selection, and OpenClaw config
- OpenAI-compatible endpoint: `http://localhost:8765/v1`

## Quick Start

1) Install

```bash
git clone https://github.com/lichengiggs/free_proxy.git
cd free_proxy
npm install
```

2) Start

```bash
npm start
```

3) Open setup page

- Visit: `http://localhost:8765`
- Save at least one provider API key
- Select a model (recommended: `openrouter/auto:free`)

## Setup Guide

### Step 1: Save API Key(s)

- OpenRouter: https://openrouter.ai/keys
- Groq: https://console.groq.com/keys
- OpenCode: https://opencode.ai/auth
- Gemini: https://aistudio.google.com/app/apikey
- GitHub Models: https://github.com/settings/tokens
- Mistral: https://console.mistral.ai/api-keys
- Cerebras: https://cloud.cerebras.ai/
- SambaNova: https://cloud.sambanova.ai/

Only one provider key is enough to start.

### Step 2: Choose a model

- Click **Refresh model list**
- Select your model
- If unsure, use `openrouter/auto:free`

### Step 3: Manually add a model (optional)

If a model is available but not shown in list:

- Enter `provider + modelId`
- Click **Add**
- It will be saved directly, and fallback will handle unavailable cases

## Use with AI clients

Any OpenAI-compatible client should work (OpenClaw, Cursor, Continue, etc.).

Base URL:

```txt
http://localhost:8765/v1
```

Client API key:

- Any non-empty string is fine on client side
- Real provider keys are managed by this proxy

## Current status

This project supports 8 providers: OpenRouter, Groq, OpenCode Zen, Gemini, GitHub Models, Mistral, Cerebras, and SambaNova.

### What the app does now

- The UI saves provider keys in compact cards.
- Model selection is direct: click a model, and it becomes active.
- Manual model add no longer asks for verification.
- Backend fallback still protects you if a model becomes unavailable.

## OpenClaw (optional)

Use **Update OpenClaw Config** in the web UI.
It updates `~/.openclaw/openclaw.json` and creates backups automatically.

## FAQ

### "Network error" when saving API key

- Ensure server is running: `npm start`
- Open the UI with `http://localhost:8765` (avoid mixing with 127.0.0.1)

### "No available model"

- Free models may be rate-limited temporarily
- Refresh model list and retry
- Or manually add a known-available model

### Where are API keys stored?

- In local `.env` file at project root
- Not uploaded automatically

## Dev commands

```bash
npm start
npm test
npx tsc --noEmit
```

## License

MIT
