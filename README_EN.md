# or-free-proxy

[中文](README.md) | [English](README_EN.md)

A local AI proxy that aggregates models from OpenRouter / Groq / OpenCode and automatically falls back when a model fails.

Built for personal use: simple setup, stable usage.

## Features

- Multi-provider support: OpenRouter, Groq, OpenCode
- Automatic fallback across available models
- Manual model add: useful for temporary-free models not marked as free
- Local web UI to save API keys, choose model, and update OpenClaw config
- OpenAI-compatible endpoint: `http://localhost:8765/v1`

## Quick Start

1) Install

```bash
git clone https://github.com/lichengiggs/or-free-proxy.git
cd or-free-proxy
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

Only one provider key is enough to start.

### Step 2: Choose a model

- Click **Refresh model list**
- Select your model
- If unsure, use `openrouter/auto:free`

### Step 3: Manually add a model (optional)

If a model is available but not shown in list:

- Enter `provider + modelId`
- Click **Verify and Add**
- Once verified, it joins fallback candidates

## Use with AI clients

Any OpenAI-compatible client should work (OpenClaw, Cursor, Continue, etc.).

Base URL:

```txt
http://localhost:8765/v1
```

Client API key:

- Any non-empty string is fine on client side
- Real provider keys are managed by this proxy

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
