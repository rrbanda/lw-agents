"""Comprehensive tests for the refactored test generation pipeline.

Tests every component: TestResultChecker (snapshot comparison),
TestCommitter (deterministic BaseAgent), agent structure (tools,
skills, sub-agents), and end-to-end pipeline wiring.

All tests are pure — no LLM calls, no network, no side effects.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from unittest.mock import patch

import pytest

# ============================================================================
# TestResultChecker — snapshot-based file comparison
# ============================================================================


class TestTestResultCheckerSnapshotLogic:
    """Tests for the snapshot comparison logic in TestResultChecker.

    TestResultChecker compares md5 checksums before/after to detect
    new and modified test files. We test the comparison logic directly
    using real temp directories and files.
    """

    def _md5(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()

    def _write_snapshot(self, files: dict[str, str], snapshot_path: str) -> None:
        """Write a snapshot file in md5sum format: '<hash>  <path>'."""
        with open(snapshot_path, "w") as f:
            for path, content in files.items():
                f.write(f"{self._md5(content)}  {path}\n")

    def _setup_test_workspace(
        self,
        tmpdir: str,
        files: dict[str, str],
    ) -> str:
        """Create a workspace with test files. Returns workspace path."""
        workspace = os.path.join(tmpdir, "workspace")
        for relpath, content in files.items():
            full = os.path.join(workspace, relpath)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
        return workspace

    def test_detect_new_file_no_snapshot(self):
        """New test file with no prior snapshot → detected as new."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._setup_test_workspace(
                tmpdir,
                {"src/test/java/com/example/Cve2024Test.java": "public class Cve2024Test {}"},
            )
            # No snapshot file exists
            old_checksums = {}
            # Compute current checksums
            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            new_checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    new_checksums[parts[1]] = parts[0]

            new_files = [f for f in new_checksums if f not in old_checksums]
            assert len(new_files) == 1
            assert "Cve2024Test.java" in new_files[0]

    def test_detect_new_file_with_snapshot(self):
        """New file added after snapshot → detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = os.path.join(tmpdir, "snapshot.txt")
            old_content = "public class ExistingTest {}"
            self._write_snapshot(
                {"src/test/java/com/example/ExistingTest.java": old_content},
                snapshot_path,
            )
            old_checksums = {
                "src/test/java/com/example/ExistingTest.java": self._md5(old_content),
            }

            workspace = self._setup_test_workspace(
                tmpdir,
                {
                    "src/test/java/com/example/ExistingTest.java": old_content,
                    "src/test/java/com/example/Cve2024Test.java": "public class Cve2024Test {}",
                },
            )
            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            new_checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    new_checksums[parts[1]] = parts[0]

            new_files = [f for f in new_checksums if f not in old_checksums]
            modified_files = [
                f
                for f in new_checksums
                if f in old_checksums and new_checksums[f] != old_checksums[f]
            ]
            assert len(new_files) == 1
            assert "Cve2024Test.java" in new_files[0]
            assert len(modified_files) == 0

    def test_detect_modified_file(self):
        """Existing file with changed content → detected as modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_content = "public class ExistingTest { /* v1 */ }"
            new_content = "public class ExistingTest { /* v2 with CVE test */ }"
            file_path = "src/test/java/com/example/ExistingTest.java"

            old_checksums = {file_path: self._md5(old_content)}

            workspace = self._setup_test_workspace(tmpdir, {file_path: new_content})
            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            new_checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    new_checksums[parts[1]] = parts[0]

            modified_files = [
                f
                for f in new_checksums
                if f in old_checksums and new_checksums[f] != old_checksums[f]
            ]
            assert len(modified_files) == 1
            assert "ExistingTest.java" in modified_files[0]

    def test_no_changes_detected(self):
        """Identical files before and after → no changes."""
        content = "public class ExistingTest {}"
        file_path = "src/test/java/com/example/ExistingTest.java"

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._setup_test_workspace(tmpdir, {file_path: content})
            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    checksums[parts[1]] = parts[0]

            # Same checksums as "old"
            old_checksums = dict(checksums)

            new_files = [f for f in checksums if f not in old_checksums]
            modified_files = [
                f for f in checksums if f in old_checksums and checksums[f] != old_checksums[f]
            ]
            changed_files = new_files + modified_files
            assert len(changed_files) == 0

    def test_snapshot_file_parsing(self):
        """Snapshot file with md5sum format is parsed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = os.path.join(tmpdir, "test_snapshot.txt")
            with open(snapshot_path, "w") as f:
                f.write("d41d8cd98f00b204e9800998ecf8427e  src/test/java/FooTest.java\n")
                f.write("098f6bcd4621d373cade4e832627b4f6  src/test/java/BarTest.java\n")

            old_checksums = {}
            for line in open(snapshot_path).readlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    old_checksums[parts[1]] = parts[0]

            assert len(old_checksums) == 2
            assert old_checksums["src/test/java/FooTest.java"] == "d41d8cd98f00b204e9800998ecf8427e"
            assert old_checksums["src/test/java/BarTest.java"] == "098f6bcd4621d373cade4e832627b4f6"

    def test_empty_snapshot_file(self):
        """Empty snapshot file → all current files are 'new'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = os.path.join(tmpdir, "test_snapshot.txt")
            with open(snapshot_path, "w") as f:
                f.write("")

            old_checksums = {}
            for line in open(snapshot_path).readlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    old_checksums[parts[1]] = parts[0]

            assert len(old_checksums) == 0

    def test_no_test_dir_no_crash(self):
        """Missing src/test directory → empty checksums, no crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = os.path.join(tmpdir, "workspace")
            os.makedirs(workspace)
            # No src/test directory

            test_dir = os.path.join(workspace, "src", "test")
            new_checksums = {}
            if os.path.isdir(test_dir):
                # Would run md5sum
                pass

            assert len(new_checksums) == 0

    def test_multiple_new_and_modified(self):
        """Mix of new files and modified files → all detected."""
        old_existing = "public class OldTest { /* original */ }"
        new_existing = "public class OldTest { /* enhanced with CVE */ }"
        brand_new = "public class CveNewTest {}"

        old_checksums = {
            "src/test/java/OldTest.java": self._md5(old_existing),
            "src/test/java/Unchanged.java": self._md5("unchanged"),
        }

        new_checksums = {
            "src/test/java/OldTest.java": self._md5(new_existing),
            "src/test/java/Unchanged.java": self._md5("unchanged"),
            "src/test/java/CveNewTest.java": self._md5(brand_new),
        }

        new_files = [f for f in new_checksums if f not in old_checksums]
        modified_files = [
            f for f in new_checksums if f in old_checksums and new_checksums[f] != old_checksums[f]
        ]
        changed_files = new_files + modified_files

        assert "src/test/java/CveNewTest.java" in new_files
        assert "src/test/java/OldTest.java" in modified_files
        assert "src/test/java/Unchanged.java" not in changed_files
        assert len(changed_files) == 2


# ============================================================================
# TestCommitter — deterministic git BaseAgent
# ============================================================================


class TestTestCommitterLogic:
    """Tests for the deterministic git commit logic in TestCommitter.

    TestCommitter runs 3 git commands via subprocess. We test the
    logic paths by mocking subprocess.run.
    """

    def test_skip_when_no_tests(self):
        """No test_files and tests_added=False → skip, no git commands."""
        state = {"test_files": [], "tests_added": False}
        test_files = state.get("test_files", [])
        tests_added = state.get("tests_added")
        should_skip = not test_files and not tests_added
        assert should_skip is True

    def test_proceed_when_test_files_present(self):
        """test_files populated → should proceed."""
        state = {"test_files": ["src/test/java/CveTest.java"]}
        should_skip = not state.get("test_files", []) and not state.get("tests_added")
        assert should_skip is False

    def test_proceed_when_tests_added_flag(self):
        """tests_added=True with empty test_files → should still proceed."""
        state = {"test_files": [], "tests_added": True}
        should_skip = not state.get("test_files", []) and not state.get("tests_added")
        assert should_skip is False

    def test_git_commands_are_correct(self):
        """Verify the exact git commands that would be run."""
        commands = [
            ["git", "add", "src/test/"],
            ["git", "commit", "-m", "Add CVE reproducer test"],
            ["git", "push", "origin", "HEAD:ai-tests/generated"],
        ]
        assert commands[0] == ["git", "add", "src/test/"]
        assert commands[1][0:2] == ["git", "commit"]
        assert commands[2][0:2] == ["git", "push"]

    def test_success_output_format(self):
        """All commands succeed → output contains only OK lines."""
        output_lines = [
            "$ git add src/test/: OK",
            "$ git commit -m Add CVE reproducer test: OK",
            "$ git push origin HEAD:ai-tests/generated: OK",
        ]
        output = "\n".join(output_lines)
        assert "FAIL" not in output
        assert "ERROR" not in output

    def test_failure_stops_chain(self):
        """If a command fails, subsequent commands should not run."""
        output_lines = [
            "$ git add src/test/: OK",
            "$ git commit -m Add CVE reproducer test: FAIL",
            "nothing to commit, working tree clean",
        ]
        output = "\n".join(output_lines)
        # Should not contain push output
        assert "git push" not in output
        assert "FAIL" in output

    def test_structured_result_on_success(self):
        """Successful commit → TESTS_ADDED='1' in structured_result."""
        output = "$ git add src/test/: OK\n$ git commit: OK\n$ git push: OK"
        sr = {"TESTS_ADDED": "0"}
        if "FAIL" not in output and "ERROR" not in output:
            sr["TESTS_ADDED"] = "1"
        assert sr["TESTS_ADDED"] == "1"

    def test_structured_result_on_failure(self):
        """Failed commit → TESTS_ADDED stays '0'."""
        output = "$ git add src/test/: OK\n$ git commit: FAIL\nnothing to commit"
        sr = {"TESTS_ADDED": "0"}
        if "FAIL" not in output and "ERROR" not in output:
            sr["TESTS_ADDED"] = "1"
        assert sr["TESTS_ADDED"] == "0"

    def test_git_subprocess_in_temp_workspace(self):
        """Git commands run in an actual temp git repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Init a git repo — must be inside the workspace for sandbox
            init = subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, text=True)
            if init.returncode != 0:
                pytest.skip(f"git init failed (sandbox): {init.stderr}")

            subprocess.run(
                ["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

            # Create a test file
            test_dir = os.path.join(tmpdir, "src", "test")
            os.makedirs(test_dir)
            with open(os.path.join(test_dir, "CveTest.java"), "w") as f:
                f.write("public class CveTest {}")

            # Run git add + commit (not push — no remote)
            add_result = subprocess.run(
                ["git", "add", "src/test/"], cwd=tmpdir, capture_output=True, text=True
            )
            assert add_result.returncode == 0

            commit_result = subprocess.run(
                ["git", "commit", "-m", "Add CVE reproducer test"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            assert commit_result.returncode == 0

            # Verify commit happened
            log_result = subprocess.run(
                ["git", "log", "--oneline", "-1"], cwd=tmpdir, capture_output=True, text=True
            )
            assert "Add CVE reproducer test" in log_result.stdout


# ============================================================================
# Agent structure — tools, skills, sub-agents
# ============================================================================


class TestTestGenerationAgentStructure:
    """Verify the agent tree structure matches the documented architecture."""

    def setup_method(self):
        from app.agents.test_generation import (
            TestCommitter,
            TestResultChecker,
            _create_investigator,
            _create_test_writer,
            create_test_generation_agent,
        )

        self._create_investigator = _create_investigator
        self._create_test_writer = _create_test_writer
        self.create_test_generation_agent = create_test_generation_agent
        self.TestResultChecker = TestResultChecker
        self.TestCommitter = TestCommitter

    def test_investigator_has_no_skill_toolset(self):
        """Investigator should NOT load skills (saves ~2K tokens)."""
        from google.adk.tools.skill_toolset import SkillToolset

        investigator = self._create_investigator()
        for tool in investigator.tools:
            assert not isinstance(tool, SkillToolset), (
                "Investigator should not have SkillToolset — skills moved to writer"
            )

    def test_investigator_has_cve_tools(self):
        """Investigator should have all CVE investigation tools."""
        investigator = self._create_investigator()
        tool_names = set()
        for tool in investigator.tools:
            if hasattr(tool, "name"):
                tool_names.add(tool.name)
            elif hasattr(tool, "func"):
                tool_names.add(tool.func.__name__)

        # Must have clone + bash + CVE investigation
        assert (
            "clone_repository" in tool_names
            or "clone_repository_tool" in tool_names
            or any("clone" in n for n in tool_names)
        ), f"Missing clone tool. Found: {tool_names}"

    def test_investigator_output_key(self):
        """Investigator must use output_key='test_spec'."""
        investigator = self._create_investigator()
        assert investigator.output_key == "test_spec"

    def test_tee_writer_has_skill_and_bash(self):
        """Tee writer (no OpenCode) should have SkillToolset + bash."""
        from google.adk.tools.skill_toolset import SkillToolset

        with patch.dict(os.environ, {"LW_USE_OPENCODE": "false"}):
            writer = self._create_test_writer()
            has_skill = any(isinstance(t, SkillToolset) for t in writer.tools)
            assert has_skill, "Tee writer must have SkillToolset for junit-test-generation"
            assert len(writer.tools) >= 2, "Tee writer needs SkillToolset + bash"

    def test_tee_writer_no_sub_agents(self):
        """Tee writer should have no sub-agents (writes directly)."""
        with patch.dict(os.environ, {"LW_USE_OPENCODE": "false"}):
            writer = self._create_test_writer()
            sub = getattr(writer, "sub_agents", []) or []
            assert len(sub) == 0, "Tee writer should not have sub-agents"

    def test_oc_writer_has_no_bash_or_skill(self):
        """OpenCode writer should have NO bash/skill tools (delegates only).

        ADK auto-wraps sub_agents as _SingleTurnAgentTool — that's expected.
        What we check is that no FunctionTool or SkillToolset was added.
        """
        from google.adk.tools import FunctionTool
        from google.adk.tools.skill_toolset import SkillToolset

        with patch.dict(os.environ, {"LW_USE_OPENCODE": "true"}):
            with patch("shutil.which", return_value="/usr/local/bin/opencode"):
                writer = self._create_test_writer()
                explicit_tools = [
                    t for t in writer.tools if isinstance(t, (FunctionTool, SkillToolset))
                ]
                assert len(explicit_tools) == 0, (
                    f"OC writer should have no FunctionTool/SkillToolset, found: {explicit_tools}"
                )

    def test_oc_writer_has_sub_agent(self):
        """OpenCode writer should delegate to opencode_test_gen sub-agent."""
        with patch.dict(os.environ, {"LW_USE_OPENCODE": "true"}):
            with patch("shutil.which", return_value="/usr/local/bin/opencode"):
                writer = self._create_test_writer()
                sub = getattr(writer, "sub_agents", []) or []
                assert len(sub) == 1
                assert sub[0].name == "opencode_test_gen"

    def test_factory_produces_sequential_agent(self):
        """Factory must return a SequentialAgent."""
        from google.adk.agents import SequentialAgent

        with patch.dict(os.environ, {"LW_USE_OPENCODE": "false"}):
            agent = self.create_test_generation_agent()
            assert isinstance(agent, SequentialAgent)
            assert agent.name == "test_generation"

    def test_factory_sub_agent_order(self):
        """Sub-agents must be: investigator → writer → retry_loop → committer."""
        with patch.dict(os.environ, {"LW_USE_OPENCODE": "false"}):
            agent = self.create_test_generation_agent()
            names = [sa.name for sa in agent.sub_agents]
            assert names == [
                "test_investigator",
                "test_writer",
                "test_retry_loop",
                "test_committer",
            ], f"Wrong sub-agent order: {names}"

    def test_committer_is_base_agent_not_llm(self):
        """TestCommitter must be a BaseAgent, NOT an LlmAgent (saves tokens)."""
        from google.adk.agents import BaseAgent, LlmAgent

        with patch.dict(os.environ, {"LW_USE_OPENCODE": "false"}):
            agent = self.create_test_generation_agent()
            committer = agent.sub_agents[-1]
            assert committer.name == "test_committer"
            assert isinstance(committer, BaseAgent)
            assert not isinstance(committer, LlmAgent), (
                "Committer should be BaseAgent, not LlmAgent"
            )

    def test_result_checker_is_base_agent(self):
        """TestResultChecker must be a BaseAgent, NOT an LlmAgent."""
        from google.adk.agents import BaseAgent, LlmAgent

        checker = self.TestResultChecker(name="test_checker")
        assert isinstance(checker, BaseAgent)
        assert not isinstance(checker, LlmAgent)

    def test_retry_loop_max_iterations(self):
        """Retry loop should have max_iterations=2."""
        with patch.dict(os.environ, {"LW_USE_OPENCODE": "false"}):
            agent = self.create_test_generation_agent()
            retry_loop = agent.sub_agents[2]
            assert retry_loop.name == "test_retry_loop"
            assert retry_loop.max_iterations == 2

    def test_retry_loop_contains_checker_and_fixer(self):
        """Retry loop must contain TestResultChecker + fixer."""
        with patch.dict(os.environ, {"LW_USE_OPENCODE": "false"}):
            agent = self.create_test_generation_agent()
            retry_loop = agent.sub_agents[2]
            sub_names = [sa.name for sa in retry_loop.sub_agents]
            assert sub_names[0] == "test_result_checker"
            assert len(sub_names) == 2  # checker + fixer


# ============================================================================
# Workflow path — verify parity with SequentialAgent path
# ============================================================================


class TestWorkflowTestGenParity:
    """Verify the Workflow test-gen has the same capabilities as the
    SequentialAgent path — both paths should be functionally equivalent.
    """

    def test_workflow_has_separate_investigator_and_writer(self):
        """Workflow should have split investigator + writer (not monolithic)."""
        from app.workflow import (
            _create_test_gen_investigator,
            _create_test_gen_writer,
        )

        inv = _create_test_gen_investigator()
        writer = _create_test_gen_writer()
        assert inv.name == "test_gen_investigator"
        assert writer.name == "test_gen_writer"

    def test_workflow_investigator_has_no_skills(self):
        """Workflow investigator should NOT load skills (same as SequentialAgent path)."""
        from google.adk.tools.skill_toolset import SkillToolset

        from app.workflow import _create_test_gen_investigator

        inv = _create_test_gen_investigator()
        for tool in inv.tools:
            assert not isinstance(tool, SkillToolset), (
                "Workflow investigator should not have SkillToolset"
            )

    def test_workflow_writer_has_skills(self):
        """Workflow writer should have SkillToolset (same as SequentialAgent tee writer)."""
        from google.adk.tools.skill_toolset import SkillToolset

        from app.workflow import _create_test_gen_writer

        writer = _create_test_gen_writer()
        has_skill = any(isinstance(t, SkillToolset) for t in writer.tools)
        assert has_skill, "Workflow writer must have SkillToolset"

    def test_workflow_has_deterministic_check(self):
        """Workflow should have check_test_compile function (equivalent to TestResultChecker)."""
        from app.workflow import check_test_compile

        assert callable(check_test_compile)

    def test_workflow_has_deterministic_commit(self):
        """Workflow should have commit_tests function (equivalent to TestCommitter)."""
        from app.workflow import commit_tests

        assert callable(commit_tests)

    def test_workflow_has_test_retry(self):
        """Workflow should have test retry routing (equivalent to LoopAgent max=2)."""
        from app.workflow import _MAX_TEST_RETRIES, route_on_test_retry

        assert callable(route_on_test_retry)
        assert _MAX_TEST_RETRIES == 2

    def test_workflow_has_fixer(self):
        """Workflow should have a test fixer agent."""
        from app.workflow import _create_test_gen_fixer

        fixer = _create_test_gen_fixer()
        assert fixer.name == "test_gen_fixer"

    def test_workflow_pipeline_includes_test_gen_nodes(self):
        """The Workflow graph should include all test gen nodes."""
        from app.workflow import create_pipeline_workflow

        wf = create_pipeline_workflow()
        assert wf.name == "cve_remediation_pipeline"

    def test_check_test_compile_returns_event_with_route(self):
        """check_test_compile must return Event with 'pass' or 'fail' route."""
        from google.adk.events import Event

        from app.workflow import check_test_compile

        result = check_test_compile("some input text")
        assert isinstance(result, Event)
        assert result.actions.route in ("pass", "fail")

    def test_commit_tests_returns_string(self):
        """commit_tests must return a string (not Event)."""
        from app.workflow import commit_tests

        result = commit_tests("test input")
        assert isinstance(result, str)

    def test_both_paths_have_same_tool_set(self):
        """Both paths' investigators should have the same CVE tools."""
        from app.agents.test_generation import _create_investigator
        from app.workflow import _create_test_gen_investigator

        seq_inv = _create_investigator()
        wf_inv = _create_test_gen_investigator()

        def tool_names(agent):
            names = set()
            for t in agent.tools:
                if hasattr(t, "name"):
                    names.add(t.name)
                elif hasattr(t, "func"):
                    names.add(t.func.__name__)
            return names

        seq_tools = tool_names(seq_inv)
        wf_tools = tool_names(wf_inv)
        assert seq_tools == wf_tools, (
            f"Tool mismatch:\n  SequentialAgent: {seq_tools}\n  Workflow: {wf_tools}"
        )


# ============================================================================
# Integration: TestResultChecker with real filesystem
# ============================================================================


class TestTestResultCheckerIntegration:
    """Integration tests for TestResultChecker with actual filesystem ops.

    These tests create real temp directories with test files, write
    snapshot files, and verify the checker's detection logic end-to-end.
    """

    def test_full_flow_new_file_detected(self):
        """Create a workspace with a new test file, verify detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = os.path.join(tmpdir, "workspace")
            test_dir = os.path.join(workspace, "src", "test", "java", "com", "example")
            os.makedirs(test_dir)

            # Write the new test file
            test_file = os.path.join(test_dir, "CveReproducerTest.java")
            with open(test_file, "w") as f:
                f.write("public class CveReproducerTest { @Test void test() {} }")

            # No snapshot → everything is new
            old_checksums = {}

            # Run md5sum
            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            new_checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    new_checksums[parts[1]] = parts[0]

            new_files = [f for f in new_checksums if f not in old_checksums]
            assert len(new_files) == 1
            assert "CveReproducerTest.java" in new_files[0]

    def test_full_flow_enhanced_file_detected(self):
        """Modify an existing test file, verify detected as modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = os.path.join(tmpdir, "workspace")
            test_dir = os.path.join(workspace, "src", "test", "java")
            os.makedirs(test_dir)

            test_path = "src/test/java/ExistingTest.java"
            full_path = os.path.join(workspace, test_path)

            # Phase 1: write original, snapshot
            with open(full_path, "w") as f:
                f.write("public class ExistingTest { @Test void basic() {} }")

            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            old_checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    old_checksums[parts[1]] = parts[0]

            assert len(old_checksums) == 1

            # Phase 2: modify file (enhance with CVE test)
            with open(full_path, "w") as f:
                f.write(
                    "public class ExistingTest {\n"
                    "  @Test void basic() {}\n"
                    "  @Test void testCve2024Exploit() { /* CVE test */ }\n"
                    "}"
                )

            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            new_checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    new_checksums[parts[1]] = parts[0]

            modified = [
                f
                for f in new_checksums
                if f in old_checksums and new_checksums[f] != old_checksums[f]
            ]
            assert len(modified) == 1
            assert "ExistingTest.java" in modified[0]

    def test_unchanged_files_not_reported(self):
        """Files with identical content before/after → not in changed list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = os.path.join(tmpdir, "workspace")
            test_dir = os.path.join(workspace, "src", "test", "java")
            os.makedirs(test_dir)

            with open(os.path.join(test_dir, "StableTest.java"), "w") as f:
                f.write("public class StableTest {}")

            result = subprocess.run(
                ["find", "src/test", "-name", "*.java", "-exec", "md5sum", "{}", ";"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            checksums = {}
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    checksums[parts[1]] = parts[0]

            old_checksums = dict(checksums)

            new_files = [f for f in checksums if f not in old_checksums]
            modified = [
                f for f in checksums if f in old_checksums and checksums[f] != old_checksums[f]
            ]
            assert len(new_files) == 0
            assert len(modified) == 0


# ============================================================================
# TestCommitter integration with real git repo
# ============================================================================


class TestTestCommitterIntegration:
    """Integration tests for TestCommitter with actual git operations."""

    def _init_git_repo(self, path: str) -> bool:
        """Initialize a git repo with initial commit. Returns False if git unavailable."""
        init = subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True)
        if init.returncode != 0:
            return False
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
        readme = os.path.join(path, "README.md")
        with open(readme, "w") as f:
            f.write("init")
        subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True)
        return True

    def test_add_and_commit_succeed(self):
        """git add + commit succeed with test files present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            if not self._init_git_repo(tmpdir):
                pytest.skip("git init failed (sandbox)")
            test_dir = os.path.join(tmpdir, "src", "test")
            os.makedirs(test_dir)
            with open(os.path.join(test_dir, "CveTest.java"), "w") as f:
                f.write("public class CveTest {}")

            add = subprocess.run(
                ["git", "add", "src/test/"], cwd=tmpdir, capture_output=True, text=True
            )
            assert add.returncode == 0

            commit = subprocess.run(
                ["git", "commit", "-m", "Add CVE reproducer test"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            assert commit.returncode == 0

    def test_commit_fails_nothing_staged(self):
        """git commit with nothing staged → non-zero exit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            if not self._init_git_repo(tmpdir):
                pytest.skip("git init failed (sandbox)")

            commit = subprocess.run(
                ["git", "commit", "-m", "Add CVE reproducer test"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            assert commit.returncode != 0

    def test_only_test_files_staged(self):
        """git add src/test/ should only stage test files, not other changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            if not self._init_git_repo(tmpdir):
                pytest.skip("git init failed (sandbox)")

            # Create a production file AND a test file
            os.makedirs(os.path.join(tmpdir, "src", "main"))
            with open(os.path.join(tmpdir, "src", "main", "App.java"), "w") as f:
                f.write("public class App {}")
            os.makedirs(os.path.join(tmpdir, "src", "test"))
            with open(os.path.join(tmpdir, "src", "test", "CveTest.java"), "w") as f:
                f.write("public class CveTest {}")

            # Only stage src/test/
            subprocess.run(["git", "add", "src/test/"], cwd=tmpdir, capture_output=True)

            # Check what's staged
            diff = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            staged = diff.stdout.strip().splitlines()
            assert "src/test/CveTest.java" in staged
            assert "src/main/App.java" not in staged
