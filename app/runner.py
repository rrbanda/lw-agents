"""Pipeline runner — deterministic agent execution with resume, cost control, and gates.

Implements Layers 5 (orchestration) and 6 (retry/self-correction) from the
production upgrade plan. In production mode, agents run linearly in a defined
order. The LLM coordinator in agent.py remains for playground/interactive use.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import yaml

from app.logging_config import bind_run_context, clear_run_context
from app.results import (
    AgentResult,
    AgentStatus,
    RunSummary,
    load_prior_results,
    write_metrics_snapshot,
)
from app.validation import is_valid_cve_id

logger = logging.getLogger(__name__)


# ============================================================================
# L5.1 — Agent execution order
# ============================================================================

REMEDIATION_AGENT_ORDER: list[str] = [
    "cve_selection",
    "cve_analysis",
    "remediation",
    "test_generation",
    "fix_validation",
]

ANALYSIS_ONLY_ORDER: list[str] = [
    "cve_selection",
    "cve_analysis",
]


# ============================================================================
# L5.5 — Cost budget
# ============================================================================


def _check_cost_budget(
    config: "RunConfig",
    results: list[AgentResult],
) -> bool:
    """Return True if the cost budget has been exceeded."""
    if not config.max_cost_usd:
        return False
    total_cost = sum(float(r.token_usage.get("cost_usd", 0.0) or 0.0) for r in results)
    if total_cost >= config.max_cost_usd:
        logger.warning(
            "cost_budget_exceeded total=%.2f budget=%.2f",
            total_cost,
            config.max_cost_usd,
        )
        return True
    return False


# ============================================================================
# L5.3 — Early termination gates
# ============================================================================


def _should_halt(agent_name: str, result: AgentResult) -> tuple[bool, str]:
    """Check if the pipeline should stop after this agent result."""
    if result.status in (AgentStatus.FAILED, AgentStatus.NEEDS_ESCALATION):
        return True, f"Agent {agent_name} {result.status.value}"

    data = result.data

    # Selection found nothing
    if agent_name == "cve_selection" and str(data.get("selected", "0")) != "1":
        return True, "No CVE selected — nothing to remediate"

    # Already fixed
    if data.get("already_fixed"):
        return True, f"Already fixed in version {data.get('fixed_version', '')}"

    return False, ""


# ============================================================================
# L5.6 — YAML run config
# ============================================================================


@dataclass
class RunConfig:
    """Configuration for a pipeline run."""

    vuln_id: str = ""
    component: str = ""
    version: str = ""
    workspace_path: str = ""
    agents: list[str] = field(default_factory=lambda: list(REMEDIATION_AGENT_ORDER))
    max_cost_usd: float = 10.0
    max_retries: int = 3
    run_dir: str = ""
    resume: bool = False

    # Model settings
    model_name: str = ""
    safety_model: str = ""

    # SCM settings
    scm_provider: str = ""
    scm_host: str = ""
    scm_token: str = ""
    repo_url: str = ""
    base_branch: str = "main"

    def __post_init__(self) -> None:
        # Env var overrides
        if not self.vuln_id:
            self.vuln_id = os.environ.get("VULN_ID", "")
        if not self.workspace_path:
            self.workspace_path = os.environ.get("WORKSPACE_PATH", "/workspace/source")
        if not self.model_name:
            self.model_name = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
        if not self.run_dir:
            self.run_dir = os.environ.get("LW_RUN_DIR", "/tmp/lw-agents-runs")

        # Validation
        if self.vuln_id and not is_valid_cve_id(self.vuln_id):
            raise ValueError(f"Invalid vuln_id: {self.vuln_id!r}")
        if self.max_cost_usd < 0:
            raise ValueError(f"max_cost_usd must be >= 0, got {self.max_cost_usd}")

    @property
    def run_key(self) -> str:
        if self.vuln_id and self.component:
            return f"{self.vuln_id.lower()}_{self.component}"
        return self.vuln_id.lower() or "unknown"

    @property
    def run_report_dir(self) -> str:
        return os.path.join(self.run_dir, self.run_key)

    @classmethod
    def from_yaml(cls, path: str) -> "RunConfig":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return cls(
            vuln_id=raw.get("vuln_id", ""),
            component=raw.get("component", ""),
            version=raw.get("version", ""),
            workspace_path=raw.get("workspace_path", ""),
            agents=raw.get("agents", list(REMEDIATION_AGENT_ORDER)),
            max_cost_usd=float(raw.get("max_cost_usd", 10.0)),
            max_retries=int(raw.get("max_retries", 3)),
            run_dir=raw.get("run_dir", ""),
            resume=bool(raw.get("resume", False)),
            model_name=raw.get("model_name", ""),
            safety_model=raw.get("safety_model", ""),
            scm_provider=raw.get("scm_provider", ""),
            scm_host=raw.get("scm_host", ""),
            repo_url=raw.get("repo_url", ""),
            base_branch=raw.get("base_branch", "main"),
        )


# ============================================================================
# L6.1-L6.4 — Retry policy
# ============================================================================


def _is_hopeless_case(build_output: str, attempt_cost: float = 0.0) -> tuple[bool, str]:
    """Detect cases that shouldn't be retried."""
    output_lower = build_output.lower()
    missing_count = sum(
        output_lower.count(p)
        for p in [
            "cannot find symbol",
            "does not exist",
            "error: file not found",
            "no such file or directory",
        ]
    )
    if missing_count > 3:
        return True, f"Too many missing symbols ({missing_count})"

    error_count = sum(
        build_output.count(m)
        for m in [
            "COMPILATION ERROR",
            "] error:",
            "] ERROR:",
        ]
    )
    if error_count > 40:
        return True, f"Too many compile errors ({error_count})"

    if attempt_cost > 2.0:
        return True, f"High first-attempt cost (${attempt_cost:.2f})"

    return False, ""


