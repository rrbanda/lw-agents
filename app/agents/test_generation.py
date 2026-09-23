"""Test Generation Agent — SequentialAgent pipeline.

Architecture:
  SequentialAgent:
    1. investigator      (LlmAgent)  — clone, investigate CVE, build test spec
    2. test_writer       (LlmAgent)  — generate test from spec (OpenCode or tee)
    3. TestResultChecker  (BaseAgent) — filesystem check: new/modified test files
    4. retry_loop        (LoopAgent)  — if check fails, fixer → re-check (max 2)
    5. test_committer    (BaseAgent)  — deterministic git add/commit/push

Token efficiency:
  - Investigator: NO skills loaded (only CVE tools — saves ~2K tokens)
  - Writer (OC mode): NO bash tool (only delegates — saves duplication)
  - Committer: BaseAgent, NOT LlmAgent (saves ~500 tokens — git is deterministic)
  - TestResultChecker: compares against pre-snapshot, not just CVE-named files
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
# Step 1: Investigator — clone, investigate CVE, check coverage, build spec
# NO skills loaded — only CVE investigation tools (saves ~2K tokens)
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
    "  cd /tmp/workspace && find src/test -name '*Test.java' | head -30\n"
    "  cd /tmp/workspace && grep -rl '<vulnerable class name>' "
    "src/test/ | head -10\n\n"
    "If tests exist for the vulnerable class, READ them:\n"
    "  cd /tmp/workspace && cat src/test/java/.../ExistingTest.java\n\n"
    "Determine:\n"
    "  A) No tests for the vulnerable class → new_file\n"
    "  B) Tests exist but don't cover the CVE attack → new_file\n"
    "  C) Tests partially cover the CVE → enhance_existing\n"
    "  D) Exact reproducer exists → enhance with edge cases\n\n"
    "NEVER skip. Always add value.\n\n"
    "STEP 4 — SNAPSHOT existing test files for later comparison:\n"
    "  cd /tmp/workspace && find src/test -name '*.java' "
    "-exec md5sum {} \\; > /tmp/test_snapshot.txt 2>/dev/null\n\n"
    "STEP 5 — OUTPUT a test specification:\n"
    "  CVE: <cve-id>\n"
    "  COMPONENT: <group:artifact>\n"
    "  CWE: <cwe-id> (<cwe name>)\n"
    "  VULNERABLE CLASS: <fully qualified class from the diff>\n"
    "  VULNERABLE METHOD: <method that was fixed>\n"
    "  VULNERABILITY: <1-2 sentences>\n"
    "  ATTACK: <what malicious input to construct>\n"
    "  ASSERTION: <what to check to prove fix works>\n"
    "  TEST PATH: src/test/java/<package>/"
    "CveYYYYNNNNNReproducerTest.java\n"
    "  FIXED VERSION: <version>\n"
    "  UPSTREAM COMMIT: <URL if found>\n"
    "  EXISTING COVERAGE: none | partial (<what>) | full (<file>)\n"
    "  ACTION: new_file | add_method | enhance_existing\n"
    "  STRATEGY: upstream_reproducer | cve_targeted | generic\n"
)


def _create_investigator() -> LlmAgent:
    """Investigator: CVE research + spec. NO skills (saves tokens)."""
    return LlmAgent(
        name="test_investigator",
        model=MODEL,
        instruction=_INVESTIGATOR_INSTRUCTION,
        description="Investigates CVE and produces a test specification.",
        tools=[
            # Only CVE investigation tools — no skills needed
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
# Step 2: Test writer — generate code from spec
# OpenCode mode: NO bash tool (delegates to sub-agent)
# Tee mode: has bash + skills for direct writing
# ============================================================================

_TEE_WRITER_INSTRUCTION = (
    "You are a test code writer. Read the test specification from "
    "the conversation and write the test file using bash.\n\n"
    "Use the ACTION field from the spec:\n"
    "  new_file → mkdir + tee to create new file\n"
    "  add_method → read existing file, add test method via tee\n"
    "  enhance_existing → read existing, write enhanced version\n\n"
    "cd /tmp/workspace && mkdir -p <directory>\n"
    "cd /tmp/workspace && tee <TEST PATH> << 'ENDTEST'\n"
    "<JUnit 5 test code based on the specification>\n"
    "ENDTEST\n\n"
    "After writing, verify:\n"
    "  cd /tmp/workspace && cat <file>\n"
    "  cd /tmp/workspace && mvn -B -q -DskipTests compile\n"
    "If compile fails, fix and retry once.\n"
)

_OC_WRITER_INSTRUCTION = (
    "You are a test code writer. Read the test specification from "
    "the conversation and delegate to opencode_test_gen.\n\n"
    "Pass the FULL SPECIFICATION text to the sub-agent. Include "
    "every field: CVE, CWE, class, method, attack, assertion, "
    "existing coverage, and action.\n\n"
    "After delegation, verify the file exists:\n"
    "  Check session state for coding_output confirmation.\n"
)


def _create_test_writer() -> LlmAgent:
    """Test writer: generates code from spec.

    OpenCode mode: NO bash, NO skills — only delegates to sub-agent.
    Tee mode: has bash + skill for direct file writing.
    """
    oc = is_opencode_available()

    if oc:
        return LlmAgent(
            name="test_writer",
            model=MODEL,
            instruction=_OC_WRITER_INSTRUCTION,
            description="Delegates test writing to OpenCode.",
            sub_agents=[create_opencode_test_generator("opencode_test_gen")],
            # NO bash tool — delegates everything to sub-agent
            tools=[],
            output_key="coding_output",
        )

    skills = [load_skill_from_dir(SKILLS_DIR / "junit-test-generation")]
    return LlmAgent(
        name="test_writer",
        model=MODEL,
        instruction=_TEE_WRITER_INSTRUCTION,
        description="Writes test code via tee.",
        tools=[SkillToolset(skills=skills), build_bash_tool()],
        output_key="coding_output",
    )


# ============================================================================
# Step 3: TestResultChecker — filesystem verification
# Compares against pre-snapshot to detect ANY new/modified test files
# ============================================================================


class TestResultChecker(BaseAgent):
    """Verify tests were created by checking the filesystem.

    Compares current test files against the snapshot taken by the
    investigator. Detects new files AND modified existing files.
    This catches:
      - New CveXxxxxReproducerTest.java files
      - Enhanced existing test files (modified checksums)
      - Files renamed or added without "Cve" in the name
    """

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        workspace = ctx.session.state.get("workspace_path", WORKSPACE)
        if not os.path.isdir(workspace):
            workspace = "/tmp/workspace"
        if not os.path.isdir(workspace):
            ctx.session.state["compile_error"] = f"Workspace not found: {workspace}"
            yield Event(author=self.name)
            return

        # Load pre-snapshot (taken by investigator in Step 4)
        old_checksums: dict[str, str] = {}
        snapshot_path = "/tmp/test_snapshot.txt"
        if os.path.isfile(snapshot_path):
            try:
                for line in open(snapshot_path).readlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        old_checksums[parts[1]] = parts[0]
            except OSError:
                pass

        # Current test files with checksums
        test_dir = os.path.join(workspace, "src", "test")
        new_checksums: dict[str, str] = {}
        if os.path.isdir(test_dir):
            try:
                result = subprocess.run(
                    ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                for line in result.stdout.strip().splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        new_checksums[parts[1]] = parts[0]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Detect changes: new files + modified files
        new_files = [f for f in new_checksums if f not in old_checksums]
        modified_files = [
            f for f in new_checksums if f in old_checksums and new_checksums[f] != old_checksums[f]
        ]
        changed_files = new_files + modified_files

        if not changed_files:
            logger.info("TestResultChecker: no new/modified test files")
            ctx.session.state["compile_error"] = "No test files were created or modified"
            yield Event(author=self.name)
            return

        logger.info(
            "TestResultChecker: %d new, %d modified: %s",
            len(new_files),
            len(modified_files),
            changed_files,
        )

        # Compile check
        compile_ok = False
        compile_error = ""
        try:
            result = subprocess.run(
                ["mvn", "-B", "-q", "-DskipTests", "compile"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
            )
            compile_ok = result.returncode == 0
            if not compile_ok:
                compile_error = result.stderr[-2000:]
        except subprocess.TimeoutExpired:
            compile_error = "compile timeout"
        except FileNotFoundError:
            compile_error = "mvn not found"

        if compile_ok:
            logger.info("TestResultChecker: compile OK → TESTS_ADDED=1")
            ctx.session.state["tests_added"] = True
            ctx.session.state["test_files"] = changed_files
            ctx.session.state["structured_result"] = {
                "SELECTED": "0",
                "CVE_ID": "",
                "PACKAGE": "",
                "CURRENT_VERSION": "",
                "FIXED_VERSION": "",
                "JUSTIFICATION": (f"Tests: {', '.join(changed_files)}"),
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
                        "structured_result": (ctx.session.state["structured_result"]),
                        "tests_added": True,
                        "test_files": changed_files,
                    },
                ),
            )
            return

        # Compile failed
        logger.info(
            "TestResultChecker: compile FAILED: %s",
            compile_error[:200],
        )
        ctx.session.state["compile_error"] = compile_error
        ctx.session.state["test_files_need_fix"] = changed_files
        yield Event(author=self.name)


# ============================================================================
# Step 5: Committer — deterministic git commands (BaseAgent, NOT LlmAgent)
# Saves ~500 tokens per run — git add/commit/push is fully deterministic
# ============================================================================


class TestCommitter(BaseAgent):
    """Deterministic git add/commit/push. No LLM needed."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        workspace = ctx.session.state.get("workspace_path", WORKSPACE)
        if not os.path.isdir(workspace):
            workspace = "/tmp/workspace"

        test_files = ctx.session.state.get("test_files", [])
        if not test_files and not ctx.session.state.get("tests_added"):
            logger.info("TestCommitter: no tests to commit")
            yield Event(author=self.name)
            return

        commands = [
            ["git", "add", "src/test/"],
            ["git", "commit", "-m", "Add CVE reproducer test"],
            ["git", "push", "origin", "HEAD:ai-tests/generated"],
        ]

        output_lines = []
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output_lines.append(
                    f"$ {' '.join(cmd)}: {'OK' if result.returncode == 0 else 'FAIL'}"
                )
                if result.returncode != 0:
                    output_lines.append(result.stderr[:500])
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                output_lines.append(f"$ {' '.join(cmd)}: ERROR {exc}")
                break

        output = "\n".join(output_lines)
        logger.info("TestCommitter: %s", output)

        # Set structured_result with test_output for coordinator
        ctx.session.state["test_output"] = output
        if "FAIL" not in output and "ERROR" not in output:
            sr = ctx.session.state.get("structured_result", {})
            sr["TESTS_ADDED"] = "1"
            ctx.session.state["structured_result"] = sr

        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={"test_output": output},
            ),
        )


# ============================================================================
# Factory
# ============================================================================


def create_test_generation_agent() -> SequentialAgent:
    """Factory: SequentialAgent pipeline for CVE-aware test generation.

    Token-efficient architecture:
      investigator (no skills) → writer → retry_loop → committer (no LLM)
    """
    oc = is_opencode_available()

    fixer_agents: list = []
    if oc:
        fixer_agents.append(create_opencode_fixer("opencode_fixer"))
    else:
        fixer_agents.append(
            LlmAgent(
                name="test_fixer",
                model=MODEL,
                instruction=(
                    "Fix the compilation error in the test file. "
                    "Read compile_error from context. "
                    "Use sed or tee to fix the file, then verify:\n"
                    "  cd /tmp/workspace && mvn -B -q "
                    "-DskipTests compile\n"
                ),
                description="Fixes test compilation errors.",
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
            "CVE-aware test generation: investigate → write → "
            "verify → fix → commit." + (" Uses OpenCode." if oc else " Uses tee.")
        ),
        sub_agents=[
            _create_investigator(),
            _create_test_writer(),
            retry_loop,
            TestCommitter(name="test_committer"),
        ],
    )
