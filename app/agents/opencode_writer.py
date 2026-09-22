"""OpenCode coding sub-agent — delegates file editing to OpenCode.

OpenCode is a CLI coding agent that edits files in a project directory.
It's called via `opencode run "instruction"` and takes 60-90 seconds.

This module provides a `single_turn` LlmAgent that:
1. Receives a coding task from its parent (test_generation or remediation)
2. Formulates the right OpenCode instruction
3. Calls `opencode run` via execute_bash
4. Verifies the result
5. Returns structured output

The sub-agent pattern avoids ADK's AFC timeout because the bash call
happens within the sub-agent's own turn, not as a tool-call within
the parent's turn.

When OpenCode is not available (not on PATH), the agent falls back
to direct file writing via tee/sed.
"""

from __future__ import annotations

import shutil

from google.adk.agents import LlmAgent

from app.config import MODEL, build_bash_tool


def is_opencode_available() -> bool:
    """Check if OpenCode should be used.

    OpenCode takes 60-90 seconds per call. This works fine in:
    - Pipeline runner (app/runner.py) — own process, no timeout
    - Tekton Tasks — 600s HTTP timeout

    But does NOT work in:
    - ADK web UI / playground — SSE connection times out at ~30s

    Use the LW_USE_OPENCODE env var to opt in explicitly.
    When not set, OpenCode is disabled to avoid timeouts in the
    default ADK web UI path.
    """
    import os

    # Explicit opt-in (set by runner.py and Tekton)
    if os.environ.get("LW_USE_OPENCODE", "").lower() in ("1", "true", "yes"):
        return shutil.which("opencode") is not None

    # Default: disabled (safe for web UI)
    return False


def create_opencode_writer(
    name: str = "opencode_writer",
) -> LlmAgent:
    """Create an OpenCode-backed coding sub-agent.

    This agent receives a coding instruction and executes it via
    OpenCode's `run` command. It's designed to be a `single_turn`
    sub-agent of test_generation or remediation.

    The bash_tool timeout (300s) accommodates OpenCode's 60-90s
    typical execution time.
    """
    bash_tool = build_bash_tool()
    has_opencode = is_opencode_available()

    if has_opencode:
        instruction = (
            "You are a coding agent that uses OpenCode to edit files. "
            "When given a coding task:\n\n"
            "1. Make sure you're in the right directory: "
            "cd /tmp/workspace\n\n"
            "2. Call OpenCode with a precise, specific instruction:\n"
            '   execute_bash("cd /tmp/workspace && opencode run '
            '\\"<specific instruction>\\"")\n\n'
            "Be VERY specific in the instruction. Examples:\n"
            '- "In pom.xml, change the version of logback-core '
            'from 1.2.12 to 1.5.18"\n'
            '- "Create a JUnit 5 test at src/test/java/com/example/'
            "FooTest.java that tests the withdraw method of "
            'FooService"\n'
            '- "Fix the compilation error: NoSuchMethodError in '
            'TransactionService"\n\n'
            "3. After OpenCode finishes, verify the result:\n"
            '   execute_bash("cd /tmp/workspace && cat <edited-file>'
            '")\n'
            '   execute_bash("cd /tmp/workspace && mvn -B -q '
            '-DskipTests compile")\n\n'
            "4. Report what was changed and whether it compiles.\n\n"
            "IMPORTANT: OpenCode takes 60-90 seconds. This is normal."
            " Wait for it to complete. Do NOT re-run if it seems slow."
        )
    else:
        instruction = (
            "You are a coding agent that writes files directly. "
            "OpenCode is not available, so write files using "
            "mkdir + tee:\n\n"
            "  cd /tmp/workspace && mkdir -p src/test/java/com/example\n"
            "  cd /tmp/workspace && tee src/test/java/com/example/"
            "FooTest.java << 'ENDFILE'\n"
            "  ... file contents ...\n"
            "  ENDFILE\n\n"
            "For edits to existing files, use sed:\n"
            "  cd /tmp/workspace && sed -i 's/old/new/' pom.xml\n\n"
            "After writing, verify:\n"
            "  cd /tmp/workspace && cat <file>\n"
            "  cd /tmp/workspace && mvn -B -q -DskipTests compile\n\n"
            "Report what was changed and whether it compiles."
        )

    return LlmAgent(
        name=name,
        model=MODEL,
        mode="single_turn",
        instruction=instruction,
        description=(
            "Coding sub-agent that edits project files. "
            + ("Uses OpenCode CLI." if has_opencode else "Uses sed/tee.")
        ),
        tools=[bash_tool],
        output_key="coding_output",
    )
