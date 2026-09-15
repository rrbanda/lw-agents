"""Test Generation Agent — single LlmAgent that clones, generates tests,
verifies, and pushes.

The agent writes test files directly via bash (mkdir + tee) rather than
calling OpenCode, because OpenCode's long execution time causes AFC timeouts.
The LLM generates the test code in its own reasoning and writes it directly.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.config import MODEL, SKILLS_DIR, build_bash_tool
from app.tools.scm_tools import clone_repository_tool


async def _test_gen_after_callback(callback_context) -> None:
    """Set TESTS_ADDED in structured_result after test-gen completes."""
    state = callback_context.state
    test_output = str(state.get("test_output", "")).lower()

    if any(
        kw in test_output
        for kw in (
            "tests generated",
            "test generation",
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
    """Factory: single agent that generates tests end-to-end."""
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
            "You are a test engineer. You MUST execute these steps in order "
            "using your tools. Do NOT just describe what you would do — "
            "actually call the tools.\n\n"
            "STEP 1 — CLONE: Call clone_repository with the repository "
            "URL and branch from the user's message.\n\n"
            "STEP 2 — SKILL: Call load_skill to load the "
            "junit-test-generation skill.\n\n"
            "STEP 3 — ANALYZE: Use execute_bash to examine the project:\n"
            "  cd /tmp/workspace && find src/main -name '*.java' | head -20\n"
            "  cd /tmp/workspace && cat src/main/java/.../SomeService.java\n"
            "Read 2-3 key service/controller classes to understand the code.\n\n"
            "STEP 4 — WRITE TESTS: Write test files DIRECTLY using bash.\n"
            "Do NOT use opencode. Generate the JUnit 5 test code yourself "
            "and write it using mkdir + tee:\n"
            "  cd /tmp/workspace && mkdir -p src/test/java/com/example\n"
            "  cd /tmp/workspace && tee src/test/java/com/example/"
            "MyServiceTest.java << 'ENDTEST'\n"
            "  package com.example;\n"
            "  import org.junit.jupiter.api.Test;\n"
            "  import static org.junit.jupiter.api.Assertions.*;\n"
            "  public class MyServiceTest {\n"
            "    @Test void testSomething() { ... }\n"
            "  }\n"
            "  ENDTEST\n\n"
            "STEP 5 — VERIFY: Run "
            "'cd /tmp/workspace && mvn -B -q test'.\n"
            "If tests fail, fix the code and retry up to 2 times.\n\n"
            "STEP 6 — COMMIT AND PUSH:\n"
            "  cd /tmp/workspace && git add src/test/\n"
            "  cd /tmp/workspace && git commit -m "
            "'Add AI-generated unit tests'\n"
            "  cd /tmp/workspace && git push origin "
            "HEAD:ai-tests/generated\n\n"
            "STEP 7 — REPORT: Say 'TESTS GENERATED' if done, "
            "or 'TEST GENERATION FAILED' if not.\n\n"
            "IMPORTANT: Always use 'cd /tmp/workspace && ' prefix. "
            "Do NOT use opencode — write files directly with tee."
        ),
        description=(
            "Generates JUnit 5 tests, verifies they pass, commits and pushes to a branch."
        ),
        tools=[skill_toolset, bash_tool, clone_repository_tool],
        output_key="test_output",
    )
