"""Remediation Agent — SequentialAgent pipeline that reads the pom.xml,
plans the edit, applies it via OpenCode (ExecuteBashTool), verifies via
Maven build with retry, and opens a PR with HITL approval.

Uses SequentialAgent + LoopAgent for the retry logic, following the same
pattern as test_generation.py. The coordinator delegates here when the
task is dependency remediation.

Note: Workflow cannot yet be used as an LlmAgent sub-agent (ADK limitation),
so we use SequentialAgent + LoopAgent which are compatible.
"""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

from app.config import BASE_BRANCH, MODEL, SKILLS_DIR, WORKSPACE_PATH, build_bash_tool
from app.policy.post_gate import post_gate_callback
from app.policy.pre_gate import pre_gate_callback
from app.tools.build_tools import detect_build_system
from app.tools.diff_proof import snapshot_workspace, verify_changes
from app.tools.diff_tools import analyze_diff
from app.tools.live_cve_tools import lookup_nvd, lookup_osv, search_github_advisory
from app.tools.scm_tools import clone_repository_tool, create_pull_request_tool
from app.tools.upstream_tools import discover_upstream_repo, fetch_commit_diff, search_fix_commits


async def _remediation_before_callback(callback_context) -> None:
    """Snapshot workspace, check cost budget, run pre-gate."""
    from google.genai import types as genai_types

    state = callback_context.state

    # G12: Cost budget check — halt if budget exhausted
    max_cost = float(state.get("max_cost_usd", 0) or 0)
    running_cost = float(state.get("running_cost_usd", 0) or 0)
    if max_cost > 0 and running_cost >= max_cost:
        return genai_types.Content(
            role="model",
            parts=[genai_types.Part.from_text(
                text=f"Cost budget exhausted (${running_cost:.2f} "
                f">= ${max_cost:.2f}). Stopping remediation."
            )],
        )

    # Inject build feedback from previous retry if available
    feedback = state.get("build_feedback", "")
    if feedback:
        state["_retry_context"] = feedback

    workspace = state.get("workspace_path") or WORKSPACE_PATH
    import os
    if os.path.isdir(workspace):
        snapshot = snapshot_workspace(workspace)
        state["_workspace_snapshot"] = snapshot

    return await pre_gate_callback(callback_context)


async def _remediation_after_callback(callback_context) -> None:
    """Verify changes via diff proof, run ReDoS lint, then post-gate."""
    from app.tools.diff_tools import check_regex_safety

    state = callback_context.state
    workspace = state.get("workspace_path") or WORKSPACE_PATH
    snapshot = state.get("_workspace_snapshot", {})

    import os
    if snapshot and os.path.isdir(workspace):
        evidence = verify_changes(workspace, snapshot)
        state["diff_content"] = evidence.get("diff_content", "")
        state["changed_files"] = evidence.get("changed_files", [])
        state["diff_proof"] = evidence

        # G6: ReDoS lint on the generated diff
        diff_text = evidence.get("diff_content", "")
        if diff_text:
            regex_result = check_regex_safety(diff_text)
            if not regex_result["safe"]:
                state["regex_lint_warnings"] = [
                    s["risk"] for s in regex_result["smells"]
                ]

    # Then run the post-gate validation on the evidence
    await post_gate_callback(callback_context)


