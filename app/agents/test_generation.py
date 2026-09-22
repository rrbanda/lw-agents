"""Test Generation Agent — CVE-aware test generation.

Clean responsibility split:
- Parent agent: Investigates the CVE, decides strategy, delegates coding
- OpenCode sub-agent (when available): Writes/adapts test files
- Fallback: Parent writes files directly via tee when no OpenCode

Three-tier strategy:
1. UPSTREAM REPRODUCER: Find test from upstream fix commit, adapt it
2. CVE-TARGETED: Write test based on CWE vulnerability pattern
3. GENERIC COVERAGE: Standard JUnit coverage tests
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

from app.agents.opencode_writer import create_opencode_writer, is_opencode_available
from app.config import MODEL, SKILLS_DIR, build_bash_tool
from app.tools.live_cve_tools import lookup_nvd, lookup_osv, search_github_advisory
from app.tools.scm_tools import clone_repository_tool
from app.tools.upstream_tools import (
    discover_upstream_repo,
    fetch_commit_diff,
    search_fix_commits,
)


async def _test_gen_after_callback(callback_context) -> None:
    """Set TESTS_ADDED in structured_result after test-gen completes.

    IMPORTANT: ADK's output_key only captures text authored by the agent
    itself (event.author == agent.name). When the parent delegates to
    test_code_writer sub-agent, the sub-agent's output goes to its own
    output_key (coding_output), NOT to the parent's (test_output).

    We must check BOTH output keys to detect success.
    """
    state = callback_context.state

    # Merge parent output + sub-agent output
    all_output = " ".join(
        str(state.get(key, "")) for key in ("test_output", "coding_output")
    ).lower()

    if any(
        kw in all_output
        for kw in (
            "tests generated",
            "tests_generated",
            "test generation",
            "reproducer adapted",
            "reproducer test",
            "create the test file",
            "created the test",
            "wrote the test",
            "test file",
            "reproducertest",
            "git push",
            "pushed",
            "commit",
            "file changed",
            "build success",
            "tee src/test",
            "opencode",
            "strategy",
            "test_files",
            "wrote",
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


# -- Instruction blocks (no duplication) --

_INVESTIGATION_STEPS = (
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
    "STEP 3 — DECIDE STRATEGY:\n"
    "**Strategy 1 — Upstream reproducer found:**\n"
    "  Adapt the test: fix imports, adjust names, preserve "
    "the assertion logic that exercises the vulnerable code path.\n\n"
    "**Strategy 2 — No reproducer, but diff available:**\n"
    "  Call lookup_nvd(cve_id) to get the CWE classification.\n"
    "  Write a targeted test based on the vulnerability pattern.\n"
    "  Name: CveYYYYNNNNNReproducerTest.java "
    "(e.g. Cve202429025ReproducerTest.java)\n\n"
    "**Strategy 3 — No CVE context available:**\n"
    "  Standard JUnit coverage tests as last resort.\n\n"
)

_CODING_WITH_OPENCODE = (
    "STEP 4 — WRITE TESTS: Delegate to the test_code_writer "
    "sub-agent. Describe EXACTLY what to write:\n"
    "  - File path (e.g. src/test/java/com/example/...Test.java)\n"
    "  - What to test (the vulnerable code path)\n"
    "  - The assertion logic (what should pass/fail)\n"
    "  - If adapting upstream test, include the source code to adapt\n"
    "Do NOT write files yourself — let test_code_writer handle it.\n\n"
)

_CODING_WITHOUT_OPENCODE = (
    "STEP 4 — WRITE TESTS using bash (mkdir + tee):\n"
    "  cd /tmp/workspace && mkdir -p src/test/java/com/example\n"
    "  cd /tmp/workspace && tee src/test/java/com/example/"
    "Cve2024XxxxxReproducerTest.java << 'ENDTEST'\n"
    "  ... test code ...\n"
    "  ENDTEST\n\n"
)

_VERIFY_AND_PUSH = (
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
    '"cve_id": "CVE-..."}\n'
)


def create_test_generation_agent() -> LlmAgent:
    """Factory: CVE-aware test generation agent.

    Responsibility split:
    - This agent: CVE investigation + strategy selection + verify + push
    - OpenCode sub-agent (when available): file writing/editing
    - Fallback: this agent writes files via tee when no OpenCode
    """
    skills = [
        load_skill_from_dir(SKILLS_DIR / "junit-test-generation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)
    bash_tool = build_bash_tool()

    sub_agents = []
    opencode_available = is_opencode_available()
    if opencode_available:
        sub_agents.append(create_opencode_writer("test_code_writer"))

    coding_step = _CODING_WITH_OPENCODE if opencode_available else _CODING_WITHOUT_OPENCODE

    instruction = (
        "You are a CVE-aware test engineer. Your goal is to generate "
        "tests that PROVE the vulnerability fix works.\n\n"
        + _INVESTIGATION_STEPS
        + coding_step
        + _VERIFY_AND_PUSH
    )

    return LlmAgent(
        name="test_generation",
        model=MODEL,
        after_agent_callback=_test_gen_after_callback,
        sub_agents=sub_agents,
        instruction=instruction,
        description=(
            "Generates CVE-aware tests: finds upstream reproducers, "
            "adapts them, or writes targeted vulnerability tests."
        ),
        tools=[
            skill_toolset,
            bash_tool,
            clone_repository_tool,
            FunctionTool(search_github_advisory),
            FunctionTool(fetch_commit_diff),
            FunctionTool(discover_upstream_repo),
            FunctionTool(search_fix_commits),
            FunctionTool(lookup_nvd),
            FunctionTool(lookup_osv),
        ],
        output_key="test_output",
    )
