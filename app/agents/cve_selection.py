"""CVE Selection Agent — LlmAgent that loads the cve-triage skill on demand,
explores must-fix CVEs one-by-one via tools, and selects the best one.

Uses SkillToolset (ADK native) for skill loading and output_key for results
(NOT output_schema, which disables tool calling).
"""

from __future__ import annotations

import os
import pathlib

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.scoring.validate_selection import fail_closed_selection_callback
from app.tools.cve_tools import (
    check_version_exists,
    list_must_fix_cves,
    lookup_cve_detail,
    parse_maven_purl,
)

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "skills"


def create_cve_selection_agent() -> LlmAgent:
    """Factory function — avoids 'agent already has a parent' errors."""
    skills = [
        load_skill_from_dir(SKILLS_DIR / "cve-triage"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)

    return LlmAgent(
        name="cve_selection",
        model=MODEL,
        after_agent_callback=fail_closed_selection_callback,
        instruction=(
            "You are a CVE triage specialist. When asked to select a CVE, "
            "first call load_skill to read the cve-triage skill, then follow "
            "its process step by step using the available tools. Report your "
            "selection as a structured summary with: selected (true/false), "
            "cve_id, package (groupId:artifactId), current_version, "
            "fixed_version, and justification."
        ),
        description=(
            "Selects the single best CVE to remediate from a policy-gated "
            "must-fix set by exploring each CVE incrementally via tools."
        ),
        tools=[
            skill_toolset,
            list_must_fix_cves,
            lookup_cve_detail,
            parse_maven_purl,
            check_version_exists,
        ],
        output_key="selection_result",
    )
