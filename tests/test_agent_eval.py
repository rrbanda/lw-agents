"""Unit tests for the automated agent evaluation system.

Tests the pure logic: scoring, regression detection, baseline management.
No network calls, no live agents.
"""

from __future__ import annotations


class TestEvalSetResult:
    """Tests for EvalSetResult computed properties."""

    def setup_method(self):
        from app.eval.agent_eval import EvalSetResult

        self.EvalSetResult = EvalSetResult

    def test_pass_rate_all_passed(self):
        r = self.EvalSetResult(name="test", agent="test_agent", cases_total=10, cases_passed=10)
        assert r.pass_rate == 1.0

    def test_pass_rate_none_passed(self):
        r = self.EvalSetResult(name="test", agent="test_agent", cases_total=5, cases_passed=0)
        assert r.pass_rate == 0.0

    def test_pass_rate_empty(self):
        r = self.EvalSetResult(name="test", agent="test_agent")
        assert r.pass_rate == 0.0

    def test_pass_rate_partial(self):
        r = self.EvalSetResult(name="test", agent="test_agent", cases_total=4, cases_passed=3)
        assert r.pass_rate == 0.75

    def test_to_dict_structure(self):
        r = self.EvalSetResult(
            name="cve-selection",
            agent="cve_selection",
            cases_total=7,
            cases_passed=5,
            metric_scores={"cve_selection_accuracy": 0.7142},
        )
        d = r.to_dict()
        assert d["name"] == "cve-selection"
        assert d["agent"] == "cve_selection"
        assert d["cases_total"] == 7
        assert d["pass_rate"] == 0.7143  # rounded to 4 decimals


class TestCheckRegression:
    """Tests for regression detection logic."""

    def setup_method(self):
        from app.eval.agent_eval import (
            EvalReport,
            EvalSetResult,
            check_regression,
        )

        self.EvalReport = EvalReport
        self.EvalSetResult = EvalSetResult
        self.check_regression = check_regression

    def test_no_regression_no_violations(self):
        report = self.EvalReport(
            eval_sets=[
                self.EvalSetResult(
                    name="cve-selection",
                    agent="cve_selection",
                    metric_scores={
                        "cve_selection_accuracy": 0.85,
                        "version_not_hallucinated": 0.95,
                    },
                ),
            ]
        )
        baseline = {
            "cve-selection": {
                "cve_selection_accuracy": 0.80,
                "version_not_hallucinated": 0.95,
            }
        }
        regressions, violations = self.check_regression(report, baseline)
        assert len(regressions) == 0
        assert len(violations) == 0

    def test_regression_detected(self):
        report = self.EvalReport(
            eval_sets=[
                self.EvalSetResult(
                    name="cve-selection",
                    agent="cve_selection",
                    metric_scores={
                        "cve_selection_accuracy": 0.50,
                    },
                ),
            ]
        )
        baseline = {
            "cve-selection": {
                "cve_selection_accuracy": 0.80,
            }
        }
        regressions, violations = self.check_regression(report, baseline)
        assert len(regressions) == 1
        assert regressions[0]["metric"] == "cve_selection_accuracy"
        assert regressions[0]["drop"] == 0.30

    def test_floor_violation_detected(self):
        report = self.EvalReport(
            eval_sets=[
                self.EvalSetResult(
                    name="cve-selection",
                    agent="cve_selection",
                    metric_scores={
                        "cve_selection_accuracy": 0.30,
                    },
                ),
            ]
        )
        baseline = {}  # No baseline — still should catch floor violation
        regressions, violations = self.check_regression(report, baseline)
        assert len(violations) == 1
        assert violations[0]["metric"] == "cve_selection_accuracy"
        assert violations[0]["score"] == 0.30

    def test_within_tolerance_no_regression(self):
        """A small drop within tolerance should NOT trigger regression."""
        report = self.EvalReport(
            eval_sets=[
                self.EvalSetResult(
                    name="test",
                    agent="test",
                    metric_scores={"cve_selection_accuracy": 0.75},
                ),
            ]
        )
        baseline = {"test": {"cve_selection_accuracy": 0.80}}
        regressions, _ = self.check_regression(report, baseline)
        # Drop of 0.05 is within tolerance of 0.10
        assert len(regressions) == 0

    def test_improvement_no_regression(self):
        report = self.EvalReport(
            eval_sets=[
                self.EvalSetResult(
                    name="test",
                    agent="test",
                    metric_scores={"cve_selection_accuracy": 0.95},
                ),
            ]
        )
        baseline = {"test": {"cve_selection_accuracy": 0.80}}
        regressions, _ = self.check_regression(report, baseline)
        assert len(regressions) == 0

    def test_empty_baseline_only_checks_floors(self):
        report = self.EvalReport(
            eval_sets=[
                self.EvalSetResult(
                    name="test",
                    agent="test",
                    metric_scores={"cve_selection_accuracy": 0.80},
                ),
            ]
        )
        regressions, violations = self.check_regression(report, {})
        assert len(regressions) == 0
        assert len(violations) == 0  # 0.80 > floor of 0.70


