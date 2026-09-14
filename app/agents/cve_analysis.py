"""CVE Analysis Agent — LlmAgent that loads the cve-analysis skill, iterates
every must-fix CVE via tools, and creates SCM issues for fixable ones."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.config import MODEL, SKILLS_DIR
from app.tools.cve_tools import (
    check_version_exists,
    list_must_fix_cves,
    lookup_cve_detail,
    parse_maven_purl,
)
from app.tools.scm_tools import create_scm_issue_tool


def create_cve_analysis_agent() -> LlmAgent:
    """Factory function — avoids 'agent already has a parent' errors."""
    skills = [
        load_skill_from_dir(SKILLS_DIR / "cve-analysis"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)

    return LlmAgent(
        name="cve_analysis",
        model=MODEL,
        instruction=(
            "You are a CVE analysis specialist. When asked to analyze CVEs, "
            "first call load_skill to read the cve-analysis skill, then follow "
            "its process step by step. Analyze every CVE in the must-fix set "
            "individually using tools. For each fixable CVE, create an issue "
            "using the create_scm_issue tool. Report the total count of fixable "
            "CVEs and issues created."
        ),
        description=(
            "Analyzes every CVE in the must-fix set, evaluates fixability "
            "via tools, and creates one SCM issue per fixable vulnerability."
        ),
        tools=[
            skill_toolset,
            list_must_fix_cves,
            lookup_cve_detail,
            parse_maven_purl,
            check_version_exists,
            create_scm_issue_tool,
        ],
        output_key="analysis_result",
    )
