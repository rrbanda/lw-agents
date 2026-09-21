"""Local file cache for API responses.

Caches raw API responses under a configurable directory to avoid redundant
network calls across agent invocations within the same run. Multiple agents
querying the same CVE (selection, analysis, remediation) hit the cache
instead of re-fetching from OSV/NVD/GitHub.

TTL defaults to 1 hour (configurable via LW_CACHE_TTL_SECONDS).
Disable entirely with LW_CACHE_DISABLE=1.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(os.environ.get("LW_CACHE_DIR", "/tmp/lw-agents-cache"))
_DEFAULT_TTL_SECONDS = int(os.environ.get("LW_CACHE_TTL_SECONDS", "3600"))

_memory_cache: dict[str, tuple[float, str]] = {}


def _is_disabled() -> bool:
    """Return True if caching is disabled via environment."""
    return os.environ.get("LW_CACHE_DISABLE", "") in ("1", "true", "yes")


def _cache_path(namespace: str, key: str) -> Path:
    """Return the disk path for a cache entry."""
    safe_key = hashlib.sha256(key.lower().encode()).hexdigest()
    return _CACHE_DIR / namespace / safe_key


def cache_get(namespace: str, key: str, ttl: int | None = None) -> str | None:
    """Return cached response string if fresh, else None.

    Checks in-memory cache first, then disk. Returns None if disabled,
    expired, or missing.

    Args:
        namespace: Cache namespace (e.g. "osv", "nvd", "github_advisory").
        key: Cache key (e.g. CVE ID). Case-insensitive.
        ttl: Override TTL in seconds. Defaults to LW_CACHE_TTL_SECONDS.
    """
    if _is_disabled():
        return None

    effective_ttl = ttl if ttl is not None else _DEFAULT_TTL_SECONDS
    cache_key = f"{namespace}:{key.lower()}"

    # Memory cache first
    if cache_key in _memory_cache:
        ts, val = _memory_cache[cache_key]
        if time.time() - ts < effective_ttl:
            logger.debug("cache_hit_memory namespace=%s key=%s", namespace, key)
            return val
        else:
            del _memory_cache[cache_key]

    # Disk fallback
    path = _cache_path(namespace, key)
    if path.exists():
        try:
            age = time.time() - path.stat().st_mtime
            if age < effective_ttl:
                val = path.read_text(encoding="utf-8")
                _memory_cache[cache_key] = (time.time(), val)
                logger.debug(
                    "cache_hit_disk namespace=%s key=%s age=%.0fs",
                    namespace,
                    key,
                    age,
                )
                return val
            else:
                logger.debug(
                    "cache_expired namespace=%s key=%s age=%.0fs ttl=%d",
                    namespace,
                    key,
                    age,
                    effective_ttl,
                )
        except OSError as exc:
            logger.debug("cache_read_error namespace=%s key=%s error=%s", namespace, key, exc)

    return None


def cache_put(namespace: str, key: str, value: str) -> None:
    """Write a response string to the cache (memory + disk).

    Args:
        namespace: Cache namespace (e.g. "osv", "nvd").
        key: Cache key (e.g. CVE ID). Case-insensitive.
        value: Response string to cache (typically JSON).
    """
    if _is_disabled():
        return

    cache_key = f"{namespace}:{key.lower()}"
    _memory_cache[cache_key] = (time.time(), value)

    path = _cache_path(namespace, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        logger.debug(
            "cache_write namespace=%s key=%s size=%d path=%s",
            namespace,
            key,
            len(value),
            path,
        )
    except OSError as exc:
        logger.warning("cache_write_error namespace=%s key=%s error=%s", namespace, key, exc)


def cache_clear(namespace: str | None = None) -> int:
    """Clear cache entries. Returns the number of entries removed.

    Args:
        namespace: If provided, clear only that namespace. Otherwise clear all.
    """
    global _memory_cache
    count = 0

    if namespace is None:
        count = len(_memory_cache)
        _memory_cache = {}
        if _CACHE_DIR.exists():
            import shutil

            shutil.rmtree(_CACHE_DIR, ignore_errors=True)
    else:
        keys_to_remove = [k for k in _memory_cache if k.startswith(f"{namespace}:")]
        for k in keys_to_remove:
            del _memory_cache[k]
            count += 1
        ns_dir = _CACHE_DIR / namespace
        if ns_dir.exists():
            import shutil

            shutil.rmtree(ns_dir, ignore_errors=True)

    return count
