"""Provenance, checksums, and auditability — Layers 9.1, 9.2, 8.2, 8.3.

Generates run provenance documents, computes artifact checksums,
provides tee logging, and tracks per-agent prompt metrics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07")


# ============================================================================
# L9.1 — Run provenance document
# ============================================================================


def generate_run_provenance(
    *,
    run_id: str,
    vuln_id: str = "",
    component: str = "",
    model_name: str = "",
    data_sources: list[str] | None = None,
    tools_called: list[str] | None = None,
    agents_run: list[str] | None = None,
    validation_verdict: str = "",
    token_usage: dict | None = None,
    total_cost_usd: float = 0.0,
    wall_clock_seconds: float = 0.0,
    started_at: str = "",
    finished_at: str = "",
) -> dict[str, Any]:
    """Generate a provenance document for an agent pipeline run.

    Pure data function — no I/O. Caller is responsible for writing to disk.
    """
    return {
        "_type": "https://lw-agents.dev/provenance/v1",
        "run_id": run_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "identity": {
            "vuln_id": vuln_id,
            "component": component,
        },
        "execution": {
            "model": model_name,
            "agents": agents_run or [],
            "data_sources_consulted": data_sources or [],
            "tools_called": tools_called or [],
            "started_at": started_at,
            "finished_at": finished_at,
            "wall_clock_seconds": round(wall_clock_seconds, 3),
        },
        "outcome": {
            "validation_verdict": validation_verdict,
        },
        "cost": {
            "total_cost_usd": round(total_cost_usd, 6),
            "token_usage": token_usage or {},
        },
    }


def write_provenance(provenance: dict, run_dir: str) -> str:
    """Write provenance document to {run_dir}/PROVENANCE.json."""
    path = os.path.join(run_dir, "PROVENANCE.json")
    os.makedirs(run_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)
    return path


# ============================================================================
# L9.2 — Artifact checksums
# ============================================================================


def compute_checksums(path: str | os.PathLike) -> dict[str, str]:
    """Compute SHA-256, SHA-1, and MD5 checksums for a file."""
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1()
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
            sha1.update(chunk)
            md5.update(chunk)
    return {
        "sha256": sha256.hexdigest(),
        "sha1": sha1.hexdigest(),
        "md5": md5.hexdigest(),
    }


def compute_checksums_for_dir(
    directory: str,
    extensions: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    """Compute checksums for all files in a directory.

    Args:
        directory: Directory to scan.
        extensions: If provided, only include files with these extensions.

    Returns:
        Dict of {relative_path: {sha256, sha1, md5}}.
    """
    results: dict[str, dict[str, str]] = {}
    root = Path(directory)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if extensions and path.suffix not in extensions:
            continue
        rel = str(path.relative_to(root))
        try:
            results[rel] = compute_checksums(path)
        except OSError:
            continue
    return results


# ============================================================================
# L8.2 — Tee logging
# ============================================================================


class TeeWriter:
    """Write to two streams simultaneously.

    The secondary (log file) stream gets cleaned output: ANSI escapes
    stripped, carriage-return spinner frames dropped.
    """

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def write(self, data):
        self._primary.write(data)
        clean = _ANSI_RE.sub("", data)
        if clean.strip():
            self._secondary.write(clean)

    def flush(self):
        self._primary.flush()
        self._secondary.flush()

    def isatty(self):
        return self._primary.isatty()


def setup_tee_output(log_path: str):
    """Replace sys.stdout with a TeeWriter that also writes to log_path.

    Returns the original stdout for cleanup.
    """
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")
    original = sys.stdout
    sys.stdout = TeeWriter(original, log_file)
    return original, log_file


# ============================================================================
# L8.3 — Per-agent prompt metrics
# ============================================================================


@dataclass
class PromptMetric:
    """Record of a single LLM invocation."""

    prompt_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    latency_ms: float = 0.0
    outcome: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(tz=UTC).isoformat()

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "latency_ms": round(self.latency_ms, 1),
            "outcome": self.outcome,
            "timestamp": self.timestamp,
        }


class PromptMetricsCollector:
    """Thread-safe collector for per-invocation LLM metrics."""

    def __init__(self):
        self._metrics: list[PromptMetric] = []

    def record(self, metric: PromptMetric) -> None:
        self._metrics.append(metric)

    @property
    def metrics(self) -> list[PromptMetric]:
        return list(self._metrics)

    @property
    def total_input_tokens(self) -> int:
        return sum(m.input_tokens for m in self._metrics)

    @property
    def total_output_tokens(self) -> int:
        return sum(m.output_tokens for m in self._metrics)

    @property
    def total_cost_estimate(self) -> float:
        """Rough cost estimate at $0.15/1M input, $0.60/1M output (Gemini Flash pricing)."""
        inp = self.total_input_tokens * 0.15 / 1_000_000
        out = self.total_output_tokens * 0.60 / 1_000_000
        return round(inp + out, 6)

    def to_dict(self) -> dict:
        return {
            "total_invocations": len(self._metrics),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": self.total_cost_estimate,
            "metrics": [m.to_dict() for m in self._metrics],
        }