def _create_plan_agent(name: str = "remediation_planner") -> LlmAgent:
    """Create a remediation planner/executor agent.

    Loads both Maven and Gradle remediation skills so the agent can
    handle either build system. The instruction tells it to detect
    the build system first and follow the appropriate skill.

    Args:
        name: Unique agent name (needed to avoid parent conflicts when
              the same kind of agent appears in multiple pipeline stages).
    """
    skill_dirs = [
        SKILLS_DIR / "maven-remediation",
        SKILLS_DIR / "scm-conventions",
    ]
    # Load Gradle skill if available
    gradle_skill_dir = SKILLS_DIR / "gradle-remediation"
    if gradle_skill_dir.exists():
        skill_dirs.append(gradle_skill_dir)

    skills = [load_skill_from_dir(d) for d in skill_dirs]
    skill_toolset = SkillToolset(skills=skills)
    bash_tool = build_bash_tool()

    return LlmAgent(
        name=name,
        model=MODEL,
        before_agent_callback=_remediation_before_callback,
        after_agent_callback=_remediation_after_callback,
        instruction=(
            "You are a remediation engineer. You MUST execute these steps "
            "in order using your tools. Do NOT just describe what you would do — "
            "actually call the tools.\n\n"

            "STEP 1 — CLONE: Call clone_repository with the repository "
            "URL and branch from the user's message.\n\n"

            "STEP 2 — INVESTIGATE THE UPSTREAM FIX: Before editing anything, "
            "understand what the upstream fix actually changed:\n"
            "  a) Call search_github_advisory(cve_id) to find fix commit URLs\n"
            "  b) If commits found, call fetch_commit_diff(commit_url) to see "
            "     the actual code changes\n"
            "  c) Call discover_upstream_repo(package) to find the upstream repo\n"
            "  d) Call search_fix_commits(cve_id, owner, repo) if no commits "
            "     found in the advisory\n"
            "This tells you whether the fix is:\n"
            "  - A simple version bump (only pom.xml/build.gradle changes)\n"
            "  - A source code patch (Java/Python files changed)\n"
            "  - A configuration change\n"
            "If the upstream fix involves source code changes beyond a dependency "
            "version bump, report that in your output — the pipeline may need "
            "source-level patching which requires human review.\n\n"

            "STEP 3 — SKILL: Call load_skill to load the remediation skill "
            "(maven-remediation or gradle-remediation based on build system).\n\n"

            "STEP 4 — READ: Use execute_bash to examine the project:\n"
            "  cd /tmp/workspace && cat pom.xml\n"
            "  (or cat build.gradle / build.gradle.kts for Gradle)\n"
            "Understand: Is the dependency direct? In dependencyManagement? "
            "Via a BOM? A property variable?\n\n"

            "STEP 5 — FIX: Apply the version change. For Maven:\n"
            "  - Property-controlled: edit the property value\n"
            "  - BOM-managed: add a version override property\n"
            "  - Direct dependency: edit the version inline\n"
            "For Gradle: edit build.gradle, version catalog, or ext property.\n"
            "Use sed or direct file writing via execute_bash.\n\n"

            "STEP 6 — BUILD: Run the build:\n"
            "  Maven: cd /tmp/workspace && mvn -B -q -DskipTests install\n"
            "  Gradle: cd /tmp/workspace && ./gradlew build -x test\n"
            "If it fails, report 'BUILD FAILURE' with the error output.\n\n"

            "STEP 7 — TEST: If build passes, run tests:\n"
            "  Maven: cd /tmp/workspace && mvn -B -q verify\n"
            "  Gradle: cd /tmp/workspace && ./gradlew test\n\n"

            "STEP 8 — COMMIT AND PUSH: If tests pass:\n"
            "  cd /tmp/workspace && git add -A\n"
            "  cd /tmp/workspace && git diff --cached --stat\n"
            "  cd /tmp/workspace && git commit -m "
            "'Remediate <CVE>: <package> -> <version>'\n"
            "  cd /tmp/workspace && git push origin "
            "HEAD:rhtpa/remediate-<CVE>\n\n"

            "STEP 9 — REPORT: Report as JSON:\n"
            "  {\"build_status\": \"SUCCESS\"|\"FAILURE\", "
            "\"fix_type\": \"version_bump\"|\"source_patch\"|\"config_change\", "
            "\"upstream_fix_analyzed\": true|false, "
            "\"files_changed\": [\"pom.xml\"]}\n\n"

            "IMPORTANT: Always prefix bash commands with "
            "'cd /tmp/workspace && ' to ensure correct directory."
        ),
        description="Plans and applies a Maven dependency version bump using OpenCode.",
        tools=[
            skill_toolset, bash_tool, clone_repository_tool,
            # G8: Build system detection
            FunctionTool(detect_build_system),
            # G1: Upstream fix investigation
            FunctionTool(lookup_osv),
            FunctionTool(lookup_nvd),
            FunctionTool(search_github_advisory),
            FunctionTool(discover_upstream_repo),
            FunctionTool(search_fix_commits),
            FunctionTool(fetch_commit_diff),
            # G7: Diff analysis for validation
            FunctionTool(analyze_diff),
        ],
        output_key="remediation_output",
    )


