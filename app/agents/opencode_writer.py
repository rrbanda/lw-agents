"""OpenCode integration — coding agent for test generation and build fixing.

OpenCode's strengths:
  - Reads the full project (understands imports, packages, APIs)
  - Writes compilable code (resolves dependencies, correct syntax)
  - Fixes build errors iteratively (reads error, edits, retries)

Architecture:
  ADK Agent: Investigates CVE → builds a TEST SPECIFICATION (what to test)
  OpenCode: Receives the specification → generates the actual code

This avoids the telephone game: we pass WHAT to test (specification),
not HOW to test it (code). OpenCode generates the code from scratch
using its understanding of the project.

For build errors: OpenCode reads the error + project context and fixes.
"""

from __future__ import annotations

import os
import shutil

from google.adk.agents import LlmAgent

from app.config import MODEL, build_bash_tool


def is_opencode_available() -> bool:
    """Check if OpenCode should be used.

    Requires explicit opt-in via LW_USE_OPENCODE=true because
    OpenCode takes 60-90s and causes SSE timeouts in the web UI.
    Pipeline runner and Tekton set this automatically.
    """
    if os.environ.get("LW_USE_OPENCODE", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        return shutil.which("opencode") is not None
    return False


def create_opencode_test_generator(
    name: str = "opencode_test_gen",
) -> LlmAgent:
    """Create an OpenCode-backed test generation sub-agent.

    This agent receives a TEST SPECIFICATION from the parent
    (what to test, not code), and calls OpenCode to generate
    the actual test file using its project context awareness.

    The parent agent does CVE research and builds the spec.
    OpenCode does the coding — reading the project, finding
    classes, writing compilable tests.
    """
    bash_tool = build_bash_tool()

    return LlmAgent(
        name=name,
        model=MODEL,
        mode="single_turn",
        instruction=(
            "You are a bridge to OpenCode. You receive a TEST "
            "SPECIFICATION describing what to test, and you call "
            "OpenCode to generate the actual test code.\n\n"
            "IMPORTANT RULES:\n"
            "- Pass the SPECIFICATION to OpenCode, NOT generated code\n"
            "- Let OpenCode read the project and write the test\n"
            "- OpenCode understands imports, packages, APIs — trust it\n"
            "- After OpenCode finishes, verify the test compiles\n\n"
            "HOW TO CALL OPENCODE:\n"
            "Build a clear, specific instruction from the spec you "
            "received. Example:\n\n"
            '  execute_bash("cd /tmp/workspace && opencode run '
            "--auto "
            "'Create a JUnit 5 test file at "
            "src/test/java/com/example/Cve202429025ReproducerTest.java "
            "for CVE-2024-29025 in netty-codec-http. "
            "The vulnerability is in HttpObjectDecoder where oversized "
            "HTTP headers cause resource exhaustion (CWE-400). "
            "Write a test that sends headers exceeding 8192 bytes "
            "and asserts the decoder rejects or limits them. "
            "Use JUnit 5 assertions. Make sure it compiles and "
            "passes against the fixed version."
            "'\")\n\n"
            "AFTER OPENCODE FINISHES:\n"
            "1. Check the file exists:\n"
            '   execute_bash("cd /tmp/workspace && ls -la '
            'src/test/java/com/example/*Test.java")\n'
            "2. Verify it compiles:\n"
            '   execute_bash("cd /tmp/workspace && mvn -B -q '
            '-DskipTests compile")\n'
            "3. If compilation fails, call OpenCode again to fix:\n"
            '   execute_bash("cd /tmp/workspace && opencode run '
            "--auto 'Fix the compilation error in "
            "Cve202429025ReproducerTest.java: <error message>'"
            '")\n\n'
            "TIMING: OpenCode takes 60-90 seconds. This is normal. "
            "Do NOT re-run if it seems slow."
        ),
        description=(
            "Calls OpenCode to generate test code from a specification. "
            "OpenCode reads the project and writes compilable tests."
        ),
        tools=[bash_tool],
        output_key="coding_output",
    )


def create_opencode_fixer(
    name: str = "opencode_fixer",
) -> LlmAgent:
    """Create an OpenCode-backed build-error fixer sub-agent.

    Called ONLY when a build fails after tests are written.
    OpenCode reads the error + project context and fixes the code.
    """
    bash_tool = build_bash_tool()

    return LlmAgent(
        name=name,
        model=MODEL,
        mode="single_turn",
        instruction=(
            "You fix build errors using OpenCode. You are called "
            "ONLY when a build or test fails.\n\n"
            "1. Read the error from the context\n"
            "2. Call OpenCode to fix it:\n"
            '   execute_bash("cd /tmp/workspace && opencode run '
            "--auto "
            "'Fix this error: <key error lines>'\")\n"
            "3. Verify the fix compiles:\n"
            '   execute_bash("cd /tmp/workspace && mvn -B -q '
            '-DskipTests compile")\n'
            "4. Report whether it worked.\n\n"
            "Do NOT rewrite files from scratch. Only fix the error."
        ),
        description="Fixes build errors using OpenCode.",
        tools=[bash_tool],
        output_key="fix_output",
    )
