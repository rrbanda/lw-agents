"""Unit tests for EvalHub integration — no network, no side-effects.

Tests the pure logic in app/eval/cve_metrics.py and app/eval/client.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# CVEEvalResult
# ---------------------------------------------------------------------------


class TestCVEEvalResult:
    """Tests for CVEEvalResult dataclass and its computed properties."""

    def setup_method(self):
        from app.eval.cve_metrics import CVEEvalResult

        self.CVEEvalResult = CVEEvalResult

    def test_empty_result_all_zeros(self):
        r = self.CVEEvalResult()
        assert r.selection_accuracy == 0.0
        assert r.remediation_success_rate == 0.0
        assert r.fix_safety_score == 0.0
        assert r.pr_hygiene_score == 0.0

    def test_selection_accuracy(self):
        r = self.CVEEvalResult(total_cves=10, selections_valid=8)
        assert r.selection_accuracy == 0.8

    def test_remediation_success_rate(self):
        r = self.CVEEvalResult(remediations_attempted=5, remediations_succeeded=4)
        assert r.remediation_success_rate == 0.8

    def test_fix_safety_score(self):
        r = self.CVEEvalResult(fixes_validated=10, fixes_safe=9)
        assert r.fix_safety_score == 0.9

    def test_pr_hygiene_score(self):
        r = self.CVEEvalResult(prs_opened=4, prs_with_tests=3)
        assert r.pr_hygiene_score == 0.75

    def test_to_evalhub_metrics(self):
        r = self.CVEEvalResult(
            total_cves=10,
            selections_valid=8,
            remediations_attempted=5,
            remediations_succeeded=4,
            fixes_validated=10,
            fixes_safe=9,
            prs_opened=4,
            prs_with_tests=3,
        )
        metrics = r.to_evalhub_metrics()
        assert len(metrics) == 4
        names = {m["name"] for m in metrics}
        assert names == {
            "cve_selection_accuracy",
            "remediation_success_rate",
            "fix_safety_score",
            "pr_hygiene_score",
        }

    def test_to_dict_round_trips(self):
        r = self.CVEEvalResult(
            total_cves=3,
            selections_valid=2,
            remediations_attempted=2,
            remediations_succeeded=1,
        )
        d = r.to_dict()
        assert d["total_cves"] == 3
        assert d["selections_valid"] == 2
        assert d["selection_accuracy"] == round(2 / 3, 4)
        assert d["remediation_success_rate"] == 0.5


# ---------------------------------------------------------------------------
# evaluate_selection_batch
# ---------------------------------------------------------------------------


class TestEvaluateSelectionBatch:
    """Tests for batch selection evaluation."""

    def setup_method(self):
        from app.eval.cve_metrics import evaluate_selection_batch

        self.evaluate = evaluate_selection_batch

    def test_all_valid(self):
        selections = [
            {
                "selected": "1",
                "cve_id": "CVE-2024-1234",
                "package": "com.example:lib",
                "current_version": "1.0.0",
                "fixed_version": "1.0.1",
                "justification": "Critical vuln with easy fix",
            },
            {
                "selected": "1",
                "cve_id": "CVE-2024-5678",
                "package": "org.apache:commons",
                "current_version": "2.0",
                "fixed_version": "2.1",
                "justification": "High severity",
            },
        ]
        result = self.evaluate(selections)
        assert result.total_cves == 2
        assert result.selections_valid == 2
        assert result.selection_accuracy == 1.0

    def test_some_invalid(self):
        selections = [
            {
                "selected": "1",
                "cve_id": "CVE-2024-1234",
                "package": "com.example:lib",
                "current_version": "1.0.0",
                "fixed_version": "1.0.1",
                "justification": "Good fix",
            },
            {
                "selected": "1",
                "cve_id": "NOT-A-CVE",
                "package": "bad",
                "current_version": "",
                "fixed_version": "",
                "justification": "",
            },
        ]
        result = self.evaluate(selections)
        assert result.total_cves == 2
        assert result.selections_valid == 1
        assert result.selection_accuracy == 0.5
        assert len(result.errors) > 0

    def test_empty_batch(self):
        result = self.evaluate([])
        assert result.total_cves == 0
        assert result.selection_accuracy == 0.0


# ---------------------------------------------------------------------------
# evaluate_remediation_batch
# ---------------------------------------------------------------------------


class TestEvaluateRemediationBatch:
    """Tests for batch remediation evaluation."""

    def setup_method(self):
        from app.eval.cve_metrics import evaluate_remediation_batch

        self.evaluate = evaluate_remediation_batch

    def test_all_successful(self):
        remediations = [
            {
                "build_passed": True,
                "validation_verdict": "pass",
                "pr_url": "https://git.example.com/pr/1",
                "has_tests": True,
            },
            {
                "build_passed": True,
                "validation_verdict": "passed",
                "pr_url": "https://git.example.com/pr/2",
                "has_tests": True,
            },
        ]
        result = self.evaluate(remediations)
        assert result.remediations_attempted == 2
        assert result.remediations_succeeded == 2
        assert result.remediation_success_rate == 1.0
        assert result.fix_safety_score == 1.0
        assert result.pr_hygiene_score == 1.0

    def test_mixed_results(self):
        remediations = [
            {
                "build_passed": True,
                "validation_verdict": "pass",
                "pr_url": "https://git.example.com/pr/1",
                "has_tests": True,
            },
            {
                "build_passed": False,
                "validation_verdict": "fail",
                "pr_url": "",
                "has_tests": False,
            },
        ]
        result = self.evaluate(remediations)
        assert result.remediation_success_rate == 0.5
        assert result.fix_safety_score == 0.5
        assert result.prs_opened == 1

    def test_empty_batch(self):
        result = self.evaluate([])
        assert result.remediations_attempted == 0
        assert result.remediation_success_rate == 0.0


# ---------------------------------------------------------------------------
# build_evalhub_benchmark_config
# ---------------------------------------------------------------------------


class TestBuildEvalHubBenchmarkConfig:
    """Tests for the EvalHub benchmark config builder."""

    def setup_method(self):
        from app.eval.cve_metrics import (
            CVEEvalResult,
            build_evalhub_benchmark_config,
        )

        self.build = build_evalhub_benchmark_config
        self.CVEEvalResult = CVEEvalResult

    def test_produces_valid_structure(self):
        result = self.CVEEvalResult(total_cves=10, selections_valid=8)
        config = self.build(result)
        assert config["name"] == "lw-agents-cve-eval"
        assert config["provider_id"] == "custom"
        assert len(config["benchmarks"]) == 4
        assert config["metadata"]["source"] == "lw-agents"

    def test_custom_experiment_name(self):
        result = self.CVEEvalResult()
        config = self.build(result, experiment_name="my-test")
        assert config["name"] == "my-test"

    def test_benchmarks_have_thresholds(self):
        result = self.CVEEvalResult(
            total_cves=10,
            selections_valid=10,
            remediations_attempted=5,
            remediations_succeeded=5,
            fixes_validated=5,
            fixes_safe=5,
            prs_opened=5,
            prs_with_tests=5,
        )
        config = self.build(result)
        for benchmark in config["benchmarks"]:
            assert "pass_criteria" in benchmark
            assert "threshold" in benchmark["pass_criteria"]
            threshold = benchmark["pass_criteria"]["threshold"]
            assert 0.0 <= threshold <= 1.0
