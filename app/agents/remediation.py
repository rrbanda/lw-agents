"""Remediation Agent — SequentialAgent pipeline that reads the pom.xml,
plans the edit, applies it via OpenCode (ExecuteBashTool), verifies via
Maven build with retry, and opens a PR with HITL approval.

Uses SequentialAgent + LoopAgent for the retry logic, following the same
pattern as test_generation.py. The coordinator delegates here when the
task is dependency remediation.

Note: Workflow cannot yet be used as an LlmAgent sub-agent (ADK limitation),
so we use SequentialAgent + LoopAgent which are compatible.
"""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.config import BASE_BRANCH, MODEL, SKILLS_DIR, build_bash_tool
from app.policy.post_gate import post_gate_callback
from app.policy.pre_gate import pre_gate_callback
from app.tools.scm_tools import clone_repository_tool, create_pull_request_tool


def _create_plan_agent(name: str = "remediation_planner") -> LlmAgent:
    """Create a remediation planner/executor agent.

    Args:
        name: Unique agent name (needed to avoid parent conflicts when
              the same kind of agent appears in multiple pipeline stages).
    """
    skills = [
        load_skill_from_dir(SKILLS_DIR / "maven-remediation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)
    bash_tool = build_bash_tool()

    return LlmAgent(
        name=name,
        model=MODEL,
        before_agent_callback=pre_gate_callback,
        after_agent_callback=post_gate_callback,
        instruction=(
            "You are a Maven remediation engineer. You MUST execute these steps "
            "in order using your tools. Do NOT just describe what you would do — "
            "actually call the tools.\n\n"
            "STEP 1 — CLONE: You MUST call clone_repository with the repository "
            "URL and branch from the user's message. This is required.\n\n"
            "STEP 2 — SKILL: Call load_skill to load the maven-remediation skill.\n\n"
            "STEP 3 — READ: Use execute_bash to run 'cat pom.xml' in the cloned "
            "repo to understand the project structure.\n\n"
            "STEP 4 — FIX: Use execute_bash to run opencode to apply the "
            "dependency version change in pom.xml.\n\n"
            "STEP 5 — BUILD: Use execute_bash to run 'mvn -B -q -DskipTests install' "
            "to verify the build. If it fails, report 'BUILD FAILURE'.\n\n"
            "STEP 6 — TEST: If build passes, run 'mvn -B -q verify' for tests.\n\n"
            "STEP 7 — REPORT: Report 'BUILD SUCCESS' or 'BUILD FAILURE'.\n\n"
            "Extract CVE details, repository URL, and branch from the user's message."
        ),
        description="Plans and applies a Maven dependency version bump using OpenCode.",
        tools=[skill_toolset, bash_tool, clone_repository_tool],
        output_key="remediation_output",
    )


class BuildResultChecker(BaseAgent):
    """Checks the build result and escalates (stops loop) on success.

    Similar to TestEscalationChecker in test_generation.py. When the
    remediation planner reports BUILD SUCCESS, this agent escalates to
    exit the retry loop. On failure, it lets the loop continue.
    """

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        output = str(ctx.session.state.get("remediation_output", "")).lower()
        build_status = ctx.session.state.get("build_status", "")

        is_success = build_status == "pass" or "build success" in output
        is_failure = build_status == "fail" or (
            any(kw in output for kw in ("build failure", "compilation error", "maven error"))
            and "no errors" not in output
            and "did not fail" not in output
        )

        if is_success:
            ctx.session.state["build_passed"] = True
            ctx.session.state["structured_result"] = {
                "CHANGED": "1",
                "BUILD_STATUS": "SUCCESS",
            }
            yield Event(
                author=self.name,
                actions=EventActions(escalate=True),
            )
        elif is_failure:
            retry_count = ctx.session.state.get("retry_count", 0) + 1
            ctx.session.state["retry_count"] = retry_count
            ctx.session.state["build_passed"] = False
            yield Event(author=self.name)
        else:
            # Ambiguous output — fail-closed: treat as failure, let retry loop continue
            retry_count = ctx.session.state.get("retry_count", 0) + 1
            ctx.session.state["retry_count"] = retry_count
            ctx.session.state["build_passed"] = False
            yield Event(author=self.name)


def _create_pr_opener() -> LlmAgent:
    """Agent that opens the remediation PR."""
    return LlmAgent(
        name="remediation_pr_opener",
        model=MODEL,
        instruction=(
            "Open a pull request with the remediation changes. "
            "Get the CVE details from session state (remediation_output) "
            "or from earlier conversation context.\n"
            "- Branch naming: rhtpa/remediate-<cve_id>-<timestamp>\n"
            "- Title: Remediate <cve_id>: <package> -> <fixed_version>\n"
            "- Stage files: pom.xml */pom.xml REMEDIATION.md\n"
            "- Base branch: " + BASE_BRANCH + "\n\n"
            "If the build did not pass (check state), report the failure "
            "instead of opening a PR."
        ),
        description="Opens a remediation pull request.",
        tools=[create_pull_request_tool],
        output_key="pr_result",
    )


def create_remediation_agent() -> SequentialAgent:
    """Factory: builds the SequentialAgent + LoopAgent remediation pipeline.

    Architecture: plan_agent -> retry_loop(checker -> retry_planner) -> pr_opener

    The retry loop runs up to 3 times. On build success, BuildResultChecker
    escalates to stop the loop. The PR opener only submits if build passed.
    """
    retry_loop = LoopAgent(
        name="remediation_retry_loop",
        sub_agents=[
            BuildResultChecker(name="build_result_checker"),
            _create_plan_agent("remediation_retry_planner"),
        ],
        max_iterations=3,
    )

    return SequentialAgent(
        name="remediation",
        description=(
            "Remediates a Maven dependency vulnerability: reads pom.xml, "
            "applies the fix via OpenCode, verifies with Maven (up to 3 "
            "retries), and opens a pull request."
        ),
        sub_agents=[
            _create_plan_agent("initial_remediation_planner"),
            retry_loop,
            _create_pr_opener(),
        ],
    )
