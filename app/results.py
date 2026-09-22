"""Structured agent results — typed envelope for every agent output.

Replaces the fragile regex-based extraction in callbacks.py with typed,
persistent, and Tekton-compatible result objects. Every agent callback
produces an AgentResult; downstream consumers never parse LLM prose.

Design:
- AgentResult is the per-agent envelope (analogous to StageResult)
- RunSummary is the pipeline-level rollup (analogous to PipelineSummary)
- Both serialize to/from JSON files for resume capability
- to_tekton_results() provides backward-compatible Tekton output
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class AgentStatus(Enum):
    """Status of a completed agent execution."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_ESCALATION = "needs_escalation"


@dataclass
class AgentResult:
    """Standardized envelope written by every agent.

    The ``data`` payload is an open dict. Each agent populates keys
    specific to its work. Cross-cutting keys:

    - ``cve_id``: The CVE being processed
    - ``selected``: "1" or "0" for selection results
    - ``changed``: "1" or "0" for remediation results
    - ``pr_url``: Pull request URL if one was created
    """

    agent: str
    status: AgentStatus
    timestamp: str = ""
    duration_seconds: float = 0.0
    ai_invocations: int = 0
    data: dict = field(default_factory=dict)
    error: str | None = None
    token_usage: dict = field(default_factory=dict)
    prompt_metrics: list[dict] = field(default_factory=list)
    start: float | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Compute duration_seconds from start when provided."""
        if not self.timestamp:
            self.timestamp = datetime.now(tz=UTC).isoformat()
        if self.start is not None:
            if self.duration_seconds:
                raise ValueError("Cannot provide both 'start' and 'duration_seconds'")
            self.duration_seconds = time.monotonic() - self.start
            self.start = None

    def to_dict(self) -> dict:
        """Return a plain-dict representation of this result."""
        d: dict = {
            "agent": self.agent,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "duration_seconds": round(self.duration_seconds, 3),
            "ai_invocations": self.ai_invocations,
            "data": self.data,
        }
        if self.error is not None:
            d["error"] = self.error
        if self.token_usage:
            d["token_usage"] = self.token_usage
        if self.prompt_metrics:
            d["prompt_metrics"] = self.prompt_metrics
        return d

    def to_json(self, path: str) -> None:
        """Serialize this result to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_file(self, directory: str) -> str:
        """Write this result to *directory*/{agent}.json. Returns the path."""
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{self.agent}.json")
        self.to_json(path)
        return path

    @classmethod
    def from_json(cls, path: str) -> AgentResult:
        """Deserialize an AgentResult from a JSON file."""
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            agent=raw["agent"],
            status=AgentStatus(raw["status"]),
            timestamp=raw.get("timestamp", ""),
            duration_seconds=raw.get("duration_seconds", 0.0),
            ai_invocations=raw.get("ai_invocations", 0),
            data=raw.get("data", {}),
            error=raw.get("error"),
            token_usage=raw.get("token_usage", {}),
            prompt_metrics=raw.get("prompt_metrics", []),
        )

    @classmethod
    def from_file(cls, directory: str, agent_name: str) -> AgentResult:
        """Load an AgentResult from *directory*/{agent_name}.json."""
        path = os.path.join(directory, f"{agent_name}.json")
        return cls.from_json(path)

    def to_tekton_results(self) -> dict[str, str]:
        """Map to the Tekton result contract (backward compatible).

        Always returns the 11-field contract, filling defaults for
        missing fields.
        """
        d = self.data
        return {
            "SELECTED": str(d.get("selected", "0")),
            "CVE_ID": str(d.get("cve_id", "")),
            "PACKAGE": str(d.get("package", "")),
            "CURRENT_VERSION": str(d.get("current_version", "")),
            "FIXED_VERSION": str(d.get("fixed_version", "")),
            "JUSTIFICATION": str(d.get("justification", "")),
            "PR_URL": str(d.get("pr_url", "")),
            "COUNT": str(d.get("count", "0")),
            "TESTS_ADDED": str(d.get("tests_added", "0")),
            "ISSUES_CREATED": str(d.get("issues_created", "0")),
            "CHANGED": str(d.get("changed", "0")),
        }


