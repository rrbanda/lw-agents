"""CVE Selection Agent — LlmAgent that loads the cve-triage skill on demand,
explores must-fix CVEs one-by-one via tools, and selects the best one.

Now equipped with live CVE data tools (OSV, NVD, EPSS, GitHub Advisory)
and upstream discovery tools alongside the original local file tools.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

from app.config import MODEL, SKILLS_DIR
from app.scoring.validate_selection import fail_closed_selection_callback
from app.tools.cve_tools import (
    check_version_exists,
    list_must_fix_cves,
    lookup_cve_detail,
    parse_maven_purl,
)
from app.tools.live_cve_tools import (
    lookup_epss,
    lookup_nvd,
    lookup_osv,
    search_github_advisory,
)
from app.tools.upstream_tools import (
    discover_upstream_repo,
    lookup_known_repo,
)


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
            "its process step by step using the available tools.\n\n"
            "IMPORTANT: If the workspace files are not found when you call "
            "list_must_fix_cves or lookup_cve_detail (tool returns 'not_found' "
            "or 'error'), use the CVE data provided directly in the user's "
            "message instead. The Tekton pipeline embeds file contents in the "
            "prompt when the agent runs as a remote service.\n\n"
            "You have access to LIVE CVE data sources beyond the local report:\n"
            "- lookup_osv: Get affected versions and fix versions from OSV.dev/GHSA\n"
            "- lookup_nvd: Get CVSS scores, CWE classification, and patch URLs from NVD\n"
            "- lookup_epss: Get exploit probability score (EPSS) — "
            "best predictor of real-world exploitation\n"
            "- search_github_advisory: Find fix commit URLs and patched versions\n"
            "- discover_upstream_repo: Find the GitHub repo for any component\n\n"
            "Use these to enrich your analysis beyond the local RHTPA report. "
            "EPSS score is especially valuable for prioritization — a CVE with "
            "high EPSS (>0.5) should be prioritized over one with higher CVSS but low EPSS.\n\n"
            "Report your selection as a structured summary with: selected (true/false), "
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
            # Live CVE data tools
            FunctionTool(lookup_osv),
            FunctionTool(lookup_nvd),
            FunctionTool(lookup_epss),
            FunctionTool(search_github_advisory),
            FunctionTool(discover_upstream_repo),
            FunctionTool(lookup_known_repo),
        ],
        output_key="selection_result",
    )