def _build_feedback(
    build_output: str,
    category: str,
    test_failures: list[str] | None = None,
) -> dict[str, Any]:
    """Build diagnostic feedback for the next retry attempt."""
    return {
        "compile_output": build_output[-3000:],
        "failure_category": category,
        "test_regressions": test_failures or [],
    }


def _find_test_regressions(
    baseline: list[str],
    current: list[str],
) -> list[str]:
    """Find test failures that are regressions (not pre-existing)."""
    baseline_set = set(baseline)
    return [t for t in current if t not in baseline_set]


# ============================================================================
# L8.1 — Progress display
# ============================================================================

_STATUS_EMOJI = {
    AgentStatus.SUCCESS: "✅",
    AgentStatus.FAILED: "❌",
    AgentStatus.SKIPPED: "⏭️",
    AgentStatus.NEEDS_ESCALATION: "⚠️",
}


def _display_agent_start(name: str, index: int, total: int) -> None:
    is_ci = bool(os.environ.get("CI"))
    if is_ci:
        print(
            f"\n\033[0Ksection_start:{int(time.time())}:{name}[collapsed=false]\r\033[0K"
            f"▶ [{index}/{total}] {name}"
        )
    else:
        print(f"\n▶ [{index}/{total}] {name} ...", flush=True)


def _display_agent_end(name: str, index: int, result: AgentResult) -> None:
    emoji = _STATUS_EMOJI.get(result.status, "❓")
    is_ci = bool(os.environ.get("CI"))
    line = f"{emoji} [{index}] {name}: {result.status.value} ({result.duration_seconds:.1f}s)"
    cost = float(result.token_usage.get("cost_usd", 0.0) or 0.0)
    if cost > 0:
        line += f" ${cost:.4f}"
    print(line, flush=True)
    if is_ci:
        print(f"\033[0Ksection_end:{int(time.time())}:{name}\r\033[0K")


# ============================================================================
# L5.1 + L5.2 + L5.7 + L5.8 — Pipeline runner
# ============================================================================


