"""Test Generation Agent — SequentialAgent + LoopAgent with EscalationChecker.

Uses the deep-search recipe pattern: a sequential pipeline with an inner
refinement loop that repeats generate -> test -> evaluate until tests pass
(or max iterations reached).
"""

from __future__ import annotations

import os
import pathlib
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.skills import load_skill_from_dir
from google.adk.tools.bash_tool import BashToolPolicy, ExecuteBashTool
from google.adk.tools.skill_toolset import SkillToolset

from app.tools.scm_tools import create_pull_request_tool

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "skills"


def _build_bash_tool(workspace: str) -> ExecuteBashTool:
    return ExecuteBashTool(
        workspace=workspace,
        policy=BashToolPolicy(
            allowed_command_prefixes=(
                "opencode ", "mvn ", "cat ", "ls ", "head ", "grep ", "find ",
            ),
            timeout_seconds=300,
            max_memory_bytes=1024 * 1024 * 1024,
        ),
    )


def _create_test_generator() -> LlmAgent:
    """LlmAgent that generates/fixes tests using OpenCode."""
    skills = [
        load_skill_from_dir(SKILLS_DIR / "junit-test-generation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    skill_toolset = SkillToolset(skills=skills)
    workspace = os.environ.get("WORKSPACE_PATH", "/workspace/source")
    bash_tool = _build_bash_tool(workspace)

    return LlmAgent(
        name="test_writer",
        model=MODEL,
        instruction=(
            "You are a test engineer. Load the junit-test-generation skill "
            "and follow its process to generate JUnit 5 tests. Use opencode "
            "via bash to write tests and mvn to verify them. If tests fail, "
            "analyze the error and report what needs fixing."
        ),
        tools=[skill_toolset, bash_tool],
        output_key="test_output",
    )


def _create_test_evaluator() -> LlmAgent:
    """LlmAgent that evaluates whether tests pass."""
    workspace = os.environ.get("WORKSPACE_PATH", "/workspace/source")
    bash_tool = _build_bash_tool(workspace)

    return LlmAgent(
        name="test_evaluator",
        model=MODEL,
        instruction=(
            "Run 'mvn -B -q test' via bash and evaluate the result. "
            "If all tests pass, respond with exactly: GRADE: pass. "
            "If tests fail, respond with: GRADE: fail, followed by "
            "a summary of what needs fixing."
        ),
        tools=[bash_tool],
        output_key="test_evaluation",
    )


class TestEscalationChecker(BaseAgent):
    """Stops the LoopAgent when tests pass (like deep-search EscalationChecker)."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        evaluation = ctx.session.state.get("test_evaluation", "")
        if isinstance(evaluation, str) and "GRADE: pass" in evaluation.lower():
            yield Event(
                author=self.name,
                actions=EventActions(escalate=True),
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
            "create_pull_request with branch 'ai-tests/generated-{timestamp}', "
            "title 'Add AI-generated unit tests', and stage only src/test files. "
            "Use the repo_url and workspace from session state."
        ),
        tools=[create_pull_request_tool],
        output_key="pr_result",
    )


def create_test_generation_agent() -> SequentialAgent:
    """Factory: builds the SequentialAgent + LoopAgent pipeline."""
    test_writer = _create_test_generator()
    test_evaluator = _create_test_evaluator()
    escalation_checker = TestEscalationChecker(name="test_escalation_checker")

    refinement_loop = LoopAgent(
        name="test_refinement_loop",
        sub_agents=[test_evaluator, escalation_checker, test_writer],
        max_iterations=3,
    )

    return SequentialAgent(
        name="test_generation",
        description=(
            "Generates JUnit 5 tests via OpenCode, iterates until they pass "
            "(up to 3 attempts), then opens a tests-only pull request."
        ),
        sub_agents=[
            _create_test_generator(),
            refinement_loop,
            _create_pr_opener(),
        ],
    )
