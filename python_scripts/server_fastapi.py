from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .opencode_config import configure_opencode_provider, detect_opencode_config
from .openclaw_config import configure_openclaw_model, detect_openclaw_config, list_backups, restore_backup
from .provider_errors import ProviderError
from .service import ProxyService

logger = logging.getLogger('free-proxy')

app = FastAPI(title='free-proxy')

_web_root = Path(__file__).resolve().parent / 'web'
app.mount('/web', StaticFiles(directory=str(_web_root)), name='web')

_service: ProxyService | None = None
_debug_enabled = False


def _debug_log(event: str, **fields: object) -> None:
    if not _debug_enabled:
        return
    parts = [f'event={event}']
    for key, value in fields.items():
        if key == 'messages' or key == 'prompt':
            continue
        parts.append(f'{key}={value}')
    logger.info(' '.join(parts))


def get_service() -> ProxyService:
    global _service
    if _service is None:
        _service = ProxyService(debug_log=_debug_log)
    return _service


def set_debug(enabled: bool) -> None:
    global _debug_enabled
    _debug_enabled = enabled
    if enabled:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s %(name)s: %(message)s',
            stream=sys.stderr,
        )


@app.middleware('http')
async def log_requests(request: Request, call_next):
    if _debug_enabled:
        _debug_log(
            'request_received',
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else 'unknown',
        )
    response = await call_next(request)
    if _debug_enabled:
        _debug_log(
            'request_completed',
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
    return response


@app.get('/')
async def index():
    return FileResponse(str(_web_root / 'index.html'))


@app.get('/health')
async def health():
    return {'ok': True}


@app.get('/v1/models')
async def list_models():
    svc = get_service()
    return {'object': 'list', 'data': svc.public_models()}


@app.get('/api/provider-keys')
async def get_provider_keys():
    svc = get_service()
    return svc.provider_key_statuses()


@app.get('/api/preferred-model')
async def get_preferred_model():
    svc = get_service()
    current = svc.preferred_model()
    if current:
        provider, model = current.split('/', 1)
        return {'ok': True, 'provider': provider, 'model': model, 'requested_model': current}
    return {'ok': True, 'provider': None, 'model': None, 'requested_model': None}


@app.post('/api/preferred-model')
async def save_preferred_model(request: Request):
    payload = await request.json()
    provider = str(payload.get('provider', '')).strip()
    model = str(payload.get('model', '')).strip()
    if not provider or not model:
        return JSONResponse({'ok': False, 'error': 'missing provider or model'}, status_code=400)
    svc = get_service()
    try:
        result = svc.save_preferred_model(provider, model)
        return result
    except ProviderError as exc:
        return JSONResponse({'ok': False, 'error': str(exc)}, status_code=400)


@app.get('/api/providers/{provider}/models/recommended')
async def recommended_models(provider: str, model: str | None = None):
    svc = get_service()
    items = svc.recommended_models(provider, requested_model=model)
    return {'provider': provider, 'items': items}


@app.get('/api/detect-openclaw')
async def detect_openclaw():
    return detect_openclaw_config()


@app.get('/api/detect-opencode')
async def detect_opencode():
    return detect_opencode_config()


@app.get('/api/backups')
async def list_backups_route():
    return {'backups': list_backups()}


@app.get('/providers')
async def list_providers():
    svc = get_service()
    return {'providers': svc.available_providers()}


@app.get('/providers/{provider}/models')
async def provider_models(provider: str):
    svc = get_service()
    try:
        models = svc.list_models(provider)
        return {'provider': provider, 'models': models}
    except ProviderError as exc:
        return JSONResponse({'ok': False, 'error': str(exc)}, status_code=400)


@app.post('/api/provider-keys/{provider}/verify')
async def verify_provider_key(provider: str):
    svc = get_service()
    result = svc.verify_provider_key(provider)
    return JSONResponse(result, status_code=200 if result.get('ok') else 400)


@app.post('/api/configure-openclaw')
async def configure_openclaw(request: Request):
    payload = await request.json()
    mode = str(payload.get('mode', '')).strip()
    if mode not in {'default', 'fallback'}:
        return JSONResponse({'success': False, 'error': 'Invalid mode'}, status_code=400)
    svc = get_service()
    statuses = svc.provider_key_statuses()
    has_any_configured = any(bool(item.get('configured')) for item in statuses.values())
    if not has_any_configured:
        return JSONResponse({'success': False, 'error': 'Please configure at least one provider API key first'}, status_code=400)
    raw_port = os.environ.get('PORT', str(settings.port)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = settings.port
    result = configure_openclaw_model(mode, port=port)
    if not result.get('success'):
        return JSONResponse(result, status_code=400)
    message = '已设为 OpenClaw 默认模型' if mode == 'default' else '已加入 OpenClaw 备用模型'
    return {'success': True, 'backup': result.get('backup'), 'message': message}


@app.post('/api/configure-opencode')
async def configure_opencode(request: Request):
    svc = get_service()
    statuses = svc.provider_key_statuses()
    has_any_configured = any(bool(item.get('configured')) for item in statuses.values())
    if not has_any_configured:
        return JSONResponse({'success': False, 'error': 'Please configure at least one provider API key first'}, status_code=400)
    raw_port = os.environ.get('PORT', str(settings.port)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = settings.port
    result = configure_opencode_provider(port=port)
    if not result.get('success'):
        return JSONResponse(result, status_code=400)
    return {'success': True, 'backup': result.get('backup'), 'message': '已写入 Opencode free-proxy provider'}


@app.post('/api/restore-backup')
async def restore_backup_route(request: Request):
    payload = await request.json()
    backup = str(payload.get('backup', '')).strip()
    if not backup:
        return JSONResponse({'success': False, 'error': 'Backup filename is required'}, status_code=400)
    result = restore_backup(backup)
    if not result.get('success'):
        return JSONResponse(result, status_code=400)
    return {'success': True, 'message': 'Restore successful'}


@app.post('/api/provider-keys/{provider}')
async def save_provider_key(provider: str, request: Request):
    payload = await request.json()
    api_key = str(payload.get('api_key', '')).strip()
    if not api_key:
        return JSONResponse({'ok': False, 'error': 'missing api_key'}, status_code=400)
    svc = get_service()
    try:
        result = svc.save_provider_key(provider, api_key)
        return result
    except ProviderError as exc:
        return JSONResponse({'ok': False, 'error': str(exc)}, status_code=400)


@app.post('/providers/{provider}/probe')
async def probe_provider(provider: str, request: Request):
    payload = await request.json()
    model = str(payload.get('model', '')).strip()
    if not model:
        return JSONResponse({'ok': False, 'error': 'missing model'}, status_code=400)
    svc = get_service()
    try:
        result = svc.probe(provider, model)
        if _debug_enabled:
            _debug_log(
                'probe_result',
                provider=provider,
                model=model,
                ok=result.ok,
                actual_model=result.actual_model,
                error=result.error,
                category=result.category,
                status=result.status,
            )
        return JSONResponse(result.__dict__, status_code=200 if result.ok else 400)
    except Exception as exc:
        if _debug_enabled:
            _debug_log(
                'probe_error',
                provider=provider,
                model=model,
                error=str(exc),
            )
        return JSONResponse({'ok': False, 'error': str(exc)}, status_code=500)


@app.post('/chat/completions')
async def legacy_chat_completions(request: Request):
    payload = await request.json()
    provider = str(payload.get('provider', '')).strip()
    model = str(payload.get('model', '')).strip()
    if not provider or not model:
        return JSONResponse({'ok': False, 'error': 'missing provider or model'}, status_code=400)
    svc = get_service()
    stream = bool(payload.get('stream'))
    if _debug_enabled:
        _debug_log(
            'chat_completions_request',
            provider=provider,
            model=model,
            stream=stream,
        )
    if stream:
        try:
            result = svc.forward_direct_chat(provider, model, payload)
            if _debug_enabled:
                _debug_log(
                    'chat_completions_result',
                    provider=provider,
                    model=model,
                    ok=result.ok,
                    status=result.status,
                    has_body=bool(result.body),
                    has_stream=bool(result.stream_chunks),
                    content_length=len(result.body) if result.body else 0,
                    error=result.error,
                )
            if result.ok and result.stream_chunks is not None:
                return StreamingResponse(
                    _iter_chunks(result.stream_chunks),
                    media_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'},
                )
            if result.ok and result.body:
                try:
                    parsed_body = json.loads(result.body)
                    if _debug_enabled:
                        _debug_log(
                            'chat_completions_body_preview',
                            provider=provider,
                            model=model,
                            body_preview=str(result.body[:300], 'utf-8', errors='ignore'),
                        )
                    return JSONResponse(content=parsed_body)
                except json.JSONDecodeError as exc:
                    if _debug_enabled:
                        _debug_log(
                            'chat_completions_json_decode_error',
                            provider=provider,
                            model=model,
                            error=str(exc),
                            body_preview=str(result.body[:300], 'utf-8', errors='ignore'),
                        )
                    return JSONResponse({'ok': False, 'error': 'upstream returned invalid JSON'}, status_code=502)
            if result.ok and not result.body and result.content:
                return {'ok': True, 'provider': provider, 'model': model, 'actual_model': result.actual_model or model, 'content': result.content}
            if not result.ok:
                if _debug_enabled:
                    _debug_log(
                        'chat_completions_error',
                        provider=provider,
                        model=model,
                        error=result.error,
                        category=result.category,
                        status=result.status,
                    )
                return JSONResponse({
                    'ok': False,
                    'provider': provider,
                    'model': model,
                    'error': result.error,
                    'category': result.category,
                    'status': result.status,
                    'suggestion': result.suggestion,
                }, status_code=result.status or 400)
        except ProviderError as exc:
            if _debug_enabled:
                _debug_log(
                    'chat_completions_exception',
                    provider=provider,
                    model=model,
                    error=str(exc),
                )
            return JSONResponse({'ok': False, 'provider': provider, 'model': model, 'error': str(exc)}, status_code=400)
        except Exception as exc:
            if _debug_enabled:
                _debug_log(
                    'chat_completions_unexpected_error',
                    provider=provider,
                    model=model,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            return JSONResponse({'ok': False, 'provider': provider, 'model': model, 'error': str(exc)}, status_code=500)
    prompt = _extract_prompt_from_payload(payload)
    result = svc.chat(provider, model, prompt)
    if result.ok:
        return {'ok': True, 'provider': provider, 'model': model, 'actual_model': result.actual_model or model, 'content': result.content}
    return JSONResponse({
        'ok': False,
        'provider': provider,
        'model': model,
        'error': result.error,
        'category': result.category,
        'status': result.status,
        'suggestion': result.suggestion,
    }, status_code=400)


@app.post('/v1/chat/completions')
async def openai_chat_completions(request: Request):
    payload = await request.json()
    user_agent = request.headers.get('User-Agent', '')
    client_hint = 'opencode' if 'opencode' in user_agent.lower() else 'openclaw' if 'openclaw' in user_agent.lower() else ''
    try:
        payload = dict(payload)
        payload['client_hint'] = client_hint
        svc = get_service()
        relay = svc.openai_relay()
        req = relay.normalize(payload)
    except ValueError as exc:
        error_code = 'model_deprecated' if 'no longer supported' in str(exc) else None
        return JSONResponse(
            {'error': {'message': str(exc), 'type': 'invalid_request_error', 'param': None, 'code': error_code}},
            status_code=400,
        )

    result = relay.handle_chat(req)

    if result.stream_chunks is not None:
        return StreamingResponse(
            _iter_chunks(result.stream_chunks),
            media_type=result.headers.get('Content-Type', 'text/event-stream'),
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'},
        )
    if result.body is not None:
        return JSONResponse(content=json.loads(result.body), headers=dict(result.headers))
    return JSONResponse(content=b'', status_code=result.status or 200)


async def _iter_chunks(chunks):
    for chunk in chunks:
        yield chunk


def _extract_prompt_from_payload(payload: dict) -> str:
    from .prompt_utils import extract_prompt
    return extract_prompt(payload)
