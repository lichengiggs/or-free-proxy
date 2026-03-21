# free_proxy

[中文](README.md) | [English](README_EN.md)

A local AI proxy that aggregates models from OpenRouter / Groq / OpenCode / Gemini / GitHub Models / Mistral / Cerebras / SambaNova and automatically falls back when a model fails.

Built for personal use: simple setup, stable usage.

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

This project now supports 8 providers:

- OpenRouter
- Groq
- OpenCode Zen
- Gemini
- GitHub Models
- Mistral
- Cerebras
- SambaNova

### What the app does now

- The UI saves provider keys in compact cards.
- Model selection is direct: click a model, and it becomes the active one.
- Manual model add no longer asks for a verification step.
- Backend fallback still protects you if a model becomes unavailable.

### Notes for beginners

- This is not a single-model proxy.
- Think of it as a small model router: it tries your chosen model first, then falls back automatically if needed.

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
