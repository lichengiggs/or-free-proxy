from __future__ import annotations

import ssl
from collections.abc import Iterable
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import certifi
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential, wait_random

from .errors import classify_error
from .provider_errors import ProviderError, ProviderHTTPError


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
    from urllib.parse import urlencode

    base = base_url.rstrip('/')
    normalized_path = path if path.startswith('/') else f'/{path}'
    if not query:
        return f'{base}{normalized_path}'
    return f'{base}{normalized_path}?{urlencode(query)}'


class HttpxTransport:
    _retryable_statuses = {429, 500, 502, 503, 504}

    @staticmethod
    def _headers_map(headers: httpx.Headers) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for key, value in headers.items():
            mapping[key] = value
            mapping[key.lower()] = value
            if key.lower() == 'content-type':
                mapping['Content-Type'] = value
        return mapping

    @staticmethod
    def _response_text(body: bytes) -> str:
        return body.decode('utf-8', errors='ignore')

    @staticmethod
    def _verify_value() -> object:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        if not isinstance(ssl_context, ssl.SSLContext):
            return ssl_context
        cert_path = certifi.where()
        try:
            ssl_context.load_verify_locations(cafile=cert_path)
        except FileNotFoundError:
            pass
        return ssl_context

    @classmethod
    def _is_retryable_status(cls, status: int) -> bool:
        return status in cls._retryable_statuses

    @retry(
        retry=retry_if_exception_type(ProviderError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.5, max=8) + wait_random(0, 0.5),
        reraise=True,
    )
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        verify = self._verify_value()
        if not isinstance(verify, ssl.SSLContext):
            try:
                with urlopen(url, data=body, timeout=timeout, context=verify) as response:  # type: ignore[arg-type]
                    response_body = response.read()
                    response_headers = {key.lower(): value for key, value in response.headers.items()}
                    status = getattr(response, 'status', getattr(response, 'code', 200))
                    if self._is_retryable_status(status):
                        failure = classify_error(status, self._response_text(response_body))
                        raise ProviderHTTPError(message=failure.message, status=status, category=failure.category)
                    return status, response_headers, response_body
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                raise ProviderError(f'网络连接失败: {exc}') from exc

        with httpx.Client(verify=verify, timeout=timeout, follow_redirects=True) as client:
            try:
                response = client.request(method, url, headers=headers or {}, content=body)
            except httpx.RequestError as exc:
                raise ProviderError(f'网络连接失败: {exc}') from exc
            response_headers = self._headers_map(response.headers)
            response_body = response.content
            if self._is_retryable_status(response.status_code):
                failure = classify_error(response.status_code, self._response_text(response_body))
                raise ProviderHTTPError(message=failure.message, status=response.status_code, category=failure.category)
            return response.status_code, response_headers, response_body

    @retry(
        retry=retry_if_exception_type(ProviderError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.5, max=8) + wait_random(0, 0.5),
        reraise=True,
    )
    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], Iterable[bytes]]:
        verify = self._verify_value()
        if not isinstance(verify, ssl.SSLContext):
            try:
                response = urlopen(url, data=body, timeout=timeout, context=verify)  # type: ignore[arg-type]
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                raise ProviderError(f'网络连接失败: {exc}') from exc
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            status = getattr(response, 'status', getattr(response, 'code', 200))
            response_body = response.read()
            response.close()
            if self._is_retryable_status(status):
                failure = classify_error(status, self._response_text(response_body))
                raise ProviderHTTPError(message=failure.message, status=status, category=failure.category)
            return status, response_headers, [response_body]

        httpx_timeout = httpx.Timeout(connect=min(timeout, 15), read=max(timeout, 300), write=min(timeout, 15), pool=5)
        client = httpx.Client(verify=verify, timeout=httpx_timeout, follow_redirects=True)
        request = client.build_request(method, url, headers=headers or {}, content=body)
        try:
            response = client.send(request, stream=True)
        except httpx.RequestError as exc:
            client.close()
            raise ProviderError(f'网络连接失败: {exc}') from exc
        response_headers = self._headers_map(response.headers)

        if self._is_retryable_status(response.status_code):
            response_body = response.read()
            response.close()
            client.close()
            failure = classify_error(response.status_code, self._response_text(response_body))
            raise ProviderHTTPError(message=failure.message, status=response.status_code, category=failure.category)

        if response.status_code >= 400:
            response_body = response.read()
            response.close()
            client.close()
            return response.status_code, response_headers, [response_body]

        def iterator() -> Iterable[bytes]:
            pending = bytearray()
            event = bytearray()
            try:
                for chunk in response.iter_bytes():
                    pending.extend(chunk)
                    while True:
                        newline_index = pending.find(b'\n')
                        if newline_index < 0:
                            break
                        line = bytes(pending[: newline_index + 1])
                        del pending[: newline_index + 1]
                        event.extend(line)
                        if line in {b'\n', b'\r\n'}:
                            if len(event) > len(line):
                                chunk = bytes(event)
                                yield chunk
                                if self._is_done_chunk(chunk):
                                    return
                            event.clear()
                if event:
                    yield bytes(event)
                elif pending:
                    yield bytes(pending)
            finally:
                response.close()
                client.close()

        return response.status_code, response_headers, iterator()

    @staticmethod
    def _is_done_chunk(chunk: bytes) -> bool:
        normalized = chunk.replace(b' ', b'')
        return b'data:[DONE]' in normalized


UrlLibTransport = HttpxTransport
