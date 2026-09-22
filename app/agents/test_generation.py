"""Test Generation Agent — CVE-aware test generation.

Two-mode architecture:
  WITH OpenCode (pipeline mode):
    Agent investigates CVE → builds TEST SPECIFICATION → OpenCode generates code
    Agent verifies build → if fails → OpenCode fixes errors
  WITHOUT OpenCode (web UI mode):
    Agent investigates CVE → writes test code directly via tee
    Agent verifies build → fixes manually (up to 2 retries)

The key insight: we pass WHAT to test (specification) to OpenCode,
not HOW to test it (code). This avoids the LLM telephone game.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

from app.agents.opencode_writer import (
    create_opencode_fixer,
    create_opencode_test_generator,
    is_opencode_available,
)
from app.config import MODEL, SKILLS_DIR, build_bash_tool
from app.tools.live_cve_tools import lookup_nvd, lookup_osv, search_github_advisory
from app.tools.scm_tools import clone_repository_tool
from app.tools.upstream_tools import (
    discover_upstream_repo,
    fetch_commit_diff,
    search_fix_commits,
)


async def _test_gen_after_callback(callback_context) -> None:
    """Set TESTS_ADDED after test-gen completes.

    Reads parent output + both sub-agent outputs (coding_output
    from opencode_test_gen, fix_output from opencode_fixer).
    Copies into test_output for coordinator visibility.
    """
    import logging

    logger = logging.getLogger(__name__)
    state = callback_context.state
    logger.warning("_test_gen_after_callback FIRED")

    # Merge all output sources
    coding_output = str(state.get("coding_output", ""))
    fix_output = str(state.get("fix_output", ""))
    test_output = str(state.get("test_output", ""))

    # Propagate sub-agent output to parent's output_key
    combined_sub = " ".join(filter(None, [coding_output, fix_output]))
    if combined_sub and not test_output:
        state["test_output"] = combined_sub
    elif combined_sub:
        state["test_output"] = test_output + "\n" + combined_sub

    all_output = " ".join([test_output, coding_output, fix_output]).lower()

    logger.warning(
        "_test_gen_after_callback: test_output=%d chars, coding_output=%d chars, "
        "fix_output=%d chars, all_output=%d chars",
        len(test_output),
        len(coding_output),
        len(fix_output),
        len(all_output),
    )

    if any(
        kw in all_output
        for kw in (
            "tests generated",
            "test generation",
            "reproducer",
            "test file",
            "git push",
            "pushed",
            "commit",
            "build success",
            "tee src/test",
            "opencode",
            "wrote",
            "fixed",
            "created",
        )
    ):
        state["structured_result"] = {
            "SELECTED": "0",
            "CVE_ID": "",
            "PACKAGE": "",
            "CURRENT_VERSION": "",
            "FIXED_VERSION": "",
            "JUSTIFICATION": "Tests generated.",
            "PR_URL": "",
            "COUNT": "0",
            "TESTS_ADDED": "1",
            "ISSUES_CREATED": "0",
            "CHANGED": "0",
        }
        logger.warning("_test_gen_after_callback: SET TESTS_ADDED=1")
    else:
        logger.warning(
            "_test_gen_after_callback: NO keyword match. First 200 chars: %s",
            all_output[:200],
        )


# -- Investigation steps (same for both modes) --

_INVESTIGATION = (
    "STEP 1 — CLONE: Call clone_repository with the repo URL "
    "and branch.\n\n"
    "STEP 2 — INVESTIGATE THE CVE:\n"
    "  a) Call search_github_advisory(cve_id) → find fix commits\n"
    "  b) Call fetch_commit_diff(commit_url) → see the actual fix\n"
    "  c) Call lookup_nvd(cve_id) → get CWE classification\n"
    "  d) Look for test files in the upstream diff\n\n"
    "STEP 3 — BUILD A TEST SPECIFICATION:\n"
    "Based on your investigation, determine:\n"
    "  - What class/method is vulnerable\n"
    "  - What the attack input looks like\n"
    "  - What the fix changes\n"
    "  - What assertion proves the fix works\n"
    "  - Where the test file should go (package path)\n"
    "  - Test class name: CveYYYYNNNNNReproducerTest\n\n"
)

# -- OpenCode mode: pass specification, OpenCode generates code --

_OPENCODE_GENERATE = (
    "STEP 4 — DELEGATE TO OPENCODE:\n"
    "Pass the TEST SPECIFICATION (not code!) to the "
    "opencode_test_gen sub-agent. Describe:\n"
    "  - The CVE ID and what it affects\n"
    "  - The vulnerable class/method and what's wrong\n"
    "  - The CWE pattern (e.g. CWE-400 resource exhaustion)\n"
    "  - What the test should assert\n"
    "  - The file path for the test\n\n"
    "Example: 'Create a JUnit 5 test at "
    "src/test/java/.../Cve202429025ReproducerTest.java "
    "for CVE-2024-29025 in netty HttpObjectDecoder. "
    "The vulnerability is CWE-400: oversized HTTP headers "
    "cause resource exhaustion. Test that headers exceeding "
    "8192 bytes are rejected by the decoder.'\n\n"
    "OpenCode will read the project, find the right imports, "
    "and write a compilable test.\n\n"
    "STEP 5 — VERIFY:\n"
    "  cd /tmp/workspace && mvn -B -q test\n"
    "  If fails, delegate to opencode_fixer with the error.\n\n"
)

# -- Tee mode: agent writes code directly --

_TEE_GENERATE = (
    "STEP 4 — WRITE TESTS using bash (mkdir + tee):\n"
    "Write the test code yourself based on your investigation:\n"
    "  cd /tmp/workspace && mkdir -p src/test/java/com/example\n"
    "  cd /tmp/workspace && tee src/test/java/com/example/"
    "Cve2024XxxxxReproducerTest.java << 'ENDTEST'\n"
    "  package com.example;\n"
    "  import org.junit.jupiter.api.Test;\n"
    "  import static org.junit.jupiter.api.Assertions.*;\n"
    "  public class Cve2024XxxxxReproducerTest {\n"
    "    @Test void testCveIsFixed() { /* test logic */ }\n"
    "  }\n"
    "  ENDTEST\n\n"
    "STEP 5 — VERIFY:\n"
    "  cd /tmp/workspace && mvn -B -q test\n"
    "  If fails, fix and retry up to 2 times.\n\n"
)

# -- Commit (same for both modes) --

_COMMIT = (
    "STEP 6 — COMMIT AND PUSH:\n"
    "  cd /tmp/workspace && git add src/test/\n"
    "  cd /tmp/workspace && git commit -m "
    "'Add CVE reproducer test'\n"
    "  cd /tmp/workspace && git push origin "
    "HEAD:ai-tests/generated\n\n"
    "STEP 7 — REPORT as JSON:\n"
    '  {"tests_generated": true, '
    '"strategy": "upstream_reproducer|cve_targeted|generic", '
    '"cve_id": "CVE-..."}\n'
)


def create_test_generation_agent() -> LlmAgent:
    """Factory: CVE-aware test generation agent.

    Two modes:
    - WITH OpenCode: agent investigates → passes spec → OpenCode codes
    - WITHOUT OpenCode: agent investigates → writes code via tee
    """
    skills = [
        load_skill_from_dir(SKILLS_DIR / "junit-test-generation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)
    bash_tool = build_bash_tool()

    sub_agents = []
    oc = is_opencode_available()
    if oc:
        sub_agents.append(create_opencode_test_generator("opencode_test_gen"))
        sub_agents.append(create_opencode_fixer("opencode_fixer"))

    generate_step = _OPENCODE_GENERATE if oc else _TEE_GENERATE

    instruction = (
        "You are a CVE-aware test engineer. Generate tests that "
        "PROVE the vulnerability fix works.\n\n" + _INVESTIGATION + generate_step + _COMMIT
    )

    return LlmAgent(
        name="test_generation",
        model=MODEL,
        after_agent_callback=_test_gen_after_callback,
        sub_agents=sub_agents,
        instruction=instruction,
        description=(
            "Investigates CVEs and generates reproducer tests. "
            + ("Delegates coding to OpenCode." if oc else "Writes tests via tee.")
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
