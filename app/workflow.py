"""Graph-based remediation pipeline using ADK Workflow.

Replaces the deprecated SequentialAgent/LoopAgent pattern with a first-class
Workflow graph. The LLM coordinator in agent.py remains for playground/
interactive use; this module provides the deterministic pipeline execution
path used by the runner and CI/CD.

Architecture:
    START → cve_selection → route_on_selection
    route_on_selection:
        "selected"     → remediation_planner → route_on_build
        "not_selected" → report_no_selection
    route_on_build:
        "success"  → test_generation → fix_validation → report_complete
        "failure"  → route_on_retry
        "hopeless" → report_hopeless
    route_on_retry:
        "retry" → remediation_planner  (back to build loop)
        "stop"  → report_failure
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.events import Event
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.workflow import START, Workflow

from app.agents.remediation import (
    _remediation_after_callback,
    _remediation_before_callback,
)
from app.config import MODEL, SKILLS_DIR, build_bash_tool
from app.scoring.validate_selection import fail_closed_selection_callback
from app.tools.build_tools import detect_build_system
from app.tools.cve_tools import (
    check_version_exists,
    list_must_fix_cves,
    lookup_cve_detail,
    parse_maven_purl,
)
from app.tools.diff_tools import (
    analyze_diff,
    check_regex_safety,
    score_exploit_source,
)
from app.tools.live_cve_tools import (
    lookup_epss,
    lookup_nvd,
    lookup_osv,
    search_github_advisory,
)
from app.tools.scm_tools import clone_repository_tool
from app.tools.upstream_tools import (
    discover_upstream_repo,
    fetch_commit_diff,
    lookup_known_repo,
    search_fix_commits,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Shared tool sets (reused by multiple agents)
# ============================================================================


def _cve_tools() -> list:
    """Tools for CVE investigation."""
    return [
        list_must_fix_cves,
        lookup_cve_detail,
        parse_maven_purl,
        check_version_exists,
        FunctionTool(lookup_osv),
        FunctionTool(lookup_nvd),
        FunctionTool(lookup_epss),
        FunctionTool(search_github_advisory),
        FunctionTool(discover_upstream_repo),
        FunctionTool(lookup_known_repo),
    ]


def _remediation_tools() -> list:
    """Tools for the remediation planner."""
    bash_tool = build_bash_tool()
    return [
        bash_tool,
        clone_repository_tool,
        FunctionTool(detect_build_system),
        FunctionTool(lookup_osv),
        FunctionTool(lookup_nvd),
        FunctionTool(search_github_advisory),
        FunctionTool(discover_upstream_repo),
        FunctionTool(search_fix_commits),
        FunctionTool(fetch_commit_diff),
        FunctionTool(analyze_diff),
    ]


def _validation_tools() -> list:
    """Tools for validation personas."""
    return [
        lookup_cve_detail,
        parse_maven_purl,
        FunctionTool(analyze_diff),
        FunctionTool(check_regex_safety),
        FunctionTool(lookup_nvd),
        FunctionTool(lookup_osv),
    ]


# ============================================================================
# Agent nodes (LlmAgents in single_turn mode for pipeline use)
# ============================================================================


def _create_selection_agent() -> LlmAgent:
    """CVE selection agent as a Workflow node."""
    skills = [
        load_skill_from_dir(SKILLS_DIR / "cve-triage"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    return LlmAgent(
        name="cve_selection",
        model=MODEL,
        mode="single_turn",
        after_agent_callback=fail_closed_selection_callback,
        instruction=(
            "You are a CVE triage specialist. Select the single best CVE "
            "to remediate from the data provided. Use the available tools "
            "to investigate each CVE. Report your selection as JSON with: "
            "selected (true/false), cve_id, package, current_version, "
            "fixed_version, justification."
        ),
        tools=[SkillToolset(skills=skills), *_cve_tools()],
        output_key="selection_result",
    )


def _create_remediation_agent() -> LlmAgent:
    """Remediation planner as a Workflow node."""
    skill_dirs = [SKILLS_DIR / "maven-remediation", SKILLS_DIR / "scm-conventions"]
    if (SKILLS_DIR / "gradle-remediation").exists():
        skill_dirs.append(SKILLS_DIR / "gradle-remediation")
    skills = [load_skill_from_dir(d) for d in skill_dirs]

    return LlmAgent(
        name="remediation_planner",
        model=MODEL,
        mode="single_turn",
        before_agent_callback=_remediation_before_callback,
        after_agent_callback=_remediation_after_callback,
        instruction=(
            "You are a remediation engineer. Investigate the upstream fix, "
            "clone the repo, apply the version change, build, test, and "
            "commit+push. Report as JSON with: build_status (SUCCESS/FAILURE), "
            "fix_type, upstream_fix_analyzed, files_changed, error_message."
        ),
        tools=[SkillToolset(skills=skills), *_remediation_tools()],
        output_key="remediation_output",
    )


def _create_test_gen_agent() -> LlmAgent:
    """Test generation agent as a Workflow node."""
    skills = [
        load_skill_from_dir(SKILLS_DIR / "junit-test-generation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    return LlmAgent(
        name="test_generation",
        model=MODEL,
        mode="single_turn",
        instruction=(
            "Generate JUnit tests for the applied fix. Write test files "
            "directly via bash (mkdir + tee), verify they pass, commit "
            "and push. Report 'TESTS GENERATED' or 'TEST GENERATION FAILED'."
        ),
        tools=[SkillToolset(skills=skills), build_bash_tool(), clone_repository_tool],
        output_key="test_output",
    )


def _create_architect_agent() -> LlmAgent:
    """Security architect validation persona."""
    skills = [load_skill_from_dir(SKILLS_DIR / "validation-architect")]
    return LlmAgent(
        name="security_architect",
        model=MODEL,
        mode="single_turn",
        instruction=(
            "You are a security architect reviewing a vulnerability fix. "
            "Evaluate against four gates: root_cause, instance_coverage, "
            "no_new_vulnerabilities, security_best_practices. "
            "For each gate report: status (pass/partial/fail), summary, evidence."
        ),
        tools=[SkillToolset(skills=skills), *_validation_tools()],
        output_key="architect_report",
    )


def _create_pentester_agent() -> LlmAgent:
    """Penetration tester validation persona."""
    skills = [load_skill_from_dir(SKILLS_DIR / "validation-pentester")]
    return LlmAgent(
        name="penetration_tester",
        model=MODEL,
        mode="single_turn",
        instruction=(
            "You are a penetration tester reviewing a vulnerability fix. "
            "Try to find bypasses. Evaluate the same four gates. "
            "For each gate report: status (pass/partial/fail), summary, evidence."
        ),
        tools=[
            SkillToolset(skills=skills),
            *_validation_tools(),
            FunctionTool(score_exploit_source),
        ],
        output_key="pentester_report",
    )


# ============================================================================
# Routing functions (deterministic decision nodes)
# ============================================================================


def route_on_selection(node_input: str) -> Event:
    """Route based on whether a CVE was selected."""
    text = str(node_input).lower()
    if '"selected": true' in text or '"selected":true' in text:
        return Event(output=node_input, route="selected")
    if "selected: true" in text:
        return Event(output=node_input, route="selected")
    return Event(output=node_input, route="not_selected")


def route_on_build(node_input: str) -> Event:
    """Route based on build result."""
    text = str(node_input).lower()

    # Hopeless detection
    missing_count = sum(
        text.count(p) for p in ["cannot find symbol", "does not exist", "file not found"]
    )
    if missing_count > 3:
        return Event(output=node_input, route="hopeless")

    if "build success" in text or '"build_status": "success"' in text:
        return Event(output=node_input, route="success")

    return Event(output=node_input, route="failure")


_retry_count = 0
_MAX_RETRIES = 3


def route_on_retry(node_input: str) -> Event:
    """Route based on retry count."""
    global _retry_count
    _retry_count += 1
    if _retry_count >= _MAX_RETRIES:
        return Event(output=node_input, route="stop")
    return Event(output=node_input, route="retry")


def compute_validation_score(node_input: str) -> str:
    """Deterministic scoring from architect + pentester reports.

    Pure computation — no LLM. Reads the gate statuses from both
    persona reports and computes a weighted consensus score.
    """
    import re

    gate_weights = {
        "root_cause": 0.43,
        "instance_coverage": 0.2467,
        "no_new_vulnerabilities": 0.1867,
        "security_best_practices": 0.1366,
    }
    score_map = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "inconclusive": 0.0}
    severity_rank = {"fail": 0, "partial": 1, "inconclusive": 2, "pass": 3}

    text = str(node_input)
    gates = {}
    for gate_name in gate_weights:
        pattern = re.compile(
            rf"\*{{0,2}}{re.escape(gate_name)}\*{{0,2}}\s*:\s*(pass|partial|fail)",
            re.IGNORECASE,
        )
        matches = pattern.findall(text)
        statuses = [m.lower() for m in matches] if matches else ["inconclusive"]
        most_conservative = min(statuses, key=lambda s: severity_rank.get(s, 2))
        gates[gate_name] = most_conservative

    total = sum(gate_weights[g] * score_map.get(gates[g], 0.0) for g in gate_weights)
    if total >= 0.80:
        decision = "FIXED"
    elif total >= 0.50:
        decision = "PARTIALLY_FIXED"
    else:
        decision = "NOT_FIXED"

    if gates.get("root_cause") != "pass" and decision == "FIXED":
        decision = "PARTIALLY_FIXED"

    return f'{{"decision": "{decision}", "score": {total:.3f}, "gates": {gates}}}'


def report_no_selection(node_input: str) -> str:
    """Terminal node when no CVE is selected."""
    return '{"status": "no_selection", "message": "No CVE met selection criteria"}'


def report_hopeless(node_input: str) -> str:
    """Terminal node for hopeless build failures."""
    return '{"status": "hopeless", "message": "Build failure is not recoverable"}'


def report_failure(node_input: str) -> str:
    """Terminal node after exhausting retries."""
    return '{"status": "failed", "message": "Remediation failed after max retries"}'


def report_complete(node_input: str) -> str:
    """Terminal node for successful pipeline completion."""
    return f'{{"status": "complete", "validation": {node_input}}}'


# ============================================================================
# Workflow construction
# ============================================================================


def create_pipeline_workflow() -> Workflow:
    """Build the full CVE remediation pipeline as a Workflow graph.

    This is the production execution path. The LLM coordinator in agent.py
    remains available for playground/interactive use.
    """
    global _retry_count
    _retry_count = 0

    selection = _create_selection_agent()
    remediation = _create_remediation_agent()
    test_gen = _create_test_gen_agent()
    architect = _create_architect_agent()
    pentester = _create_pentester_agent()

    return Workflow(
        name="cve_remediation_pipeline",
        edges=[
            # Phase 1: Select CVE
            (START, selection, route_on_selection),
            # Phase 2: Route on selection result
            (
                route_on_selection,
                {
                    "selected": remediation,
                    "not_selected": report_no_selection,
                },
            ),
            # Phase 3: Route on build result
            (remediation, route_on_build),
            (
                route_on_build,
                {
                    "success": test_gen,
                    "failure": route_on_retry,
                    "hopeless": report_hopeless,
                },
            ),
            # Phase 3b: Retry loop
            (
                route_on_retry,
                {
                    "retry": remediation,
                    "stop": report_failure,
                },
            ),
            # Phase 4: Test generation → Validation
            (test_gen, architect, pentester, compute_validation_score, report_complete),
        ],
    )


# ============================================================================
# Convenience: create App with Workflow as root
# ============================================================================


def create_workflow_app():
    """Create an ADK App with the Workflow as root agent.

    Includes the same safety + redaction plugins as the coordinator
    App in agent.py. These guard ALL nodes in the workflow:
    - SafetyPlugin: LLM-as-judge content safety on input/output
    - RedactionPlugin: Secret masking on tool results

    Use this for pipeline/CI execution. For interactive/playground,
    use the coordinator-based App in agent.py.
    """
    from google.adk.apps import App

    from app.plugins.redaction import RedactionPlugin
    from app.plugins.safety import SafetyPlugin

    return App(
        name="lw-agents-pipeline",
        root_agent=create_pipeline_workflow(),
        plugins=[SafetyPlugin(), RedactionPlugin()],
    )
