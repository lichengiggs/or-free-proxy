# free-proxy

中文 | English

A local OpenAI-compatible entrypoint that combines multiple free LLM providers. Add one API key and start using it.

This project is best for:

1. People who want to try multiple free models at low cost
2. People who want one local entrypoint for OpenAI SDK / OpenClaw / Opencode
3. People who do not want to maintain separate provider configs by hand

## What you get

- A local OpenAI-compatible base URL: `http://127.0.0.1:8765/v1`
- Two stable model aliases: `free-proxy/auto`, `free-proxy/coding`
- Automatic provider fallback when one model fails
- A local web page for API key setup, so you do not need to edit config files by hand

## Install free-proxy

Clone the project to your machine:

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

Start the service:

```bash
uv run free-proxy serve
```

Open the page:

```text
http://127.0.0.1:8765
```

## Upgrade free-proxy

If you already installed it, run this inside the project folder:

```bash
git pull --ff-only
uv sync
uv run free-proxy serve
```

## Quick start in 3 steps

1. Save at least one provider API key
2. Pick a recommended model first
3. Click verify, or send a small test message

Beginner tip: keep the terminal window open while the service is running.

## Which model to choose

If you only want the fastest path, start with Longcat.

| Provider | Recommended model | Best for | Notes |
|---|---|---|---|
| Longcat | `LongCat-Flash-Lite` | default first choice | easiest starting point, large free quota |
| Gemini | `gemini-3.1-flash-lite-preview` | backup option | stable free tier fallback |
| Mistral | `mistral-large-latest` | stable backup | strong fallback quality |
| GitHub Models | `gpt-4o` / `gpt-4o-mini` | users with Copilot access | quality is high, quota depends on account |
| SambaNova | `DeepSeek-V3.1-Terminus` | extra option | useful as another fallback |

If you only remember one rule:

- Not sure: `free-proxy/auto`
- Mostly coding: `free-proxy/coding`

## Troubleshooting logs

If you want more detailed debugging output, start with:

```bash
uv run free-proxy serve --debug
```

## FAQ

### The page does not open

Make sure the service is still running, then refresh the page.

### No model is available

Try another recommended model first.

### Where are API keys stored?

They are stored in the project root `.env` file and are not committed to GitHub.

## Thanks

This project tries to keep the hard parts behind the scenes so beginners can get started quickly.

## License

MIT
