"""EvalHub runner — orchestrates eval submission and result tracking.

Entry points:
  - run_safety_gate()   — CI gate for safety benchmarks
  - run_cve_eval()      — CVE-specific evaluation with MLflow tracking
  - run_full_suite()    — Both safety + CVE evals
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.eval.client import EvalHubClient
from app.eval.cve_metrics import (
    CVEEvalResult,
    evaluate_remediation_batch,
    evaluate_selection_batch,
)

logger = logging.getLogger(__name__)

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "eval"


def run_safety_gate(
    config_path: str | Path | None = None,
    timeout: float = 1800,
) -> tuple[bool, dict[str, Any]]:
    """Run the safety benchmark gate.

    Args:
        config_path: Path to EvalHub config. Defaults to safety-baseline.
        timeout: Max seconds to wait.

    Returns:
        (passed, result_dict)
    """
    if config_path is None:
        config_path = CONFIGS_DIR / "evalhub-safety-baseline.yaml"

    with EvalHubClient() as client:
        passed, result = client.check_gate(config_path=config_path, timeout=timeout)
    logger.info("Safety gate %s", "PASSED" if passed else "FAILED")
    return passed, result


def run_security_scan(
    config_path: str | Path | None = None,
    timeout: float = 1800,
) -> tuple[bool, dict[str, Any]]:
    """Run the Garak security scan gate.

    Args:
        config_path: Path to EvalHub config. Defaults to garak-security.
        timeout: Max seconds to wait.

    Returns:
        (passed, result_dict)
    """
    if config_path is None:
        config_path = CONFIGS_DIR / "evalhub-garak-security.yaml"

    with EvalHubClient() as client:
        passed, result = client.check_gate(config_path=config_path, timeout=timeout)
    logger.info("Security scan %s", "PASSED" if passed else "FAILED")
    return passed, result


def run_cve_eval(
    selections: list[dict[str, Any]] | None = None,
    remediations: list[dict[str, Any]] | None = None,
    experiment_name: str = "lw-agents-cve-eval",
) -> CVEEvalResult:
    """Run CVE-specific evaluation and optionally report to MLflow.

    Args:
        selections: List of CVE selection results to evaluate.
        remediations: List of remediation results to evaluate.
        experiment_name: MLflow experiment name.

    Returns:
        Aggregated CVEEvalResult.
    """
    combined = CVEEvalResult()

    if selections:
        sel_result = evaluate_selection_batch(selections)
        combined.total_cves = sel_result.total_cves
        combined.selections_valid = sel_result.selections_valid
        combined.errors.extend(sel_result.errors)
        combined.benchmark_scores.update(sel_result.benchmark_scores)

    if remediations:
        rem_result = evaluate_remediation_batch(remediations)
        combined.remediations_attempted = rem_result.remediations_attempted
        combined.remediations_succeeded = rem_result.remediations_succeeded
        combined.fixes_validated = rem_result.fixes_validated
        combined.fixes_safe = rem_result.fixes_safe
        combined.prs_opened = rem_result.prs_opened
        combined.prs_with_tests = rem_result.prs_with_tests
        combined.errors.extend(rem_result.errors)
        combined.benchmark_scores.update(rem_result.benchmark_scores)

    _try_log_to_mlflow(combined, experiment_name)

    return combined


def run_full_suite(
    selections: list[dict[str, Any]] | None = None,
    remediations: list[dict[str, Any]] | None = None,
    safety_timeout: float = 1800,
) -> dict[str, Any]:
    """Run the full evaluation suite: safety gate + CVE eval.

    Returns:
        Dict with 'safety_gate', 'security_scan', and 'cve_eval' results.
    """
    results: dict[str, Any] = {}

    logger.info("=== Running Safety Gate ===")
    safety_passed, safety_result = run_safety_gate(timeout=safety_timeout)
    results["safety_gate"] = {
        "passed": safety_passed,
        "details": safety_result,
    }

    logger.info("=== Running Security Scan ===")
    sec_passed, sec_result = run_security_scan(timeout=safety_timeout)
    results["security_scan"] = {
        "passed": sec_passed,
        "details": sec_result,
    }

    logger.info("=== Running CVE Eval ===")
    cve_result = run_cve_eval(selections, remediations)
    results["cve_eval"] = cve_result.to_dict()

    all_passed = safety_passed and sec_passed
    results["overall_pass"] = all_passed
    logger.info("Full suite %s", "PASSED" if all_passed else "FAILED")

    return results


def _try_log_to_mlflow(
    result: CVEEvalResult,
    experiment_name: str,
) -> None:
    """Best-effort log metrics to MLflow if available."""
    mlflow_url = os.environ.get("MLFLOW_TRACKING_URI", "")
    if not mlflow_url:
        logger.debug("MLFLOW_TRACKING_URI not set, skipping MLflow logging")
        return

    try:
        import mlflow

        mlflow.set_tracking_uri(mlflow_url)
        mlflow.set_experiment(experiment_name)

        with mlflow.start_run(run_name="cve-eval"):
            for metric in result.to_evalhub_metrics():
                mlflow.log_metric(metric["name"], metric["value"])
            mlflow.log_dict(result.to_dict(), "cve_eval_result.json")
            logger.info("Logged CVE eval results to MLflow")
    except ImportError:
        logger.warning("mlflow not installed, skipping MLflow logging")
    except Exception:
        logger.exception("Failed to log to MLflow")
