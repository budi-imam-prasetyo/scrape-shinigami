"""HTTP client untuk API JSON Shinigami dengan retry, backoff, dan rate guard.

Version: 1.0.0

Sumber data adalah JSON API publik Shinigami (bukan HTML). Semua request
melewati sini agar:
- retry/backoff/jitter konsisten;
- status transient (429, 5xx) di-retry, status lain tidak;
- parsing JSON gagal dianggap error dan di-retry;
- request serial + polite delay agar tidak membebani API.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Protocol

import requests

from .config import DEFAULT_HEADERS

LOGGER = logging.getLogger(__name__)

# Status yang layak di-retry (transient / rate limit).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SessionLike(Protocol):
    """Kontrak minimal requests.Session (mendukung stub untuk test)."""

    headers: dict

    def get(
        self, url: str, params: dict[str, Any] | None = ..., timeout: Any = ...
    ) -> Any: ...


class ApiClientError(RuntimeError):
    """Kesalahan saat memanggil API (setelah retry habis / payload tak valid)."""


class _RetryableStatus(Exception):
    """Status transient (429, 5xx) yang layak dicoba ulang."""

    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"Status retryable {status} untuk {url}")
        self.status = status


class _FatalStatus(Exception):
    """Status 4xx permanen: tidak boleh di-retry."""

    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"Status {status} untuk {url}")
        self.status = status


def _backoff_sleep(attempt, last_error, url, max_retries, backoff_base) -> None:
    sleep = backoff_base**attempt + random.uniform(0, 1)
    LOGGER.warning(
        "Percobaan %d/%d gagal untuk %s: %s (retry dalam %.1fs)",
        attempt,
        max_retries,
        url,
        last_error,
        sleep,
    )
    time.sleep(sleep)


class ApiClient:
    def __init__(
        self,
        session: SessionLike | None = None,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        delays: tuple[float, float] = (1.0, 2.0),
    ) -> None:
        self.session = session or new_session()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.delays = delays

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET dan kembalikan body JSON terurai.

        Raise ApiClientError setelah retry habis untuk error jaringan,
        HTTP 5xx/429, atau payload yang bukan JSON valid.
        """
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=(10, 30))
                if resp.status_code in RETRYABLE_STATUS:
                    raise _RetryableStatus(url, resp.status_code)
                # 4xx non-retryable: jangan coba ulang.
                if resp.status_code >= 400:
                    raise _FatalStatus(url, resp.status_code)
                return resp.json()
            except _RetryableStatus as error:
                last_error = error
                if attempt == self.max_retries:
                    raise ApiClientError(f"Gagal request {url}: {error}") from error
                _backoff_sleep(
                    attempt, last_error, url, self.max_retries, self.backoff_base
                )
            except _FatalStatus as error:
                raise ApiClientError(f"Gagal request {url}: {error}") from error
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt == self.max_retries:
                    raise ApiClientError(f"Gagal request {url}: {error}") from error
                _backoff_sleep(
                    attempt, last_error, url, self.max_retries, self.backoff_base
                )

        raise ApiClientError(
            f"Gagal request {url} setelah {self.max_retries} percobaan: {last_error}"
        ) from last_error

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """GET dan kembalikan teks mentah (dipakai fallback HTML komentar)."""
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=(10, 30))
                if resp.status_code in RETRYABLE_STATUS:
                    raise _RetryableStatus(url, resp.status_code)
                if resp.status_code >= 400:
                    raise _FatalStatus(url, resp.status_code)
                return resp.text
            except _RetryableStatus as error:
                last_error = error
                if attempt == self.max_retries:
                    raise ApiClientError(f"Gagal request {url}: {error}") from error
                _backoff_sleep(
                    attempt, last_error, url, self.max_retries, self.backoff_base
                )
            except _FatalStatus as error:
                raise ApiClientError(f"Gagal request {url}: {error}") from error
            except requests.RequestException as error:
                last_error = error
                if attempt == self.max_retries:
                    raise ApiClientError(f"Gagal request {url}: {error}") from error
                _backoff_sleep(
                    attempt, last_error, url, self.max_retries, self.backoff_base
                )

        raise ApiClientError(
            f"Gagal request {url} setelah {self.max_retries} percobaan: {last_error}"
        ) from last_error

    def polite_delay(self) -> None:
        time.sleep(random.uniform(*self.delays))


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(dict(DEFAULT_HEADERS))
    return session