class PipelineRunner:
    """Execute agents linearly with resume, cost control, and structured results."""

    def __init__(self, config: RunConfig) -> None:
        self.config = config

    def run(self) -> list[AgentResult]:
        """Run the configured agents in order."""
        run_id = uuid4().hex[:12]
        bind_run_context(run_id=run_id, cve_id=self.config.vuln_id)

        report_dir = self.config.run_report_dir
        os.makedirs(report_dir, exist_ok=True)

        agent_names = self.config.agents
        all_results: list[AgentResult] = []

        # L5.2 — Resume from disk
        start_index = 0
        if self.config.resume:
            prior = load_prior_results(report_dir, agent_names)
            if prior:
                all_results = prior
                for i, name in enumerate(agent_names):
                    found = any(r.agent == name and r.status == AgentStatus.SUCCESS for r in prior)
                    if found:
                        start_index = i + 1
                    else:
                        break
                logger.info(
                    "pipeline_resume start_index=%d prior=%d",
                    start_index,
                    len(prior),
                )

        wall_start = time.monotonic()
        total = len(agent_names)

        for index, name in enumerate(agent_names):
            if index < start_index:
                continue

            # L5.5 — Cost budget check
            if _check_cost_budget(self.config, all_results):
                result = AgentResult(
                    agent=name,
                    status=AgentStatus.NEEDS_ESCALATION,
                    data={"reason": "Cost budget exceeded"},
                    error=f"Cost limit ${self.config.max_cost_usd:.2f} exceeded",
                )
                all_results.append(result)
                result.to_file(report_dir)
                break

            _display_agent_start(name, index + 1, total)
            bind_run_context(agent_name=name)
            agent_start = time.monotonic()

            try:
                result = self._run_agent(name)
            except Exception as exc:
                result = AgentResult(
                    agent=name,
                    status=AgentStatus.FAILED,
                    duration_seconds=time.monotonic() - agent_start,
                    error=str(exc),
                )

            if not result.duration_seconds:
                result.duration_seconds = time.monotonic() - agent_start

            _display_agent_end(name, index + 1, result)
            all_results.append(result)
            result.to_file(report_dir)

            # L8.4 — Metrics snapshot
            write_metrics_snapshot(report_dir, all_results)

            # L5.3 — Early termination
            should_halt, reason = _should_halt(name, result)
            if should_halt:
                logger.info("pipeline_halt agent=%s reason=%s", name, reason)
                break

        # L5.8 — Run summary
        wall_seconds = time.monotonic() - wall_start
        summary = RunSummary.from_results(
            all_results,
            vuln_id=self.config.vuln_id,
            wall_clock_seconds=wall_seconds,
        )
        summary.to_json(os.path.join(report_dir, "run_summary.json"))
        logger.info(
            "pipeline_complete status=%s agents=%d/%d cost=$%.4f wall=%.1fs",
            summary.status,
            summary.agents_succeeded,
            summary.total_agents,
            summary.total_cost_usd,
            summary.wall_clock_seconds,
        )

        clear_run_context()
        return all_results

    def _run_agent(self, name: str) -> AgentResult:
        """Execute a single ADK agent and return its AgentResult.

        Creates the agent via its factory function, runs it through ADK's
        InMemoryRunner, collects events, and maps the outcome to AgentResult.

        Handles both sync and async calling contexts:
        - If already in an event loop (e.g. called from async test),
          uses nest_asyncio or runs in a new thread.
        - If no event loop, uses asyncio.run().
        """
        import asyncio

        agent = self._create_agent(name)
        if agent is None:
            return AgentResult(
                agent=name,
                status=AgentStatus.SKIPPED,
                data={"reason": f"No factory registered for agent: {name}"},
            )

        try:
            try:
                asyncio.get_running_loop()
                # Already in an async context — run in a new thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self._run_adk_agent(agent, name))
                    return future.result(timeout=120)
            except RuntimeError:
                # No running loop — safe to use asyncio.run()
                return asyncio.run(self._run_adk_agent(agent, name))
        except Exception as exc:
            return AgentResult(
                agent=name,
                status=AgentStatus.FAILED,
                error=str(exc),
            )

    def _create_agent(self, name: str):
        """Look up and instantiate the ADK agent by name."""
        from app.agents.cve_analysis import create_cve_analysis_agent
        from app.agents.cve_selection import create_cve_selection_agent
        from app.agents.remediation import create_remediation_agent
        from app.agents.test_generation import create_test_generation_agent
        from app.agents.validation import create_validation_agent

        factories = {
            "cve_selection": create_cve_selection_agent,
            "cve_analysis": create_cve_analysis_agent,
            "remediation": create_remediation_agent,
            "test_generation": create_test_generation_agent,
            "fix_validation": create_validation_agent,
        }
        factory = factories.get(name)
        return factory() if factory else None

    async def _run_adk_agent(self, agent, name: str) -> AgentResult:
        """Run an ADK agent via InMemoryRunner and collect results."""
        from google.adk.runners import InMemoryRunner
        from google.genai import types as genai_types

        start = time.monotonic()
        runner = InMemoryRunner(agent=agent, app_name=f"lw-pipeline-{name}")

        session = await runner.session_service.create_session(
            app_name=f"lw-pipeline-{name}", user_id="pipeline"
        )

        prompt = self._build_prompt(name)
        final_text = ""

        try:
            async for event in runner.run_async(
                user_id="pipeline",
                session_id=session.id,
                new_message=genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text=prompt)],
                ),
            ):
                if event.is_final_response() and event.content:
                    for part in event.content.parts or []:
                        if hasattr(part, "text") and part.text:
                            final_text += part.text
        except Exception as exc:
            return AgentResult(
                agent=name,
                status=AgentStatus.FAILED,
                duration_seconds=time.monotonic() - start,
                error=str(exc),
            )

        # Extract structured data from session state first
        data = dict(session.state) if hasattr(session, "state") else {}
        tekton_fields = data.get("structured_result", {})

        # If session state is empty, try parsing the agent's JSON output
        if not tekton_fields or all(v in ("0", "") for v in tekton_fields.values()):
            from app.callbacks import _extract_json_object

            parsed = _extract_json_object(final_text)
            if parsed:
                for key, val in parsed.items():
                    k_upper = key.upper()
                    k_lower = key.lower()
                    if k_lower == "selected":
                        tekton_fields["SELECTED"] = "1" if val else "0"
                    elif k_lower == "cve_id":
                        tekton_fields["CVE_ID"] = str(val)
                        tekton_fields["cve_id"] = str(val)
                    elif k_lower == "package":
                        tekton_fields["PACKAGE"] = str(val)
                        tekton_fields["package"] = str(val)
                    elif k_lower in ("current_version", "fixed_version", "justification"):
                        tekton_fields[k_upper] = str(val)
                        tekton_fields[k_lower] = str(val)
                # Also store as typed data
                tekton_fields["selected"] = tekton_fields.get("SELECTED", "0")

        # Determine status
        status = AgentStatus.SUCCESS
        selected = tekton_fields.get("SELECTED", tekton_fields.get("selected", "0"))
        if name == "cve_selection" and str(selected) not in ("1", "true", "True"):
            status = AgentStatus.NEEDS_ESCALATION

        return AgentResult(
            agent=name,
            status=status,
            duration_seconds=time.monotonic() - start,
            data={
                **tekton_fields,
                "raw_output": final_text[:5000],
            },
        )

    def _build_prompt(self, name: str) -> str:
        """Build the initial prompt for a pipeline agent."""
        c = self.config
        parts = []
        if c.vuln_id:
            parts.append(f"CVE: {c.vuln_id}")
        if c.component:
            parts.append(f"Component: {c.component}")
        if c.version:
            parts.append(f"Version: {c.version}")
        if c.workspace_path:
            parts.append(f"Workspace: {c.workspace_path}")
        if c.repo_url:
            parts.append(f"Repository: {c.repo_url}")

        actions = {
            "cve_selection": "Select the best CVE to remediate.",
            "cve_analysis": "Analyze all CVEs and create issues for fixable ones.",
            "remediation": "Apply the fix for the selected CVE.",
            "test_generation": "Generate tests for the applied fix.",
            "fix_validation": "Validate the applied fix with adversarial review.",
        }
        parts.append(actions.get(name, f"Run the {name} agent."))
        return "\n".join(parts)


# ============================================================================
# L5.7 — CLI interface
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the pipeline runner."""
    import argparse

    parser = argparse.ArgumentParser(description="lw-agents pipeline runner")
    parser.add_argument("--config", "-c", help="YAML run config file")
    parser.add_argument("--vuln-id", help="CVE identifier")
    parser.add_argument("--agents", help="Comma-separated agent names to run")
    parser.add_argument("--max-cost", type=float, help="Maximum cost in USD")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args(argv)

    from app.logging_config import configure_logging

    configure_logging(level=logging.DEBUG if args.debug else logging.INFO)

    if args.config:
        config = RunConfig.from_yaml(args.config)
    else:
        config = RunConfig()

    if args.vuln_id:
        config.vuln_id = args.vuln_id
    if args.agents:
        config.agents = [a.strip() for a in args.agents.split(",")]
    if args.max_cost is not None:
        config.max_cost_usd = args.max_cost
    if args.resume:
        config.resume = True

    runner = PipelineRunner(config)
    results = runner.run()

    failed = any(r.status == AgentStatus.FAILED for r in results)
    escalated = any(r.status == AgentStatus.NEEDS_ESCALATION for r in results)
    return 1 if (failed or escalated) else 0


if __name__ == "__main__":
    sys.exit(main())
