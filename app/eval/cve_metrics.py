"""Custom CVE evaluation metrics for EvalHub.

These metrics assess the quality of lw-agents' CVE remediation pipeline.
They can be submitted as custom benchmarks via the EvalHub API or used
standalone for local validation.

Metrics computed:
  - cve_selection_accuracy: % of CVE selections that pass fail-closed validation
  - remediation_success_rate: % of remediations that produce a passing build
  - fix_safety_score: % of fixes passing adversarial validation
  - pr_hygiene_score: PR content quality (diff confined, tests present, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.scoring.validate_selection import validate_selection


@dataclass
class CVEEvalResult:
    """Aggregated results from a CVE evaluation run."""

    total_cves: int = 0
    selections_valid: int = 0
    remediations_attempted: int = 0
    remediations_succeeded: int = 0
    fixes_validated: int = 0
    fixes_safe: int = 0
    prs_opened: int = 0
    prs_with_tests: int = 0
    benchmark_scores: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def selection_accuracy(self) -> float:
        if self.total_cves == 0:
            return 0.0
        return self.selections_valid / self.total_cves

    @property
    def remediation_success_rate(self) -> float:
        if self.remediations_attempted == 0:
            return 0.0
        return self.remediations_succeeded / self.remediations_attempted

    @property
    def fix_safety_score(self) -> float:
        if self.fixes_validated == 0:
            return 0.0
        return self.fixes_safe / self.fixes_validated

    @property
    def pr_hygiene_score(self) -> float:
        if self.prs_opened == 0:
            return 0.0
        return self.prs_with_tests / self.prs_opened

    def to_evalhub_metrics(self) -> list[dict[str, Any]]:
        """Convert to EvalHub-compatible metrics format."""
        return [
            {
                "name": "cve_selection_accuracy",
                "value": self.selection_accuracy,
                "description": "Proportion of CVE selections passing validation",
            },
            {
                "name": "remediation_success_rate",
                "value": self.remediation_success_rate,
                "description": "Proportion of successful remediations",
            },
            {
                "name": "fix_safety_score",
                "value": self.fix_safety_score,
                "description": "Proportion of fixes passing adversarial review",
            },
            {
                "name": "pr_hygiene_score",
                "value": self.pr_hygiene_score,
                "description": "Proportion of PRs with associated tests",
            },
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON/YAML output."""
        return {
            "total_cves": self.total_cves,
            "selections_valid": self.selections_valid,
            "selection_accuracy": round(self.selection_accuracy, 4),
            "remediations_attempted": self.remediations_attempted,
            "remediations_succeeded": self.remediations_succeeded,
            "remediation_success_rate": round(self.remediation_success_rate, 4),
            "fixes_validated": self.fixes_validated,
            "fixes_safe": self.fixes_safe,
            "fix_safety_score": round(self.fix_safety_score, 4),
            "prs_opened": self.prs_opened,
            "prs_with_tests": self.prs_with_tests,
            "pr_hygiene_score": round(self.pr_hygiene_score, 4),
            "errors": self.errors,
        }


def evaluate_selection_batch(
    selections: list[dict[str, Any]],
) -> CVEEvalResult:
    """Evaluate a batch of CVE selection results.

    Args:
        selections: List of CVE selection dicts (as returned by the agent).

    Returns:
        CVEEvalResult with selection metrics populated.
    """
    result = CVEEvalResult(total_cves=len(selections))
    for sel in selections:
        validated = validate_selection(sel)
        if validated.get("validation_status") == "accepted":
            result.selections_valid += 1
        if validated.get("validation_errors"):
            result.errors.extend(validated["validation_errors"])
    result.benchmark_scores["cve_selection_accuracy"] = result.selection_accuracy
    return result


def evaluate_remediation_batch(
    remediations: list[dict[str, Any]],
) -> CVEEvalResult:
    """Evaluate a batch of remediation results.

    Args:
        remediations: List of remediation result dicts with keys:
            - build_passed: bool
            - validation_verdict: str  (pass/fail)
            - pr_url: str
            - has_tests: bool

    Returns:
        CVEEvalResult with remediation metrics populated.
    """
    result = CVEEvalResult()
    for rem in remediations:
        result.remediations_attempted += 1
        if rem.get("build_passed"):
            result.remediations_succeeded += 1
        if rem.get("validation_verdict"):
            result.fixes_validated += 1
            verdict = str(rem["validation_verdict"]).lower()
            if verdict in ("pass", "passed", "true"):
                result.fixes_safe += 1
        if rem.get("pr_url"):
            result.prs_opened += 1
            if rem.get("has_tests"):
                result.prs_with_tests += 1

    result.benchmark_scores["remediation_success_rate"] = result.remediation_success_rate
    result.benchmark_scores["fix_safety_score"] = result.fix_safety_score
    result.benchmark_scores["pr_hygiene_score"] = result.pr_hygiene_score
    return result


def build_evalhub_benchmark_config(
    result: CVEEvalResult,
    experiment_name: str = "lw-agents-cve-eval",
) -> dict[str, Any]:
    """Build an EvalHub-compatible custom benchmark payload.

    This can be submitted via the EvalHub API to track CVE eval results
    alongside standard LLM benchmarks in MLflow.
    """
    metrics = result.to_evalhub_metrics()
    return {
        "name": experiment_name,
        "provider_id": "custom",
        "benchmarks": [
            {
                "id": m["name"],
                "provider_id": "custom",
                "primary_score": {"metric": m["name"]},
                "pass_criteria": {
                    "threshold": _default_threshold(m["name"]),
                },
                "results": {"value": m["value"]},
            }
            for m in metrics
        ],
        "metadata": {
            "source": "lw-agents",
            "type": "cve_remediation_eval",
        },
    }


def _default_threshold(metric_name: str) -> float:
    """Return default pass threshold for a CVE metric."""
    thresholds = {
        "cve_selection_accuracy": 0.8,
        "remediation_success_rate": 0.7,
        "fix_safety_score": 0.9,
        "pr_hygiene_score": 0.8,
    }
    return thresholds.get(metric_name, 0.5)
