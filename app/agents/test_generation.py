"""Test Generation Agent — single LlmAgent that clones, generates tests,
verifies, and pushes.

Simplified from the SequentialAgent + LoopAgent pattern to match the
remediation agent's proven approach: one agent does everything in one
execution context.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.config import MODEL, SKILLS_DIR, build_bash_tool
from app.tools.scm_tools import clone_repository_tool


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
        instruction=(
            "You are a test engineer. You MUST execute these steps in order "
            "using your tools. Do NOT just describe what you would do — "
            "actually call the tools.\n\n"
            "STEP 1 — CLONE: You MUST call clone_repository with the repository "
            "URL and branch from the user's message.\n\n"
            "STEP 2 — SKILL: Call load_skill to load the junit-test-generation skill.\n\n"
            "STEP 3 — ANALYZE: Use execute_bash to run "
            "'cd /tmp/workspace && find src/main -name \"*.java\" | head -20' "
            "to see the project structure.\n\n"
            "STEP 4 — WRITE: Use execute_bash to run opencode to write JUnit 5 tests:\n"
            "cd /tmp/workspace && opencode run 'Generate JUnit 5 tests for the "
            "service classes. Create test files in src/test/java with the correct "
            "package structure. Use Mockito for mocking dependencies.'\n\n"
            "STEP 5 — VERIFY: Use execute_bash to run "
            "'cd /tmp/workspace && mvn -B -q test'. "
            "If tests fail, use opencode to fix them. Retry up to 2 times.\n\n"
            "STEP 6 — COMMIT AND PUSH: If tests pass, run:\n"
            "  cd /tmp/workspace && git add src/test/\n"
            "  cd /tmp/workspace && git diff --cached --stat\n"
            "  cd /tmp/workspace && git commit -m 'Add AI-generated unit tests'\n"
            "  cd /tmp/workspace && git push origin HEAD:ai-tests/generated\n\n"
            "STEP 7 — REPORT: Report 'TESTS GENERATED' if tests were created "
            "and pass, or 'TEST GENERATION FAILED' if not.\n\n"
            "IMPORTANT: Always prefix bash commands with 'cd /tmp/workspace && '."
        ),
        description=(
            "Generates JUnit 5 tests via OpenCode, verifies they pass, "
            "commits and pushes to a branch."
        ),
        tools=[skill_toolset, bash_tool, clone_repository_tool],
        output_key="test_output",
    )
