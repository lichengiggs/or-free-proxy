from __future__ import annotations

import ssl
from collections.abc import Iterable
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi

from .provider_errors import ProviderError


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        ...

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], Iterable[bytes]]:
        ...


def build_url(base_url: str, path: str, query: dict[str, str] | None = None) -> str:
    base = base_url.rstrip('/')
    normalized_path = path if path.startswith('/') else f'/{path}'
    if not query:
        return f'{base}{normalized_path}'
    return f'{base}{normalized_path}?{urlencode(query)}'


class UrlLibTransport:
    @staticmethod
    def _is_done_chunk(chunk: bytes) -> bool:
        normalized = chunk.replace(b' ', b'')
        return b'data:[DONE]' in normalized

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        request = Request(url=url, data=body, headers=headers or {}, method=method)
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        try:
            with urlopen(request, timeout=timeout, context=ssl_context) as response:
                return response.status, dict(response.headers.items()), response.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read()
        except TimeoutError as exc:
            raise ProviderError(f'网络连接失败: {exc}') from exc
        except URLError as exc:
            raise ProviderError(f'网络连接失败: {exc.reason}') from exc

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], Iterable[bytes]]:
        request = Request(url=url, data=body, headers=headers or {}, method=method)
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        try:
            response = urlopen(request, timeout=timeout, context=ssl_context)
        except HTTPError as exc:
            headers_map = dict(exc.headers.items()) if exc.headers else {}
            return exc.code, headers_map, [exc.read()]
        except TimeoutError as exc:
            raise ProviderError(f'网络连接失败: {exc}') from exc
        except URLError as exc:
            raise ProviderError(f'网络连接失败: {exc.reason}') from exc

        status = response.status
        headers_map = dict(response.headers.items())

        def iterator() -> Iterable[bytes]:
            try:
                # SSE must be forwarded as soon as each line arrives, otherwise long-thinking
                # models appear to stall until the upstream socket finally closes.
                pending = bytearray()
                while True:
                    line = response.readline()
                    if not line:
                        if pending:
                            yield bytes(pending)
                        break
                    pending.extend(line)
                    if line in {b'\n', b'\r\n'}:
                        if len(pending) > len(line):
                            chunk = bytes(pending)
                            yield chunk
                            if self._is_done_chunk(chunk):
                                break
                        pending.clear()
            finally:
                response.close()

        return status, headers_map, iterator()