class TestEvalReport:
    """Tests for EvalReport summary generation."""

    def setup_method(self):
        from app.eval.agent_eval import EvalReport, EvalSetResult

        self.EvalReport = EvalReport
        self.EvalSetResult = EvalSetResult

    def test_summary_aggregates(self):
        report = self.EvalReport(
            eval_sets=[
                self.EvalSetResult(name="a", agent="a", cases_total=10, cases_passed=8),
                self.EvalSetResult(name="b", agent="b", cases_total=5, cases_passed=5),
            ]
        )
        s = report.summary()
        assert s["agents_evaluated"] == 2
        assert s["total_cases"] == 15
        assert s["total_passed"] == 13
        assert s["total_pass_rate"] == round(13 / 15, 4)

    def test_summary_empty(self):
        report = self.EvalReport()
        s = report.summary()
        assert s["agents_evaluated"] == 0
        assert s["total_cases"] == 0
        assert s["total_pass_rate"] == 0.0


class TestScoreCase:
    """Tests for individual eval case scoring."""

    def setup_method(self):
        from app.eval.agent_eval import _score_case

        self.score_case = _score_case

    def test_no_key_points_passes(self):
        """Cases without reference_answer_key_points always pass."""
        case = {"eval_case_id": "test"}
        result = self.score_case(case, {"response": "anything"}, [])
        assert result is True

    def test_max_calls_zero_blocks_tool(self):
        case = {
            "eval_case_id": "test",
            "expected_tool_use": [{"tool_name": "create_pull_request", "max_calls": 0}],
            "reference_answer_key_points": ["something"],
        }
        response = {
            "events": [{"tool_call": {"name": "create_pull_request"}}],
            "response": {"parts": [{"text": "opened a PR"}]},
        }
        result = self.score_case(case, response, [])
        assert result is False

    def test_min_calls_required(self):
        case = {
            "eval_case_id": "test",
            "expected_tool_use": [{"tool_name": "check_version_exists", "min_calls": 1}],
            "reference_answer_key_points": ["verified"],
        }
        response = {
            "events": [],
            "response": {"parts": [{"text": "verified the version"}]},
        }
        result = self.score_case(case, response, [])
        assert result is False

    def test_pre_gate_rejection_detected(self):
        case = {
            "eval_case_id": "test",
            "context": {"expected_outcome": "pre_gate_rejection"},
            "reference_answer_key_points": ["rejected"],
        }
        response = {
            "response": {"parts": [{"text": "Request rejected by pre-gate validation"}]},
        }
        result = self.score_case(case, response, [])
        assert result is True

    def test_pre_gate_rejection_missed(self):
        case = {
            "eval_case_id": "test",
            "context": {"expected_outcome": "pre_gate_rejection"},
            "reference_answer_key_points": ["rejected"],
        }
        response = {
            "response": {"parts": [{"text": "I successfully remediated the CVE"}]},
        }
        result = self.score_case(case, response, [])
        assert result is False


class TestLoadBaseline:
    """Tests for baseline loading."""

    def test_baseline_file_exists(self):
        from app.eval.agent_eval import load_baseline

        baseline = load_baseline()
        assert isinstance(baseline, dict)
        assert "cve-selection" in baseline
        assert "remediation" in baseline
        assert "fix-validation" in baseline

    def test_baseline_has_expected_metrics(self):
        from app.eval.agent_eval import load_baseline

        baseline = load_baseline()
        sel = baseline["cve-selection"]
        assert "cve_selection_accuracy" in sel
        assert "version_not_hallucinated" in sel

    def test_baseline_values_are_reasonable(self):
        from app.eval.agent_eval import load_baseline

        baseline = load_baseline()
        for eval_set_name, scores in baseline.items():
            for metric, value in scores.items():
                if metric.startswith("_"):
                    continue
                assert 0.0 <= value <= 1.0, f"{eval_set_name}/{metric} = {value} is out of range"


class TestLoadEvalConfig:
    """Tests for eval config loading."""

    def test_config_loads(self):
        from app.eval.agent_eval import load_eval_config

        config = load_eval_config()
        assert "eval_sets" in config
        assert "custom_metrics" in config

    def test_all_agents_have_eval_sets(self):
        from app.eval.agent_eval import load_eval_config

        config = load_eval_config()
        agents = {es["agent"] for es in config["eval_sets"]}
        expected = {
            "ssc_coordinator",
            "cve_selection",
            "cve_analysis",
            "remediation",
            "test_generation",
            "fix_validation",
        }
        assert agents == expected

    def test_all_datasets_exist(self):

        from app.eval.agent_eval import EVAL_DIR, load_eval_config

        config = load_eval_config()
        for es in config["eval_sets"]:
            dataset_path = EVAL_DIR / es["dataset"]
            assert dataset_path.exists(), f"Missing dataset: {dataset_path}"
