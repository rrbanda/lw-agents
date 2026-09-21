"""Integration tests — end-to-end pipeline with mock agents (no LLM needed).

Tests the full PipelineRunner flow: config loading, agent dispatch,
result persistence, resume, early termination, and cost enforcement.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

from app.results import AgentResult, AgentStatus
from app.runner import REMEDIATION_AGENT_ORDER, PipelineRunner, RunConfig


class TestPipelineRunnerE2E:
    """End-to-end pipeline tests with mocked agent execution."""

    def _make_config(self, tmpdir: str, **overrides) -> RunConfig:
        defaults = {
            "vuln_id": "CVE-2024-9999",
            "component": "test-lib",
            "version": "1.0.0",
            "run_dir": tmpdir,
            "max_cost_usd": 10.0,
        }
        defaults.update(overrides)
        return RunConfig(**defaults)

    def _mock_run_agent(self, results_map: dict[str, AgentResult]):
        """Create a mock _run_agent that returns preset results."""
        def mock_run(name: str) -> AgentResult:
            if name in results_map:
                return results_map[name]
            return AgentResult(
                agent=name,
                status=AgentStatus.SUCCESS,
                duration_seconds=0.1,
                data={"selected": "1", "cve_id": "CVE-2024-9999"},
            )
        return mock_run

    def test_full_pipeline_all_success(self):
        """All agents succeed — pipeline completes normally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            runner = PipelineRunner(config)

            mock = self._mock_run_agent({
                name: AgentResult(
                    agent=name,
                    status=AgentStatus.SUCCESS,
                    duration_seconds=0.1,
                    data={"selected": "1", "cve_id": "CVE-2024-9999"},
                )
                for name in REMEDIATION_AGENT_ORDER
            })

            with patch.object(runner, "_run_agent", side_effect=mock):
                results = runner.run()

            assert len(results) == 5
            assert all(r.status == AgentStatus.SUCCESS for r in results)

            # Verify results persisted to disk
            report_dir = config.run_report_dir
            for name in REMEDIATION_AGENT_ORDER:
                path = os.path.join(report_dir, f"{name}.json")
                assert os.path.exists(path), f"Missing {path}"

            # Verify summary written
            summary_path = os.path.join(report_dir, "run_summary.json")
            assert os.path.exists(summary_path)
            with open(summary_path) as f:
                summary = json.load(f)
            assert summary["status"] == "success"
            assert summary["agents_succeeded"] == 5

    def test_early_termination_no_selection(self):
        """Pipeline stops when cve_selection finds nothing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            runner = PipelineRunner(config)

            mock = self._mock_run_agent({
                "cve_selection": AgentResult(
                    agent="cve_selection",
                    status=AgentStatus.SUCCESS,
                    duration_seconds=0.1,
                    data={"selected": "0", "justification": "No CVEs"},
                ),
            })

            with patch.object(runner, "_run_agent", side_effect=mock):
                results = runner.run()

            # Should stop after selection — no remediation/test/validation
            assert len(results) == 1
            assert results[0].agent == "cve_selection"

    def test_early_termination_on_failure(self):
        """Pipeline stops when an agent fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            runner = PipelineRunner(config)

            mock = self._mock_run_agent({
                "cve_selection": AgentResult(
                    agent="cve_selection",
                    status=AgentStatus.SUCCESS,
                    duration_seconds=0.1,
                    data={"selected": "1", "cve_id": "CVE-2024-9999"},
                ),
                "cve_analysis": AgentResult(
                    agent="cve_analysis",
                    status=AgentStatus.FAILED,
                    duration_seconds=0.1,
                    error="Analysis crashed",
                ),
            })

            with patch.object(runner, "_run_agent", side_effect=mock):
                results = runner.run()

            assert len(results) == 2
            assert results[1].status == AgentStatus.FAILED

    def test_cost_budget_enforcement(self):
        """Pipeline stops when cost budget is exceeded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir, max_cost_usd=0.001)
            runner = PipelineRunner(config)

            mock = self._mock_run_agent({
                "cve_selection": AgentResult(
                    agent="cve_selection",
                    status=AgentStatus.SUCCESS,
                    duration_seconds=0.1,
                    data={"selected": "1", "cve_id": "CVE-2024-9999"},
                    token_usage={"cost_usd": 0.01},
                ),
            })

            with patch.object(runner, "_run_agent", side_effect=mock):
                results = runner.run()

            # cve_selection succeeds, but cve_analysis should be
            # halted with NEEDS_ESCALATION due to cost
            assert len(results) == 2
            assert results[1].status == AgentStatus.NEEDS_ESCALATION
            assert "Cost" in (results[1].error or "")

    def test_resume_from_checkpoint(self):
        """Pipeline resumes from last successful agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir, resume=True)
            report_dir = config.run_report_dir
            os.makedirs(report_dir, exist_ok=True)

            # Write prior results for first 2 agents
            for name in ["cve_selection", "cve_analysis"]:
                AgentResult(
                    agent=name,
                    status=AgentStatus.SUCCESS,
                    duration_seconds=1.0,
                    data={"selected": "1", "cve_id": "CVE-2024-9999"},
                ).to_file(report_dir)

            runner = PipelineRunner(config)
            call_log = []

            def mock_run(name: str) -> AgentResult:
                call_log.append(name)
                return AgentResult(
                    agent=name,
                    status=AgentStatus.SUCCESS,
                    duration_seconds=0.1,
                    data={"selected": "1"},
                )

            with patch.object(runner, "_run_agent", side_effect=mock_run):
                runner.run()

            # Should only run agents 3-5 (remediation, test_gen, validation)
            assert "cve_selection" not in call_log
            assert "cve_analysis" not in call_log
            assert "remediation" in call_log

    def test_selective_agents(self):
        """Only run specified agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(
                tmpdir,
                agents=["cve_selection"],
            )
            runner = PipelineRunner(config)

            mock = self._mock_run_agent({
                "cve_selection": AgentResult(
                    agent="cve_selection",
                    status=AgentStatus.SUCCESS,
                    duration_seconds=0.1,
                    data={"selected": "1", "cve_id": "CVE-2024-9999"},
                ),
            })

            with patch.object(runner, "_run_agent", side_effect=mock):
                results = runner.run()

            assert len(results) == 1
            assert results[0].agent == "cve_selection"

    def test_metrics_snapshot_written(self):
        """Verify agent-metrics.jsonl is written after each agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir, agents=["cve_selection"])
            runner = PipelineRunner(config)

            mock = self._mock_run_agent({
                "cve_selection": AgentResult(
                    agent="cve_selection",
                    status=AgentStatus.SUCCESS,
                    duration_seconds=0.5,
                    data={"selected": "1"},
                ),
            })

            with patch.object(runner, "_run_agent", side_effect=mock):
                runner.run()

            metrics_path = os.path.join(
                config.run_report_dir, "agent-metrics.jsonl"
            )
            assert os.path.exists(metrics_path)
            with open(metrics_path) as f:
                lines = f.readlines()
            assert len(lines) >= 1
            record = json.loads(lines[0])
            assert record["agent"] == "cve_selection"
            assert record["status"] == "success"

    def test_yaml_config_roundtrip(self):
        """Verify YAML config loading and pipeline execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = os.path.join(tmpdir, "config.yaml")
            with open(yaml_path, "w") as f:
                f.write(
                    "vuln_id: CVE-2024-8888\n"
                    "component: my-lib\n"
                    "max_cost_usd: 5.0\n"
                    f"run_dir: {tmpdir}\n"
                    "agents:\n"
                    "  - cve_selection\n"
                )

            config = RunConfig.from_yaml(yaml_path)
            assert config.vuln_id == "CVE-2024-8888"
            assert config.max_cost_usd == 5.0
            assert config.agents == ["cve_selection"]

            runner = PipelineRunner(config)
            mock = self._mock_run_agent({
                "cve_selection": AgentResult(
                    agent="cve_selection",
                    status=AgentStatus.SUCCESS,
                    data={"selected": "1", "cve_id": "CVE-2024-8888"},
                ),
            })

            with patch.object(runner, "_run_agent", side_effect=mock):
                results = runner.run()

            assert len(results) == 1
            assert results[0].data["cve_id"] == "CVE-2024-8888"
