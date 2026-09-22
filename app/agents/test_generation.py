"""Test Generation Agent — CVE-aware test generation with reproducer adaptation.

Three-tier strategy:
1. UPSTREAM REPRODUCER: Find the test from the upstream fix commit, adapt it
2. CVE-TARGETED: Write a test targeting the specific vulnerability pattern
3. GENERIC COVERAGE: Fall back to standard JUnit coverage tests

The agent uses upstream tools (fetch_commit_diff, search_github_advisory)
to find existing reproducer tests before writing from scratch.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

from app.config import MODEL, SKILLS_DIR, build_bash_tool
from app.tools.live_cve_tools import lookup_nvd, lookup_osv, search_github_advisory
from app.tools.scm_tools import clone_repository_tool
from app.tools.upstream_tools import (
    discover_upstream_repo,
    fetch_commit_diff,
    search_fix_commits,
)


async def _test_gen_after_callback(callback_context) -> None:
    """Set TESTS_ADDED in structured_result after test-gen completes."""
    state = callback_context.state
    test_output = str(state.get("test_output", "")).lower()

    if any(
        kw in test_output
        for kw in (
            "tests generated",
            "test generation",
            "reproducer adapted",
            "reproducer test",
            "git push",
            "pushed",
            "commit",
            "file changed",
            "build success",
            "tee src/test",
        )
    ):
        state["structured_result"] = {
            "SELECTED": "0",
            "CVE_ID": "",
            "PACKAGE": "",
            "CURRENT_VERSION": "",
            "FIXED_VERSION": "",
            "JUSTIFICATION": "Tests generated and pushed.",
            "PR_URL": "",
            "COUNT": "0",
            "TESTS_ADDED": "1",
            "ISSUES_CREATED": "0",
            "CHANGED": "0",
        }


def create_test_generation_agent() -> LlmAgent:
    """Factory: CVE-aware test generation agent."""
    skills = [
        load_skill_from_dir(SKILLS_DIR / "junit-test-generation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)
    bash_tool = build_bash_tool()

    return LlmAgent(
        name="test_generation",
        model=MODEL,
        after_agent_callback=_test_gen_after_callback,
        instruction=(
            "You are a CVE-aware test engineer. Your goal is to generate "
            "tests that PROVE the vulnerability fix works. You have three "
            "strategies, tried in order.\n\n"
            "STEP 1 — CLONE: Call clone_repository with the repo URL "
            "and branch from the user's message.\n\n"
            "STEP 2 — FIND UPSTREAM REPRODUCER: Before writing any test, "
            "check if the upstream fix already includes a test:\n"
            "  a) Call search_github_advisory(cve_id) to find fix commits\n"
            "  b) Call fetch_commit_diff(commit_url) to get the diff\n"
            "  c) Look for test files in the diff (files under src/test/ "
            "or files ending in Test.java/Tests.java)\n"
            "  d) If a reproducer test exists in the diff, extract it — "
            "this is STRATEGY 1 (best)\n\n"
            "STEP 3 — ADAPT OR WRITE THE TEST:\n\n"
            "**Strategy 1 — Upstream reproducer found:**\n"
            "  Take the test file from the upstream diff and adapt it:\n"
            "  - Fix imports for the target version's API\n"
            "  - Adjust class/method names if they changed\n"
            "  - Keep the assertion logic that exercises the vulnerable "
            "code path\n"
            "  - The test should FAIL on the vulnerable version and PASS "
            "on the fixed version\n"
            "  Write it using mkdir + tee to the correct path.\n\n"
            "**Strategy 2 — No reproducer, but diff available:**\n"
            "  Call lookup_nvd(cve_id) to get the CWE classification.\n"
            "  Write a targeted test based on the vulnerability pattern:\n"
            "  - CWE-79 (XSS): test that special chars are escaped\n"
            "  - CWE-89 (SQL Injection): test parameterized queries\n"
            "  - CWE-502 (Deserialization): test restricted types\n"
            "  - CWE-22 (Path Traversal): test path normalization\n"
            "  - CWE-400 (DoS): test input size limits\n"
            "  Name the test class: Cve{YYYY}{NNNN}ReproducerTest.java\n\n"
            "**Strategy 3 — No CVE context available:**\n"
            "  Fall back to standard JUnit coverage: analyze the project, "
            "find classes without tests, generate unit tests.\n\n"
            "STEP 4 — WRITE TEST FILES using bash (mkdir + tee):\n"
            "  cd /tmp/workspace && mkdir -p src/test/java/com/example\n"
            "  cd /tmp/workspace && tee src/test/java/com/example/"
            "Cve2024XxxxxReproducerTest.java << 'ENDTEST'\n"
            "  ... test code ...\n"
            "  ENDTEST\n\n"
            "STEP 5 — VERIFY:\n"
            "  Maven: cd /tmp/workspace && mvn -B -q test\n"
            "  Gradle: cd /tmp/workspace && ./gradlew test\n"
            "  If tests fail, fix and retry up to 2 times.\n\n"
            "STEP 6 — COMMIT AND PUSH:\n"
            "  cd /tmp/workspace && git add src/test/\n"
            "  cd /tmp/workspace && git commit -m "
            "'Add CVE reproducer test for <CVE-ID>'\n"
            "  cd /tmp/workspace && git push origin "
            "HEAD:ai-tests/generated\n\n"
            "STEP 7 — REPORT as JSON:\n"
            '  {"tests_generated": true, '
            '"strategy": "upstream_reproducer|cve_targeted|generic", '
            '"test_files": ["path/to/Test.java"], '
            '"cve_id": "CVE-..."}\n\n'
            "IMPORTANT: Always use 'cd /tmp/workspace && ' prefix. "
            "Write files directly with tee, not opencode. "
            "Prefer Strategy 1 > 2 > 3."
        ),
        description=(
            "Generates CVE-aware tests: finds upstream reproducers, "
            "adapts them, or writes targeted vulnerability tests."
        ),
        tools=[
            skill_toolset,
            bash_tool,
            clone_repository_tool,
            # Upstream investigation tools
            FunctionTool(search_github_advisory),
            FunctionTool(fetch_commit_diff),
            FunctionTool(discover_upstream_repo),
            FunctionTool(search_fix_commits),
            FunctionTool(lookup_nvd),
            FunctionTool(lookup_osv),
        ],
        output_key="test_output",
    )
