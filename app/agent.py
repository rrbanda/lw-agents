"""Root agent + App definition — the entry point ADK expects.

ADK's built-in server (adk api_server) and the scaffolded fast_api_app.py
look for root_agent and app in app/agent.py. This module wires the five
specialist agents under a coordinator, with safety + redaction plugins
at the Runner level.

Architecture follows patterns from:
- adk-samples: Coordinator with sub_agents, Safety BasePlugin, ResumabilityConfig
- VVAH: Policy gates, fail-closed scoring, output redaction, multi-persona validation
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.agents.cve_analysis import create_cve_analysis_agent
from app.agents.cve_selection import create_cve_selection_agent
from app.agents.remediation import create_remediation_agent
from app.agents.test_generation import create_test_generation_agent
from app.agents.validation import create_validation_agent
from app.callbacks import extract_structured_results, init_structured_result
from app.config import MODEL, SKILLS_DIR
from app.plugins.redaction import RedactionPlugin
from app.plugins.safety import SafetyPlugin


def _create_cve_test_investigator():
    """Create a standalone CVE test investigator agent.

    This is the investigation-only step from the test_generation pipeline,
    exposed as a top-level coordinator sub-agent. It researches the CVE,
    checks existing test coverage, and produces a TEST SPECIFICATION —
    but does NOT write code. Used by the lw-investigate-cve Tekton task
    when OpenCode handles code writing separately.
    """
    from app.agents.test_generation import _create_investigator

    # Create a fresh investigator with a distinct name for the coordinator
    base = _create_investigator()
    return LlmAgent(
        name="cve_test_investigator",
        model=base.model,
        instruction=base.instruction,
        description=(
            "Investigates a CVE and produces a test specification (what to test, "
            "CWE, vulnerable class, attack vector, assertion). Does NOT write code."
        ),
        tools=list(base.tools),
        output_key="test_spec",
    )


def _build_app() -> App:
    # Domain knowledge skill — lets the coordinator answer conceptual
    # questions about CVE lifecycle, Lightwell, CVSS vs EPSS, etc.
    domain_skill_dir = SKILLS_DIR / "domain-knowledge"
    domain_skills = [load_skill_from_dir(domain_skill_dir)] if domain_skill_dir.exists() else []
    domain_toolset = SkillToolset(skills=domain_skills) if domain_skills else None

    coordinator_tools = [domain_toolset] if domain_toolset else []

    root_agent = LlmAgent(
        name="ssc_coordinator",
        model=MODEL,
        instruction=(
            "You are the Software Supply Chain security agent coordinator. "
            "Based on the user's request, delegate to the appropriate specialist:\n\n"
            "- For CVE **selection** (pick ONE CVE to fix): delegate to cve_selection\n"
            "- For CVE **analysis** (analyze ALL CVEs, open issues): delegate to cve_analysis\n"
            "- For dependency **remediation** (apply a fix, open PR): delegate to remediation\n"
            "- For **test investigation** (research CVE, produce test SPECIFICATION only, "
            "do NOT write code): delegate to cve_test_investigator\n"
            "- For **test generation** (generate JUnit tests, write code, open PR): "
            "delegate to test_generation\n"
            "- For fix **validation** (adversarial review of a fix): delegate to fix_validation\n\n"
            "For **domain questions** about CVE lifecycle, Lightwell, CVSS vs EPSS, "
            "severity vs priority, CWE classifications, or how the agents work: "
            "call load_skill to read the domain-knowledge skill, then answer "
            "using the skill's content. Do NOT delegate domain questions to specialists.\n\n"
            "For task requests, always delegate — never attempt the task yourself. "
            "Pass the full request context (workspace path, CVE details, etc.) to the specialist."
        ),
        description="Routes software supply chain security tasks to specialist agents.",
        before_agent_callback=init_structured_result,
        after_agent_callback=extract_structured_results,
        tools=coordinator_tools,
        sub_agents=[
            create_cve_selection_agent(),
            create_cve_analysis_agent(),
            create_remediation_agent(),
            _create_cve_test_investigator(),
            create_test_generation_agent(),
            create_validation_agent(),
        ],
    )

    return App(
        name="app",
        root_agent=root_agent,
        plugins=[SafetyPlugin(), RedactionPlugin()],
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


app = _build_app()
root_agent = app.root_agent
