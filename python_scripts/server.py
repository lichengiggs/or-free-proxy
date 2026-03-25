from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_scripts.client import ProviderError
from python_scripts.openclaw_config import configure_openclaw_model, detect_openclaw_config, list_backups, restore_backup
from python_scripts.service import ProxyService


class ApiHandler(BaseHTTPRequestHandler):
    service = ProxyService()
    web_root = Path(__file__).resolve().parent / 'web'

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self._send_json(404, {'ok': False, 'error': 'not found'})
            return
        body = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {'/', '/index.html', '/ui'}:
            self._send_file(self.web_root / 'index.html')
            return

        if parsed.path.startswith('/web/'):
            rel = parsed.path.removeprefix('/web/')
            if '..' in rel:
                self._send_json(400, {'ok': False, 'error': 'invalid path'})
                return
            self._send_file(self.web_root / rel)
            return

        if parsed.path == '/health':
            self._send_json(200, {'ok': True})
            return

        if parsed.path == '/api/provider-keys':
            self._send_json(200, self.service.provider_key_statuses())
            return

        if parsed.path.startswith('/api/providers/') and parsed.path.endswith('/models/recommended'):
            provider = parsed.path.split('/')[3]
            query = parse_qs(parsed.query)
            requested_model = (query.get('model') or [''])[0].strip() or None
            items = self.service.recommended_models(provider, requested_model=requested_model)
            self._send_json(200, {'provider': provider, 'items': items})
            return

        if parsed.path == '/api/detect-openclaw':
            self._send_json(200, detect_openclaw_config())
            return

        if parsed.path == '/api/backups':
            self._send_json(200, {'backups': list_backups()})
            return

        if parsed.path == '/providers':
            self._send_json(200, {'providers': self.service.available_providers()})
            return
        if parsed.path.startswith('/providers/') and parsed.path.endswith('/models'):
            provider = parsed.path.split('/')[2]
            try:
                models = self.service.list_models(provider)
                self._send_json(200, {'provider': provider, 'models': models})
            except ProviderError as exc:
                self._send_json(400, {'ok': False, 'error': str(exc)})
            return
        self._send_json(404, {'ok': False, 'error': 'not found'})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(length) if length > 0 else b'{}'
        try:
            payload = json.loads(body.decode('utf-8')) if body else {}
        except json.JSONDecodeError:
            self._send_json(400, {'ok': False, 'error': 'invalid json'})
            return

        if parsed.path.startswith('/api/provider-keys/') and parsed.path.endswith('/verify'):
            provider = parsed.path.split('/')[3]
            result = self.service.verify_provider_key(provider)
            self._send_json(200 if result.get('ok') else 400, result)
            return

        if parsed.path == '/api/configure-openclaw':
            mode = str(payload.get('mode', '')).strip()
            if mode not in {'default', 'fallback'}:
                self._send_json(400, {'success': False, 'error': 'Invalid mode'})
                return

            statuses = self.service.provider_key_statuses()
            has_any_configured = any(bool(v.get('configured')) for v in statuses.values())
            if not has_any_configured:
                self._send_json(400, {'success': False, 'error': 'Please configure at least one provider API key first'})
                return

            raw_port = os.environ.get('PORT', '8765').strip()
            try:
                port = int(raw_port)
            except ValueError:
                port = 8765

            result = configure_openclaw_model(mode, port=port)
            if not result.get('success'):
                self._send_json(400, result)
                return

            message = '已设为 OpenClaw 默认模型' if mode == 'default' else '已加入 OpenClaw 备用模型'
            self._send_json(200, {'success': True, 'backup': result.get('backup'), 'message': message})
            return

        if parsed.path == '/api/restore-backup':
            backup = str(payload.get('backup', '')).strip()
            if not backup:
                self._send_json(400, {'success': False, 'error': 'Backup filename is required'})
                return
            result = restore_backup(backup)
            if not result.get('success'):
                self._send_json(400, result)
                return
            self._send_json(200, {'success': True, 'message': 'Restore successful'})
            return

        if parsed.path.startswith('/api/provider-keys/'):
            provider = parsed.path.split('/')[3]
            api_key = str(payload.get('api_key', '')).strip()
            if not api_key:
                self._send_json(400, {'ok': False, 'error': 'missing api_key'})
                return
            try:
                result = self.service.save_provider_key(provider, api_key)
                self._send_json(200, result)
            except ProviderError as exc:
                self._send_json(400, {'ok': False, 'error': str(exc)})
            return

        if parsed.path.startswith('/providers/') and parsed.path.endswith('/probe'):
            provider = parsed.path.split('/')[2]
            model = str(payload.get('model', '')).strip()
            if not model:
                self._send_json(400, {'ok': False, 'error': 'missing model'})
                return
            result = self.service.probe(provider, model)
            self._send_json(200 if result.ok else 400, result.__dict__)
            return

        if parsed.path == '/chat/completions':
            provider = str(payload.get('provider', '')).strip()
            model = str(payload.get('model', '')).strip()
            if not provider or not model:
                self._send_json(400, {'ok': False, 'error': 'missing provider or model'})
                return
            prompt = str(payload.get('prompt', '')).strip()
            if not prompt and isinstance(payload.get('messages'), list) and payload['messages']:
                first = payload['messages'][0]
                if isinstance(first, dict):
                    prompt = str(first.get('content', '')).strip()
            if not prompt:
                prompt = 'ok'

            result = self.service.chat(provider, model, prompt)
            if result.ok:
                self._send_json(
                    200,
                    {
                        'ok': True,
                        'provider': provider,
                        'model': model,
                        'actual_model': result.actual_model or model,
                        'content': result.content,
                    },
                )
            else:
                self._send_json(
                    400,
                    {
                        'ok': False,
                        'provider': provider,
                        'model': model,
                        'error': result.error,
                        'category': result.category,
                        'status': result.status,
                        'suggestion': result.suggestion,
                    },
                )
            return

        self._send_json(404, {'ok': False, 'error': 'not found'})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def run(host: str = '127.0.0.1', port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f'Python backend listening on http://{host}:{port}')
    server.serve_forever()


if __name__ == '__main__':
    run()
