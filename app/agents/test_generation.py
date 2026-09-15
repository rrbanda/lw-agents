"""Test Generation Agent — SequentialAgent + LoopAgent with EscalationChecker.

Uses the deep-search recipe pattern: a sequential pipeline with an inner
refinement loop that repeats generate -> test -> evaluate until tests pass
(or max iterations reached).

Architecture: initial_writer -> refinement_loop(evaluator -> checker -> fixer) -> pr_opener

The initial writer and the loop fixer are separate instances to avoid
the ADK "agent already has a parent" error on shared sub-agents.
"""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.config import MODEL, SKILLS_DIR, build_bash_tool
from app.tools.scm_tools import clone_repository_tool, create_pull_request_tool


def _create_test_writer(name: str) -> LlmAgent:
    """Create a test writer agent. Uses unique names to avoid parent conflicts."""
    skills = [
        load_skill_from_dir(SKILLS_DIR / "junit-test-generation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)
    bash_tool = build_bash_tool()

    return LlmAgent(
        name=name,
        model=MODEL,
        instruction=(
            "You are a test engineer. You MUST execute these steps in order "
            "using your tools. Do NOT just describe what you would do — "
            "actually call the tools.\n\n"
            "STEP 1 — CLONE: You MUST call clone_repository with the repository "
            "URL and branch from the user's message. This is required.\n\n"
            "STEP 2 — SKILL: Call load_skill to load the junit-test-generation skill.\n\n"
            "STEP 3 — ANALYZE: Use execute_bash to examine the project structure "
            "and identify classes that need test coverage.\n\n"
            "STEP 4 — WRITE: Use execute_bash to run opencode to write JUnit 5 tests. "
            "If tests already exist, use opencode to add more tests or improve coverage.\n\n"
            "STEP 5 — VERIFY: Use execute_bash to run 'cd /tmp/workspace && mvn -B -q test'. "
            "If tests fail, analyze the error and fix using opencode.\n\n"
            "STEP 6 — COMMIT: If tests pass, run:\n"
            "  cd /tmp/workspace && git add src/test/\n"
            "  cd /tmp/workspace && git commit -m 'Add AI-generated unit tests'\n"
            "  cd /tmp/workspace && git push origin HEAD:ai-tests/generated\n\n"
            "IMPORTANT: Always prefix bash commands with 'cd /tmp/workspace && '."
        ),
        description="Generates or fixes JUnit 5 tests using OpenCode.",
        tools=[skill_toolset, bash_tool, clone_repository_tool],
        output_key="test_output",
    )


def _create_test_evaluator() -> LlmAgent:
    """LlmAgent that evaluates whether tests pass."""
    bash_tool = build_bash_tool()

    return LlmAgent(
        name="test_evaluator",
        model=MODEL,
        instruction=(
            "You MUST run 'cd /tmp/workspace && mvn -B -q test' via execute_bash "
            "and evaluate the result.\n\n"
            "After running the command, you MUST respond with EXACTLY one of:\n"
            "  GRADE: pass\n"
            "  GRADE: fail\n\n"
            "If the mvn output contains 'BUILD SUCCESS' or tests ran without "
            "errors, respond: GRADE: pass\n"
            "If the mvn output contains 'BUILD FAILURE' or test errors, "
            "respond: GRADE: fail, followed by a summary.\n\n"
            "You MUST include 'GRADE: pass' or 'GRADE: fail' in your response. "
            "This is required for the pipeline to continue."
        ),
        description="Evaluates whether generated tests pass Maven build.",
        tools=[bash_tool],
        output_key="test_evaluation",
    )


class TestEscalationChecker(BaseAgent):
    """Stops the LoopAgent when tests pass (like deep-search EscalationChecker)."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        evaluation = ctx.session.state.get("test_evaluation", "")
        if isinstance(evaluation, str) and "grade: pass" in evaluation.lower():
            ctx.session.state["structured_result"] = {
                "SELECTED": "0",
                "CVE_ID": "",
                "PACKAGE": "",
                "CURRENT_VERSION": "",
                "FIXED_VERSION": "",
                "JUSTIFICATION": "Tests generated and passing.",
                "PR_URL": "",
                "COUNT": "0",
                "TESTS_ADDED": "1",
                "ISSUES_CREATED": "0",
                "CHANGED": "0",
            }
            yield Event(
                author=self.name,
                actions=EventActions(
                    escalate=True,
                    state_delta={
                        "structured_result": ctx.session.state["structured_result"],
                    },
                ),
            )
        else:
            yield Event(author=self.name)


def _create_pr_opener() -> LlmAgent:
    """Agent that opens the tests-only PR."""
    return LlmAgent(
        name="test_pr_opener",
        model=MODEL,
        instruction=(
            "Open a pull request with the generated tests. Call "
            "create_pull_request with a branch name like 'ai-tests/generated-<timestamp>', "
            "title 'Add AI-generated unit tests', and stage only src/test files. "
            "Use the repo_url and workspace from session state."
        ),
        description="Opens a tests-only pull request.",
        tools=[create_pull_request_tool],
        output_key="pr_result",
    )


def create_test_generation_agent() -> SequentialAgent:
    """Factory: builds the SequentialAgent + LoopAgent pipeline.

    Uses separate agent instances for the initial writer and the loop fixer
    to avoid duplicate names and ADK parent-conflict errors.
    """
    refinement_loop = LoopAgent(
        name="test_refinement_loop",
        sub_agents=[
            _create_test_evaluator(),
            TestEscalationChecker(name="test_escalation_checker"),
            _create_test_writer("test_fixer"),
        ],
        max_iterations=3,
    )

    return SequentialAgent(
        name="test_generation",
        description=(
            "Generates JUnit 5 tests via OpenCode, iterates until they pass "
            "(up to 3 attempts), then opens a tests-only pull request."
        ),
        sub_agents=[
            _create_test_writer("initial_test_writer"),
            refinement_loop,
            _create_pr_opener(),
        ],
    )
