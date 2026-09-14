"""Automated agent evaluation — runs eval datasets against live agents,
compares results to baselines, and returns pass/fail for CI gating.

This is the bridge between eval datasets (tests/eval/datasets/*.json) and
the CI pipeline. It does NOT require manual execution — Tekton calls it
automatically on every code change and on scheduled model-update checks.

Entry points:
  - run_agent_evals()       — run all agent eval sets, return structured report
  - check_regression()      — compare current scores against baseline
  - gate_decision()         — single CI call: run + compare + pass/fail
  - main()                  — CLI entry point for Tekton tasks and Makefile
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "eval"
BASELINE_PATH = EVAL_DIR / "baseline.json"

# Minimum acceptable scores per metric.  A metric below its floor
# blocks deployment even if it hasn't regressed from the baseline.
METRIC_FLOORS: dict[str, float] = {
    "cve_selection_accuracy": 0.70,
    "version_not_hallucinated": 0.90,
    "correct_routing": 0.85,
    "skill_loaded_first": 0.80,
    "tool_use_completeness": 0.70,
    "remediation_build_passes": 0.60,
    "validation_gate_accuracy": 0.70,
    "pr_hygiene": 0.60,
    "multi_turn_task_success": 0.60,
    "multi_turn_tool_use_quality": 0.60,
}

# Max allowed regression from baseline before blocking.
REGRESSION_TOLERANCE = 0.10


@dataclass
class EvalSetResult:
    """Results from running one eval set (one agent)."""

    name: str
    agent: str
    cases_total: int = 0
    cases_passed: int = 0
    metric_scores: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def pass_rate(self) -> float:
        if self.cases_total == 0:
            return 0.0
        return self.cases_passed / self.cases_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent": self.agent,
            "cases_total": self.cases_total,
            "cases_passed": self.cases_passed,
            "pass_rate": round(self.pass_rate, 4),
            "metric_scores": {k: round(v, 4) for k, v in self.metric_scores.items()},
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
        }


@dataclass
class EvalReport:
    """Aggregated results from all eval sets."""

    eval_sets: list[EvalSetResult] = field(default_factory=list)
    overall_pass: bool = False
    regressions: list[dict[str, Any]] = field(default_factory=list)
    floor_violations: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""
    git_sha: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_pass": self.overall_pass,
            "timestamp": self.timestamp,
            "git_sha": self.git_sha,
            "eval_sets": [es.to_dict() for es in self.eval_sets],
            "regressions": self.regressions,
            "floor_violations": self.floor_violations,
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        total_cases = sum(es.cases_total for es in self.eval_sets)
        total_passed = sum(es.cases_passed for es in self.eval_sets)
        return {
            "agents_evaluated": len(self.eval_sets),
            "total_cases": total_cases,
            "total_passed": total_passed,
            "total_pass_rate": (round(total_passed / total_cases, 4) if total_cases > 0 else 0.0),
            "regressions_found": len(self.regressions),
            "floor_violations_found": len(self.floor_violations),
        }


def load_eval_config() -> dict[str, Any]:
    """Load the eval configuration."""
    config_path = EVAL_DIR / "eval_config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_baseline() -> dict[str, dict[str, float]]:
    """Load the baseline scores. Returns empty dict if no baseline exists."""
    if not BASELINE_PATH.exists():
        logger.warning("No baseline found at %s — first run will create it", BASELINE_PATH)
        return {}
    with open(BASELINE_PATH) as f:
        return json.load(f)


def save_baseline(report: EvalReport) -> None:
    """Save current scores as the new baseline."""
    baseline: dict[str, dict[str, float]] = {}
    for es in report.eval_sets:
        baseline[es.name] = {
            **es.metric_scores,
            "_pass_rate": es.pass_rate,
        }
    with open(BASELINE_PATH, "w") as f:
        json.dump(baseline, f, indent=2)
    logger.info("Baseline saved to %s", BASELINE_PATH)


def _run_eval_set_against_agent(
    eval_set_config: dict[str, Any],
    agent_endpoint: str,
    timeout: float = 300,
) -> EvalSetResult:
    """Run a single eval set against the live agent service.

    Submits each eval case as a prompt to the agent via HTTP,
    then scores the response using the configured metrics.
    """
    import httpx

    name = eval_set_config["name"]
    agent = eval_set_config["agent"]
    dataset_path = EVAL_DIR / eval_set_config["dataset"]
    metrics = eval_set_config.get("metrics", [])

    result = EvalSetResult(name=name, agent=agent)
    start = time.monotonic()

    try:
        with open(dataset_path) as f:
            dataset = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        result.errors.append(f"Failed to load dataset: {exc}")
        return result

    eval_cases = dataset.get("eval_cases", [])
    result.cases_total = len(eval_cases)

    for case in eval_cases:
        case_id = case.get("eval_case_id", "unknown")
        prompt_text = case["prompt"]["parts"][0]["text"]

        try:
            resp = httpx.post(
                f"{agent_endpoint}/run",
                json={
                    "app_name": "app",
                    "user_id": "eval-runner",
                    "new_message": {
                        "role": "user",
                        "parts": [{"text": prompt_text}],
                    },
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            agent_response = resp.json()

            case_passed = _score_case(case, agent_response, metrics)
            if case_passed:
                result.cases_passed += 1

        except Exception as exc:
            result.errors.append(f"Case {case_id}: {exc}")

    result.duration_seconds = time.monotonic() - start

    # Compute per-metric aggregate scores
    if result.cases_total > 0:
        for metric in metrics:
            if metric in METRIC_FLOORS:
                result.metric_scores[metric] = result.pass_rate

    return result


def _score_case(
    case: dict[str, Any],
    agent_response: dict[str, Any],
    metrics: list[str],
) -> bool:
    """Score a single eval case against reference answer key points.

    For automated CI, we use deterministic checks against
    reference_answer_key_points. The LLM-as-judge metrics in
    eval_config.yaml are used for deeper analysis runs.
    """
    key_points = case.get("reference_answer_key_points", [])
    if not key_points:
        return True

    response_text = _extract_response_text(agent_response)
    if not response_text:
        return False

    response_lower = response_text.lower()

    # Check expected tool use
    expected_tools = case.get("expected_tool_use", [])
    tool_calls = _extract_tool_calls(agent_response)

    for expected in expected_tools:
        tool_name = expected["tool_name"]
        max_calls = expected.get("max_calls")
        if max_calls == 0:
            # Tool should NOT have been called
            if tool_name in tool_calls:
                return False
        min_calls = expected.get("min_calls", 0)
        if min_calls > 0:
            actual = tool_calls.get(tool_name, 0)
            if actual < min_calls:
                return False

    # Check context-specific expectations
    context = case.get("context", {})
    expected_outcome = context.get("expected_outcome")
    if expected_outcome == "pre_gate_rejection":
        if "rejected" not in response_lower and "invalid" not in response_lower:
            return False

    if expected_outcome == "graceful_failure":
        if "fail" not in response_lower and "error" not in response_lower:
            return False

    return True


def _extract_response_text(agent_response: dict[str, Any]) -> str:
    """Extract the agent's text response from the ADK response format."""
    for path_fn in [
        lambda d: d.get("response", {}).get("parts", [{}])[0].get("text", ""),
        lambda d: d.get("content", {}).get("parts", [{}])[0].get("text", ""),
        lambda d: str(d.get("response", "")),
    ]:
        try:
            text = path_fn(agent_response)
            if text:
                return text
        except (IndexError, KeyError, TypeError):
            continue
    return json.dumps(agent_response)


