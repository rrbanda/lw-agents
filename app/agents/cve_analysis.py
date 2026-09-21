"""CVE Analysis Agent — LlmAgent that loads the cve-analysis skill, iterates
every must-fix CVE via tools, and returns a decisions array for Tekton.

Now equipped with live CVE data tools for enriched analysis.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

from app.config import MODEL, SKILLS_DIR
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
    lookup_vex,
    search_github_advisory,
)
from app.tools.upstream_tools import (
    discover_upstream_repo,
    search_fix_commits,
)


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
            "its process step by step.\n\n"
            "IMPORTANT: If workspace files are not found when you call "
            "list_must_fix_cves or lookup_cve_detail, use the CVE data "
            "provided directly in the user's message instead.\n\n"
            "You have access to LIVE CVE data sources for enriched analysis:\n"
            "- lookup_osv: Affected versions and fix versions from OSV.dev/GHSA\n"
            "- lookup_nvd: CVSS scores, CWE classification, patch URLs from NVD\n"
            "- lookup_epss: Exploit probability score\n"
            "- lookup_vex: Red Hat VEX advisory data\n"
            "- search_github_advisory: Fix commit URLs and patched versions\n"
            "- discover_upstream_repo: Find upstream GitHub repo for a component\n"
            "- search_fix_commits: Search for commits that fix a CVE\n\n"
            "For EACH fixable CVE, verify the fixed version exists using "
            "check_version_exists. Use live data sources to find fix versions "
            "when the local report doesn't have them.\n\n"
            "Output your complete analysis as a JSON array of decisions:\n"
            '[{"cve_id":"CVE-...","package":"groupId:artifactId",'
            '"current_version":"...","fixed_version":"...",'
            '"severity":"...","justification":"...","selected":true}, ...]\n\n'
            "Include ONLY CVEs where you verified a concrete fixed version exists. "
            "Report the total count of fixable CVEs found."
        ),
        description=(
            "Analyzes every CVE in the must-fix set, evaluates fixability "
            "via tools, and returns a JSON decisions array."
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
            FunctionTool(lookup_vex),
            FunctionTool(search_github_advisory),
            FunctionTool(discover_upstream_repo),
            FunctionTool(search_fix_commits),
        ],
        output_key="analysis_result",
    )
