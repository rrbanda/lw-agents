"""Remediation Agent — ADK 2.0 Workflow graph that reads the pom.xml,
plans the edit, applies it via OpenCode (ExecuteBashTool), verifies via
Maven build, and opens a PR.

Uses the Workflow API (graph with conditional routing) from the
ambient-expense-agent pattern, not SequentialAgent.
"""

from __future__ import annotations

import os
import pathlib

from google.adk import Context, Event, Workflow
from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.bash_tool import BashToolPolicy, ExecuteBashTool
from google.adk.tools.skill_toolset import SkillToolset

from app.tools.scm_tools import create_pull_request

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "skills"


def _build_bash_tool(workspace: str) -> ExecuteBashTool:
    return ExecuteBashTool(
        workspace=workspace,
        policy=BashToolPolicy(
            allowed_command_prefixes=(
                "opencode ", "mvn ", "cat ", "ls ", "head ", "grep ", "find ",
            ),
            timeout_seconds=300,
            max_memory_bytes=1024 * 1024 * 1024,
        ),
    )


def read_project(node_input: str, ctx: Context) -> Event:
    """Parse the remediation request and stash params in state."""
    import json
    try:
        params = json.loads(node_input) if isinstance(node_input, str) else {}
    except (json.JSONDecodeError, TypeError):
        params = {}

    ctx.state["cve_id"] = params.get("cve_id", ctx.state.get("cve_id", ""))
    ctx.state["package"] = params.get("package", ctx.state.get("package", ""))
    ctx.state["current_version"] = params.get("current_version", "")
    ctx.state["fixed_version"] = params.get("fixed_version", "")
    ctx.state["justification"] = params.get("justification", "")
    ctx.state["repo_url"] = params.get("repo_url", "")
    ctx.state["workspace"] = params.get("workspace_path",
                                         os.environ.get("WORKSPACE_PATH", ""))
    ctx.state["retry_count"] = 0

    return Event(output=f"Project loaded. Remediating {ctx.state['cve_id']}: "
                        f"{ctx.state['package']} -> {ctx.state['fixed_version']}")


def _create_plan_agent() -> LlmAgent:
    skills = [
        load_skill_from_dir(SKILLS_DIR / "maven-remediation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)
    workspace = os.environ.get("WORKSPACE_PATH", "/workspace/source")
    bash_tool = _build_bash_tool(workspace)

    return LlmAgent(
        name="remediation_planner",
        model=MODEL,
        instruction=(
            "You are a Maven remediation engineer. Load the maven-remediation "
            "skill, then follow its process:\n"
            "1. Read pom.xml to understand the project structure\n"
            "2. Apply the fix using opencode run\n"
            "3. Verify with mvn -B -q -DskipTests install\n"
            "4. If build fails, report the error for retry\n"
            "5. If build passes, run mvn -B -q verify for full tests\n\n"
            "CVE: {cve_id}, Package: {package}, "
            "Current: {current_version}, Fixed: {fixed_version}\n"
            "Justification: {justification}"
        ),
        tools=[skill_toolset, bash_tool],
        output_key="remediation_output",
    )


def check_build_result(ctx: Context, node_input: str) -> Event:
    """Route based on whether the remediation agent reported success or failure."""
    output = str(node_input).lower() if node_input else ""
    if "error" in output or "fail" in output or "exception" in output:
        ctx.state["retry_count"] = ctx.state.get("retry_count", 0) + 1
        if ctx.state["retry_count"] >= 3:
            return Event(route="MAX_RETRIES", output="Max retries reached.")
        return Event(route="RETRY", output=output)
    return Event(route="SUCCESS", output=output)


def open_remediation_pr(ctx: Context, node_input: str) -> Event:
    """Open a PR with the remediation changes."""
    import time
    cve_id = ctx.state.get("cve_id", "unknown")
    package = ctx.state.get("package", "unknown")
    fixed = ctx.state.get("fixed_version", "unknown")
    justification = ctx.state.get("justification", "")
    repo_url = ctx.state.get("repo_url", "")
    workspace = ctx.state.get("workspace", "")

    result = create_pull_request(
        repo_url=repo_url,
        local_repo_path=workspace,
        branch=f"rhtpa/remediate-{cve_id}-{int(time.time())}",
        base="main",
        title=f"Remediate {cve_id}: {package} -> {fixed}",
        body=(f"Automated remediation.\n- CVE: {cve_id}\n"
              f"- Dependency: {package} -> {fixed}\n"
              f"- Rationale: {justification}"),
        files_to_stage="pom.xml */pom.xml REMEDIATION.md",
    )
    return Event(output=result)


def report_failure(node_input: str) -> Event:
    """Report that remediation failed after max retries."""
    return Event(output={"success": False, "reason": str(node_input)})


def create_remediation_agent() -> Workflow:
    """Factory: builds the Workflow-based remediation agent."""
    plan_agent = _create_plan_agent()

    return Workflow(
        name="remediation",
        description=(
            "Remediates a Maven dependency vulnerability: reads pom.xml, "
            "applies the fix via OpenCode, verifies with Maven, opens a PR."
        ),
        edges=[
            ("START", read_project),
            (read_project, plan_agent),
            (plan_agent, check_build_result),
            (check_build_result, {
                "SUCCESS": open_remediation_pr,
                "RETRY": plan_agent,
                "MAX_RETRIES": report_failure,
            }),
        ],
    )
