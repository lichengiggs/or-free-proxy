# free_proxy

[中文](README.md) | [English](README_EN.md)

It combines the free tiers of multiple providers into one usable token pool for daily development.

One-line overview: free, easy to use, and enough for everyday OpenClaw usage.

### Free-tier overview

| Option | Stability | Quota | Cost |
|---|---:|---|---:|
| `free_proxy` | Medium | Estimate: ~3.3k requests/day (~100k/month), about 300USD/month equivalent, supports 3–5 concurrent users | Free |
| US paid coding plan | High | About 200–10,000 requests/month | 20-200USD/month |
| China paid coding plan | High | Lite: 18,000 requests/month; Pro: 90,000 requests/month | 20-200RMB/month |

## Core features

- Aggregates 8 providers: OpenRouter / Groq / OpenCode / Gemini / GitHub Models / Mistral / Cerebras / SambaNova
- Automatic fallback when a model fails or gets rate-limited
- Manual model add with `provider+modelId`
- Local web UI with card-style settings, model selection, and OpenClaw config updates
- OpenAI-compatible endpoint: `http://localhost:8765/v1`

## Quick start (3 steps)

1) Clone and install dependencies

```bash
git clone https://github.com/lichengiggs/free_proxy.git
cd free_proxy
npm install
```

2) Start

```bash
npm start
```

For beginners: after running `npm start`, keep this terminal open.

3) Open the setup page and save at least one provider API key

- Visit: `http://localhost:8765`
- After saving a key, you can pick a model and start using it

## FAQ

- Network error: make sure the service is running with `npm start`, then open `http://localhost:8765`
- No available model: free models may be rate-limited temporarily; click **Refresh model list** or add a known-available model manually
- Where keys are stored: local `.env` file only (not uploaded)

## Dev commands

```bash
# start
npm start

# test
npm test

python3 test_proxy.py
```

## License

MIT