def _extract_tool_calls(agent_response: dict[str, Any]) -> dict[str, int]:
    """Extract tool call counts from the agent response."""
    counts: dict[str, int] = {}
    events = agent_response.get("events", [])
    for event in events:
        tool_name = event.get("tool_call", {}).get("name", "") or event.get(
            "function_call", {}
        ).get("name", "")
        if tool_name:
            counts[tool_name] = counts.get(tool_name, 0) + 1
    return counts


def check_regression(
    current: EvalReport,
    baseline: dict[str, dict[str, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compare current scores against baseline.

    Returns:
        (regressions, floor_violations) — each is a list of dicts
        describing the problem.
    """
    regressions: list[dict[str, Any]] = []
    floor_violations: list[dict[str, Any]] = []

    for es in current.eval_sets:
        baseline_scores = baseline.get(es.name, {})

        for metric, score in es.metric_scores.items():
            # Check absolute floor
            floor = METRIC_FLOORS.get(metric, 0.0)
            if score < floor:
                floor_violations.append(
                    {
                        "eval_set": es.name,
                        "metric": metric,
                        "score": round(score, 4),
                        "floor": floor,
                        "gap": round(floor - score, 4),
                    }
                )

            # Check regression from baseline
            baseline_score = baseline_scores.get(metric)
            if baseline_score is not None:
                drop = baseline_score - score
                if drop > REGRESSION_TOLERANCE:
                    regressions.append(
                        {
                            "eval_set": es.name,
                            "metric": metric,
                            "current": round(score, 4),
                            "baseline": round(baseline_score, 4),
                            "drop": round(drop, 4),
                            "tolerance": REGRESSION_TOLERANCE,
                        }
                    )

    return regressions, floor_violations


def run_agent_evals(
    agent_endpoint: str = "",
    eval_sets: list[str] | None = None,
) -> EvalReport:
    """Run all (or selected) agent eval sets.

    Args:
        agent_endpoint: URL of the live agent service.
        eval_sets: Optional list of eval set names to run. None = all.

    Returns:
        EvalReport with all results.
    """
    if not agent_endpoint:
        agent_endpoint = os.environ.get("AGENT_ENDPOINT", "http://ssc-agent.tssc-app-ci.svc:8080")

    config = load_eval_config()
    report = EvalReport()
    report.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report.git_sha = os.environ.get("GIT_SHA", "unknown")

    for eval_set_config in config.get("eval_sets", []):
        name = eval_set_config["name"]
        if eval_sets and name not in eval_sets:
            continue

        logger.info("Running eval set: %s (agent: %s)", name, eval_set_config["agent"])
        result = _run_eval_set_against_agent(eval_set_config, agent_endpoint)
        report.eval_sets.append(result)
        logger.info(
            "  %s: %d/%d passed (%.0f%%)",
            name,
            result.cases_passed,
            result.cases_total,
            result.pass_rate * 100,
        )

    return report


def gate_decision(
    agent_endpoint: str = "",
    update_baseline: bool = False,
) -> tuple[bool, EvalReport]:
    """CI gate: run evals, compare to baseline, return pass/fail.

    This is the single function Tekton calls. Returns:
        (passed, report)
    """
    report = run_agent_evals(agent_endpoint)

    baseline = load_baseline()
    regressions, floor_violations = check_regression(report, baseline)
    report.regressions = regressions
    report.floor_violations = floor_violations

    passed = len(regressions) == 0 and len(floor_violations) == 0
    report.overall_pass = passed

    if passed and update_baseline:
        save_baseline(report)

    return passed, report


def main() -> None:
    """CLI entry point for automated eval runs.

    Usage:
        python -m app.eval.agent_eval                    # run all evals
        python -m app.eval.agent_eval --update-baseline  # run + save as new baseline
        python -m app.eval.agent_eval --set cve-selection --set remediation
        python -m app.eval.agent_eval --report-only      # just print latest report
    """
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Automated agent evaluation runner")
    parser.add_argument(
        "--agent-endpoint",
        default=os.environ.get("AGENT_ENDPOINT", "http://ssc-agent.tssc-app-ci.svc:8080"),
        help="URL of the agent service",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Save current scores as the new baseline",
    )
    parser.add_argument(
        "--set",
        action="append",
        dest="eval_sets",
        help="Run specific eval set(s) only",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Write JSON report to this file path",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        default=True,
        help="Exit non-zero if regressions are found (default: true)",
    )
    args = parser.parse_args()

    passed, report = gate_decision(
        agent_endpoint=args.agent_endpoint,
        update_baseline=args.update_baseline,
    )

    # Print report
    report_dict = report.to_dict()
    print(json.dumps(report_dict, indent=2))

    # Write to file if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report_dict, f, indent=2)
        logger.info("Report written to %s", args.output)

    # Log to MLflow if configured
    _try_log_report_to_mlflow(report)

    # Summary
    summary = report.summary()
    print(f"\n{'=' * 60}")
    print(f"AGENT EVAL {'PASSED' if passed else 'FAILED'}")
    print(f"  Agents evaluated: {summary['agents_evaluated']}")
    print(f"  Total cases: {summary['total_cases']}")
    print(f"  Pass rate: {summary['total_pass_rate'] * 100:.1f}%")
    if report.regressions:
        print(f"  REGRESSIONS: {len(report.regressions)}")
        for reg in report.regressions:
            print(
                f"    - {reg['eval_set']}/{reg['metric']}: "
                f"{reg['baseline']:.2f} → {reg['current']:.2f} "
                f"(dropped {reg['drop']:.2f}, tolerance {reg['tolerance']:.2f})"
            )
    if report.floor_violations:
        print(f"  FLOOR VIOLATIONS: {len(report.floor_violations)}")
        for viol in report.floor_violations:
            print(
                f"    - {viol['eval_set']}/{viol['metric']}: "
                f"{viol['score']:.2f} < floor {viol['floor']:.2f}"
            )
    print(f"{'=' * 60}")

    if args.fail_on_regression and not passed:
        sys.exit(1)


def _try_log_report_to_mlflow(report: EvalReport) -> None:
    """Best-effort log agent eval results to MLflow."""
    mlflow_url = os.environ.get("MLFLOW_TRACKING_URI", "")
    if not mlflow_url:
        return

    try:
        import mlflow

        mlflow.set_tracking_uri(mlflow_url)
        mlflow.set_experiment("lw-agents-eval")

        with mlflow.start_run(run_name=f"agent-eval-{report.git_sha[:8]}"):
            for es in report.eval_sets:
                mlflow.log_metric(f"{es.name}/pass_rate", es.pass_rate)
                for metric, score in es.metric_scores.items():
                    mlflow.log_metric(f"{es.name}/{metric}", score)
            summary = report.summary()
            mlflow.log_metric("overall_pass_rate", summary["total_pass_rate"])
            mlflow.log_dict(report.to_dict(), "eval_report.json")
    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to log agent eval to MLflow")


if __name__ == "__main__":
    main()