def _extract_tokens(result: AgentResult) -> dict:
    """Extract token counts from an AgentResult."""
    return result.token_usage or {}


@dataclass
class RunSummary:
    """Roll-up metrics for a completed agent pipeline run."""

    vuln_id: str = ""
    status: str = ""
    total_agents: int = 0
    agents_succeeded: int = 0
    agents_failed: int = 0
    agents_skipped: int = 0
    total_duration_seconds: float = 0.0
    wall_clock_seconds: float = 0.0
    total_ai_invocations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    agent_details: list[dict] = field(default_factory=list)
    timestamp: str = ""

    @classmethod
    def from_results(
        cls,
        results: list[AgentResult],
        *,
        vuln_id: str = "",
        wall_clock_seconds: float = 0.0,
    ) -> RunSummary:
        """Build a summary by aggregating a list of agent results."""
        succeeded = sum(1 for r in results if r.status == AgentStatus.SUCCESS)
        failed = sum(1 for r in results if r.status == AgentStatus.FAILED)
        skipped = sum(1 for r in results if r.status == AgentStatus.SKIPPED)

        if failed:
            status = "failed"
        elif any(r.status == AgentStatus.NEEDS_ESCALATION for r in results):
            status = "needs_escalation"
        else:
            status = "success"

        total_input = 0
        total_output = 0
        total_cost = 0.0
        details: list[dict] = []

        for r in results:
            tu = _extract_tokens(r)
            inp = int(tu.get("input_tokens", 0) or 0)
            out = int(tu.get("output_tokens", 0) or 0)
            cost = float(tu.get("cost_usd", 0.0) or 0.0)
            total_input += inp
            total_output += out
            total_cost += cost

            details.append(
                {
                    "agent": r.agent,
                    "status": r.status.value,
                    "duration_seconds": r.duration_seconds,
                    "ai_invocations": r.ai_invocations,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cost_usd": cost,
                }
            )

        return cls(
            vuln_id=vuln_id,
            status=status,
            total_agents=len(results),
            agents_succeeded=succeeded,
            agents_failed=failed,
            agents_skipped=skipped,
            total_duration_seconds=sum(r.duration_seconds for r in results),
            wall_clock_seconds=round(wall_clock_seconds, 3),
            total_ai_invocations=sum(r.ai_invocations for r in results),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost_usd=round(total_cost, 6),
            agent_details=details,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )

    def to_dict(self) -> dict:
        return {
            "vuln_id": self.vuln_id,
            "status": self.status,
            "total_agents": self.total_agents,
            "agents_succeeded": self.agents_succeeded,
            "agents_failed": self.agents_failed,
            "agents_skipped": self.agents_skipped,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "wall_clock_seconds": self.wall_clock_seconds,
            "total_ai_invocations": self.total_ai_invocations,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "agent_details": self.agent_details,
            "timestamp": self.timestamp,
        }

    def to_json(self, path: str) -> None:
        """Write the summary to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


def load_prior_results(run_dir: str, agent_names: list[str]) -> list[AgentResult]:
    """Load all existing agent results from a run directory.

    Used for pipeline resume: scans for {agent_name}.json files and
    returns successfully loaded results.
    """
    results: list[AgentResult] = []
    for name in agent_names:
        path = os.path.join(run_dir, f"{name}.json")
        if os.path.exists(path):
            try:
                result = AgentResult.from_json(path)
                results.append(result)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return results


def write_metrics_snapshot(directory: str, results: list[AgentResult]) -> None:
    """Write a JSONL metrics file from current agent results.

    Each line is a compact metrics record for one agent.
    """
    metrics_path = os.path.join(directory, "agent-metrics.jsonl")
    os.makedirs(directory, exist_ok=True)
    with open(metrics_path, "w", encoding="utf-8") as f:
        for result in results:
            tu = _extract_tokens(result)
            record = {
                "agent": result.agent,
                "status": result.status.value,
                "timestamp": result.timestamp,
                "duration_seconds": round(result.duration_seconds, 3),
                "ai_invocations": result.ai_invocations,
                "cost_usd": float(tu.get("cost_usd", 0.0) or 0.0),
            }
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")