class BuildResultChecker(BaseAgent):
    """Checks the build result, classifies failures, and provides feedback.

    On success: escalates to exit the retry loop.
    On failure: classifies the error category (PATCH_ERROR, ENVIRONMENT_ERROR,
    PRE_EXISTING, NETWORK_ERROR), checks for hopeless cases, and injects
    structured feedback into session state for the next retry attempt.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        from app.tools.diff_tools import classify_build_failure

        output = str(ctx.session.state.get("remediation_output", ""))
        output_lower = output.lower()
        build_status = ctx.session.state.get("build_status", "")

        is_success = build_status == "pass" or "build success" in output_lower

        if is_success:
            ctx.session.state["build_passed"] = True
            ctx.session.state["structured_result"] = {
                "SELECTED": "0", "CVE_ID": "", "PACKAGE": "",
                "CURRENT_VERSION": "", "FIXED_VERSION": "",
                "JUSTIFICATION": "Build and tests passed.",
                "PR_URL": "", "COUNT": "0", "TESTS_ADDED": "0",
                "ISSUES_CREATED": "0", "CHANGED": "1",
                "BUILD_STATUS": "SUCCESS",
            }
            yield Event(
                author=self.name,
                actions=EventActions(
                    escalate=True,
                    state_delta={
                        "structured_result": (
                            ctx.session.state["structured_result"]
                        ),
                        "build_passed": True,
                    },
                ),
            )
            return

        # --- Failure path: classify and provide feedback ---
        retry_count = ctx.session.state.get("retry_count", 0) + 1
        ctx.session.state["retry_count"] = retry_count
        ctx.session.state["build_passed"] = False

        # G2: Classify the failure
        classification = classify_build_failure(output)
        category = classification.get("category", "UNKNOWN")
        ctx.session.state["failure_category"] = category
        ctx.session.state["failure_description"] = (
            classification.get("description", "")
        )

        # G4: Hopeless case detection
        missing_patterns = [
            "cannot find symbol", "does not exist",
            "error: file not found", "no such file or directory",
        ]
        missing_count = sum(
            output_lower.count(p) for p in missing_patterns
        )
        error_markers = [
            "compilation error", "] error:", "] ERROR:",
        ]
        error_count = sum(output.count(m) for m in error_markers)

        is_hopeless = missing_count > 3 or error_count > 40
        if is_hopeless:
            ctx.session.state["hopeless"] = True
            ctx.session.state["hopeless_reason"] = (
                f"Too many errors ({error_count} compile, "
                f"{missing_count} missing symbols)"
            )
            # Escalate to stop the loop — no point retrying
            yield Event(
                author=self.name,
                actions=EventActions(escalate=True),
            )
            return

        # G3: Structured build feedback for next retry
        # Non-retryable categories → escalate
        if category in ("NETWORK_ERROR", "PRE_EXISTING"):
            ctx.session.state["non_retryable"] = True
            ctx.session.state["non_retryable_reason"] = (
                classification.get("description", category)
            )
            yield Event(
                author=self.name,
                actions=EventActions(escalate=True),
            )
            return

        # Retryable: inject feedback for next attempt
        feedback_lines = [
            f"PREVIOUS ATTEMPT #{retry_count} FAILED",
            f"Failure category: {category}",
            f"Description: {classification.get('description', '')}",
            f"Build output (last 2000 chars):\n{output[-2000:]}",
            "",
            "Please analyze the error and try a different approach.",
        ]
        if category == "ENVIRONMENT_ERROR":
            feedback_lines.append(
                "This is an environment/config issue, not a code "
                "problem. Check build plugins, dependency repos, "
                "JDK version compatibility."
            )
        elif category == "PATCH_ERROR":
            feedback_lines.append(
                "The applied change caused a build error. Review "
                "the compilation output and adjust the fix."
            )
        ctx.session.state["build_feedback"] = "\n".join(feedback_lines)

        yield Event(author=self.name)


def _create_pr_opener() -> LlmAgent:
    """Agent that opens the remediation PR."""
    return LlmAgent(
        name="remediation_pr_opener",
        model=MODEL,
        instruction=(
            "Open a pull request with the remediation changes. "
            "Get the CVE details from session state (remediation_output) "
            "or from earlier conversation context.\n"
            "- Branch naming: rhtpa/remediate-<cve_id>-<timestamp>\n"
            "- Title: Remediate <cve_id>: <package> -> <fixed_version>\n"
            "- Stage files: pom.xml */pom.xml REMEDIATION.md\n"
            "- Base branch: " + BASE_BRANCH + "\n\n"
            "If the build did not pass (check state), report the failure "
            "instead of opening a PR."
        ),
        description="Opens a remediation pull request.",
        tools=[create_pull_request_tool],
        output_key="pr_result",
    )


def create_remediation_agent() -> SequentialAgent:
    """Factory: builds the SequentialAgent + LoopAgent remediation pipeline.

    Architecture: plan_agent -> retry_loop(checker -> retry_planner) -> pr_opener

    The retry loop runs up to 3 times. On build success, BuildResultChecker
    escalates to stop the loop. The PR opener only submits if build passed.
    """
    retry_loop = LoopAgent(
        name="remediation_retry_loop",
        sub_agents=[
            BuildResultChecker(name="build_result_checker"),
            _create_plan_agent("remediation_retry_planner"),
        ],
        max_iterations=3,
    )

    return SequentialAgent(
        name="remediation",
        description=(
            "Remediates a Maven dependency vulnerability: reads pom.xml, "
            "applies the fix via OpenCode, verifies with Maven (up to 3 "
            "retries), and opens a pull request."
        ),
        sub_agents=[
            _create_plan_agent("initial_remediation_planner"),
            retry_loop,
            _create_pr_opener(),
        ],
    )
