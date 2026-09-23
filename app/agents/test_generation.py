"""Test Generation Agent — SequentialAgent pipeline.

Architecture (mirrors remediation.py):
  SequentialAgent:
    1. investigator    (LlmAgent) — clone, investigate CVE, build test spec
    2. test_writer     (LlmAgent/OpenCode) — generate test from spec
    3. TestResultChecker (BaseAgent) — check if test file exists + compiles
    4. retry_loop      (LoopAgent) — if check fails, fixer → re-check (max 2)
    5. committer       (LlmAgent) — git add/commit/push

TestResultChecker emits TESTS_ADDED=1 via Event.state_delta (same
pattern as BuildResultChecker in remediation.py). No keyword matching.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
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

logger = logging.getLogger(__name__)

WORKSPACE = os.environ.get("WORKSPACE_PATH", "/tmp/workspace")


# ============================================================================
# Step 1: Investigator — clone repo, investigate CVE, build test specification
# ============================================================================

_INVESTIGATOR_INSTRUCTION = (
    "You are a CVE investigator. Your ONLY job is to research the CVE "
    "and produce a TEST SPECIFICATION. Do NOT write code or create files.\n\n"
    "STEP 1 — CLONE: Call clone_repository with the repo URL and branch.\n\n"
    "STEP 2 — INVESTIGATE:\n"
    "  a) Call search_github_advisory(cve_id) → find fix commits\n"
    "  b) Call fetch_commit_diff(commit_url) → see the actual fix\n"
    "  c) Call lookup_nvd(cve_id) → get CWE classification\n"
    "  d) Look for test files in the upstream diff\n\n"
    "STEP 3 — CHECK EXISTING COVERAGE:\n"
    "Before writing anything, check what tests already exist:\n"
    "  cd /tmp/workspace && find src/test -name '*Test.java' | head -30\n"
    "  cd /tmp/workspace && grep -rl '<vulnerable class name>' src/test/ | head -10\n\n"
    "If tests exist for the vulnerable class, READ them:\n"
    "  cd /tmp/workspace && cat src/test/java/.../ExistingTest.java\n\n"
    "Determine:\n"
    "  A) No tests for the vulnerable class → write new reproducer\n"
    "  B) Tests exist but don't cover the CVE attack → add CVE-specific "
    "test method or create a separate reproducer file\n"
    "  C) Tests exist and partially cover the CVE → enhance with edge "
    "cases and additional attack vectors\n"
    "  D) Exact reproducer already exists → enhance with boundary tests, "
    "different encodings, or negative test cases\n\n"
    "NEVER skip. Always add value — more attack vectors, edge cases, "
    "or boundary conditions that the existing tests don't cover.\n\n"
    "STEP 4 — OUTPUT a test specification in this exact format "
    "(see references/test-specification-template.md for examples):\n\n"
    "  CVE: <cve-id>\n"
    "  COMPONENT: <group:artifact>\n"
    "  CWE: <cwe-id> (<cwe name>)\n"
    "  VULNERABLE CLASS: <fully qualified class from the diff>\n"
    "  VULNERABLE METHOD: <method that was fixed>\n"
    "  VULNERABILITY: <1-2 sentences describing what is wrong>\n"
    "  ATTACK: <what malicious input the attacker sends>\n"
    "  ASSERTION: <what the test should check to prove the fix works>\n"
    "  TEST PATH: src/test/java/<package>/CveYYYYNNNNNReproducerTest.java\n"
    "  FIXED VERSION: <version>\n"
    "  UPSTREAM COMMIT: <URL if found>\n"
    "  EXISTING COVERAGE: none | partial (<what exists>) | full (<file>)\n"
    "  ACTION: new_file | add_method | enhance_existing\n"
    "  STRATEGY: upstream_reproducer | cve_targeted | generic\n\n"
    "The more specific the spec, the better the generated test. "
    "Fill every field from your investigation.\n"
)


def _create_investigator() -> LlmAgent:
    skills = [
        load_skill_from_dir(SKILLS_DIR / "junit-test-generation"),
        load_skill_from_dir(SKILLS_DIR / "scm-conventions"),
    ]
    return LlmAgent(
        name="test_investigator",
        model=MODEL,
        instruction=_INVESTIGATOR_INSTRUCTION,
        description="Investigates CVE and produces a test specification.",
        tools=[
            SkillToolset(skills=skills),
            build_bash_tool(),
            clone_repository_tool,
            FunctionTool(search_github_advisory),
            FunctionTool(fetch_commit_diff),
            FunctionTool(discover_upstream_repo),
            FunctionTool(search_fix_commits),
            FunctionTool(lookup_nvd),
            FunctionTool(lookup_osv),
        ],
        output_key="test_spec",
    )


# ============================================================================
# Step 2: Test writer — generate code from spec (OpenCode or tee)
# ============================================================================

_TEE_WRITER_INSTRUCTION = (
    "You are a test code writer. Read the test specification from "
    "the conversation and write the test file using bash (mkdir + tee).\n\n"
    "cd /tmp/workspace && mkdir -p <directory>\n"
    "cd /tmp/workspace && tee <TEST PATH from spec> << 'ENDTEST'\n"
    "<JUnit 5 test code based on the specification>\n"
    "ENDTEST\n\n"
    "After writing, verify:\n"
    "  cd /tmp/workspace && cat <file>  (confirm content)\n"
    "  cd /tmp/workspace && mvn -B -q -DskipTests compile  (confirm it compiles)\n"
    "If compile fails, fix and retry once.\n"
)


def _create_test_writer() -> LlmAgent:
    """Create the agent that writes test code.

    With OpenCode: uses opencode_test_gen sub-agent (receives spec, generates code)
    Without OpenCode: writes test file directly via tee
    """
    oc = is_opencode_available()
    sub_agents = []

    if oc:
        sub_agents.append(create_opencode_test_generator("opencode_test_gen"))
        instruction = (
            "You are a test code writer. Read the test specification from "
            "the conversation and delegate to opencode_test_gen.\n\n"
            "Pass the SPECIFICATION (not code!) — describe:\n"
            "  - CVE ID, CWE, vulnerable class\n"
            "  - What to test and what to assert\n"
            "  - File path for the test\n\n"
            "OpenCode will read the project and write a compilable test.\n"
            "After OpenCode finishes, verify the file exists:\n"
            "  cd /tmp/workspace && ls -la <TEST PATH>\n"
        )
    else:
        instruction = _TEE_WRITER_INSTRUCTION

    return LlmAgent(
        name="test_writer",
        model=MODEL,
        instruction=instruction,
        description="Writes test code from specification."
        + (" Delegates to OpenCode." if oc else " Uses tee."),
        sub_agents=sub_agents,
        tools=[build_bash_tool()],
        output_key="coding_output",
    )


# ============================================================================
# Step 3: TestResultChecker — inspect filesystem, emit TESTS_ADDED
# ============================================================================


class TestResultChecker(BaseAgent):
    """Check if test files were actually created. Emit TESTS_ADDED via state_delta.

    This is the same pattern as BuildResultChecker in remediation.py:
    inspect REALITY (filesystem) instead of parsing LLM prose.

    On success: sets TESTS_ADDED=1, escalates to stop retry loop.
    On failure: injects feedback for the fixer.
    """

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        # Resolve workspace: session state > env var > /tmp/workspace
        workspace = ctx.session.state.get("workspace_path", WORKSPACE)
        if not os.path.isdir(workspace):
            workspace = "/tmp/workspace"
        if not os.path.isdir(workspace):
            logger.info("TestResultChecker: workspace %s not found", workspace)
            ctx.session.state["compile_error"] = f"Workspace not found: {workspace}"
            yield Event(author=self.name)
            return

        logger.info("TestResultChecker: checking workspace %s", workspace)

        # Find any *Test.java or *Tests.java files under src/test
        test_dir = os.path.join(workspace, "src", "test")
        test_files = []
        if os.path.isdir(test_dir):
            for root, _dirs, files in os.walk(test_dir):
                for f in files:
                    if f.endswith("Test.java") or f.endswith("Tests.java"):
                        rel = os.path.relpath(os.path.join(root, f), workspace)
                        test_files.append(rel)

        # Check specifically for CVE reproducer tests
        cve_tests = [f for f in test_files if "Cve" in f or "cve" in f.lower()]

        if cve_tests:
            logger.info(
                "TestResultChecker: FOUND %d CVE test files: %s",
                len(cve_tests),
                cve_tests,
            )

            # Try a compile check
            compile_ok = False
            try:
                result = subprocess.run(
                    ["mvn", "-B", "-q", "-DskipTests", "compile"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                compile_ok = result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                compile_ok = False

            if compile_ok:
                logger.info("TestResultChecker: Compile OK → TESTS_ADDED=1")
                ctx.session.state["tests_added"] = True
                ctx.session.state["test_files"] = cve_tests
                ctx.session.state["structured_result"] = {
                    "SELECTED": "0",
                    "CVE_ID": "",
                    "PACKAGE": "",
                    "CURRENT_VERSION": "",
                    "FIXED_VERSION": "",
                    "JUSTIFICATION": f"Tests created: {', '.join(cve_tests)}",
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
                            "tests_added": True,
                            "test_files": cve_tests,
                        },
                    ),
                )
                return

            # Compile failed — inject feedback for fixer
            logger.info(
                "TestResultChecker: Compile FAILED for %s",
                cve_tests,
            )
            ctx.session.state["compile_error"] = (
                result.stderr[-2000:] if result else "compile timeout"
            )
            ctx.session.state["test_files_need_fix"] = cve_tests
            yield Event(author=self.name)
            return

        # No test files found at all
        logger.info("TestResultChecker: NO CVE test files found in %s", test_dir)
        ctx.session.state["compile_error"] = "No CVE test files found in src/test/"
        yield Event(author=self.name)


# ============================================================================
# Step 4: Committer — git add/commit/push
# ============================================================================


def _create_committer() -> LlmAgent:
    return LlmAgent(
        name="test_committer",
        model=MODEL,
        instruction=(
            "Commit and push the generated test files.\n\n"
            "  cd /tmp/workspace && git add src/test/\n"
            "  cd /tmp/workspace && git commit -m 'Add CVE reproducer test'\n"
            "  cd /tmp/workspace && git push origin HEAD:ai-tests/generated\n\n"
            "Report the result as JSON:\n"
            '  {"tests_generated": true, "test_files": [<list>]}\n'
        ),
        description="Commits and pushes generated test files.",
        tools=[build_bash_tool()],
        output_key="test_output",
    )


# ============================================================================
# Factory
# ============================================================================


def create_test_generation_agent() -> SequentialAgent:
    """Factory: SequentialAgent pipeline for CVE-aware test generation.

    Architecture:
      investigator → test_writer → retry_loop(checker → fixer) → committer

    Each step is enforced by SequentialAgent — no LLM non-determinism
    in step ordering. Same pattern as create_remediation_agent().
    """
    oc = is_opencode_available()

    # Build the fixer for the retry loop
    fixer_agents = []
    if oc:
        fixer_agents.append(create_opencode_fixer("opencode_fixer"))
    else:
        fixer_agents.append(
            LlmAgent(
                name="test_fixer",
                model=MODEL,
                instruction=(
                    "The previous test file has compilation errors. "
                    "Read the compile_error from context and fix the test file.\n"
                    "Use execute_bash with sed or tee to fix the file, "
                    "then run: cd /tmp/workspace && mvn -B -q -DskipTests compile\n"
                ),
                description="Fixes compilation errors in generated tests.",
                tools=[build_bash_tool()],
                output_key="fix_output",
            )
        )

    retry_loop = LoopAgent(
        name="test_retry_loop",
        sub_agents=[
            TestResultChecker(name="test_result_checker"),
            *fixer_agents,
        ],
        max_iterations=2,
    )

    return SequentialAgent(
        name="test_generation",
        description=(
            "Generates CVE-aware tests: investigates CVE, writes tests, "
            "verifies compilation, and commits."
            + (" Uses OpenCode for code generation." if oc else " Uses tee.")
        ),
        sub_agents=[
            _create_investigator(),
            _create_test_writer(),
            retry_loop,
            _create_committer(),
        ],
    )
