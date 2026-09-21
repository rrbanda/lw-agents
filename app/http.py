"""Resilient HTTP client with retry, exponential backoff, and Retry-After support.

All external API calls (OSV, NVD, Maven Central, GitHub, EPSS, ecosyste.ms)
should go through this module. Provides connection pooling, structured logging,
and configurable retry on transient failures (429, 5xx, network errors).

HTTP 404 is returned immediately (not retried).
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 1.5
_DEFAULT_TIMEOUT = 15.0
_MAX_RETRY_AFTER = 60

_client: httpx.Client | None = None


def get_client(timeout: float = _DEFAULT_TIMEOUT) -> httpx.Client:
    """Return a module-level httpx.Client for connection pooling.

    The client is lazily created and reused across calls.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "lw-agents/1.0"},
        )
    return _client


def close_client() -> None:
    """Close the shared client (call on shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        _client.close()
        _client = None


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    """Extract seconds to wait from a Retry-After header.

    Handles delay-seconds format (e.g. "30"). Returns None if missing
    or unparseable.
    """
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    backoff_base: float = _DEFAULT_BACKOFF_BASE,
) -> tuple[int, dict | list | None]:
    """GET *url* with retry on 429/5xx. Returns (status_code, parsed_json).

    Returns (404, None) on not-found.
    Returns (0, {"error": "..."}) after exhausting retries.
    Raises nothing — all errors are captured in the return value.
    """
    client = get_client()
    req_headers = dict(headers) if headers else {}
    if "Accept" not in req_headers:
        req_headers["Accept"] = "application/json"

    last_error: str = ""
    for attempt in range(max_retries):
        try:
            resp = client.get(url, headers=req_headers)

            if resp.status_code == 404:
                return 404, None

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = _parse_retry_after(resp.headers)
                wait = retry_after if retry_after is not None else backoff_base * (2**attempt)
                wait = min(wait, _MAX_RETRY_AFTER)
                logger.warning(
                    "http_retry url=%s status=%d attempt=%d/%d wait=%.1fs",
                    url,
                    resp.status_code,
                    attempt + 1,
                    max_retries,
                    wait,
                )
                last_error = f"HTTP {resp.status_code}"
                if attempt < max_retries - 1:
                    time.sleep(wait)
                continue

            if resp.status_code >= 400:
                return resp.status_code, {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}

            return resp.status_code, resp.json()

        except httpx.TimeoutException as exc:
            last_error = f"Timeout: {exc}"
            logger.warning(
                "http_retry url=%s error=timeout attempt=%d/%d",
                url,
                attempt + 1,
                max_retries,
            )
            if attempt < max_retries - 1:
                time.sleep(backoff_base * (2**attempt))

        except httpx.HTTPError as exc:
            last_error = f"Network error: {exc}"
            logger.warning(
                "http_retry url=%s error=%s attempt=%d/%d",
                url,
                exc,
                attempt + 1,
                max_retries,
            )
            if attempt < max_retries - 1:
                time.sleep(backoff_base * (2**attempt))

        except Exception as exc:
            last_error = f"Unexpected error: {exc}"
            logger.warning("http_unexpected url=%s error=%s", url, exc)
            return 0, {"error": last_error}

    logger.warning("http_retry_exhausted url=%s last_error=%s", url, last_error)
    return 0, {"error": f"Retries exhausted after {max_retries} attempts: {last_error}"}


def fetch_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    backoff_base: float = _DEFAULT_BACKOFF_BASE,
) -> tuple[int, str | None]:
    """GET *url* returning raw text. Same retry behavior as fetch_json.

    Returns (status_code, text) on success, (404, None) on not-found,
    (0, None) after exhausting retries.
    """
    client = get_client()
    req_headers = dict(headers) if headers else {}

    last_error: str = ""
    for attempt in range(max_retries):
        try:
            resp = client.get(url, headers=req_headers)

            if resp.status_code == 404:
                return 404, None

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = _parse_retry_after(resp.headers)
                wait = retry_after if retry_after is not None else backoff_base * (2**attempt)
                wait = min(wait, _MAX_RETRY_AFTER)
                logger.warning(
                    "http_retry url=%s status=%d attempt=%d/%d wait=%.1fs",
                    url,
                    resp.status_code,
                    attempt + 1,
                    max_retries,
                    wait,
                )
                last_error = f"HTTP {resp.status_code}"
                if attempt < max_retries - 1:
                    time.sleep(wait)
                continue

            return resp.status_code, resp.text

        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            last_error = str(exc)
            logger.warning(
                "http_retry url=%s error=%s attempt=%d/%d",
                url,
                exc,
                attempt + 1,
                max_retries,
            )
            if attempt < max_retries - 1:
                time.sleep(backoff_base * (2**attempt))

    logger.warning("http_retry_exhausted url=%s last_error=%s", url, last_error)
    return 0, None


def head_check(
    url: str,
    *,
    max_retries: int = 2,
    backoff_base: float = 1.0,
) -> tuple[int, bool]:
    """HEAD *url* to check existence. Returns (status_code, exists).

    Used for Maven Central version verification.
    """
    client = get_client()
    for attempt in range(max_retries):
        try:
            resp = client.head(url)
            return resp.status_code, resp.status_code == 200
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning(
                "head_check url=%s error=%s attempt=%d/%d",
                url,
                exc,
                attempt + 1,
                max_retries,
            )
            if attempt < max_retries - 1:
                time.sleep(backoff_base * (2**attempt))

    return 0, False


def github_headers(token: str | None = None) -> dict[str, str]:
    """Build standard GitHub API request headers."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
