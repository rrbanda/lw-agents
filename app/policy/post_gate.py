"""Post-gate: verify the agent's output after it runs.

Inspired by VVAH's harness_amend() + post_gate pattern — replaces the
agent's self-report with evidence from git diff, and rejects diffs
containing forbidden patterns.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate a security suppression — never allow in a fix
FORBIDDEN_PATTERNS = [
    (r"#\s*nosec", "nosec comment (suppresses security linter)"),
    (r"//\s*noqa", "noqa comment (suppresses linter)"),
    (r"@SuppressWarnings", "SuppressWarnings annotation"),
    (r"verify\s*=\s*False", "TLS verification disabled"),
    (r"rejectUnauthorized:\s*false", "TLS rejection disabled"),
    (r"try:\s*\n\s*.*\n\s*except.*:\s*pass", "bare except-pass (swallows errors)"),
    (r"@PermitAll", "PermitAll annotation (removes auth)"),
]

MAX_DIFF_LINES = 100
MAX_FILES_TOUCHED = 5
ALLOWED_PATHSPECS = {"pom.xml", "REMEDIATION.md"}


def validate_diff(diff_content: str, changed_files: list[str]) -> dict[str, Any]:
    """Validate the git diff produced by the remediation agent.

    Returns {valid: bool, errors: list[str], warnings: list[str]}.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not diff_content and not changed_files:
        errors.append("No changes detected — remediation produced no diff")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # Check forbidden patterns in the diff
    for pattern, description in FORBIDDEN_PATTERNS:
        if re.search(pattern, diff_content, re.MULTILINE):
            errors.append(f"Forbidden pattern in diff: {description}")

    # Check file count
    if len(changed_files) > MAX_FILES_TOUCHED:
        errors.append(
            f"Too many files changed ({len(changed_files)} > {MAX_FILES_TOUCHED})"
        )

    # Check allowed pathspecs (only pom.xml variants and REMEDIATION.md)
    for f in changed_files:
        basename = f.split("/")[-1] if "/" in f else f
        if basename not in ALLOWED_PATHSPECS:
            warnings.append(f"Unexpected file changed: {f} (expected only {ALLOWED_PATHSPECS})")

    # Check diff size
    diff_lines = diff_content.count("\n")
    if diff_lines > MAX_DIFF_LINES:
        warnings.append(
            f"Large diff ({diff_lines} lines > {MAX_DIFF_LINES} max) — review carefully"
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "diff_lines": diff_lines,
        "files_touched": len(changed_files),
    }


async def post_gate_callback(callback_context) -> None:
    """ADK after_agent_callback — validate remediation output.

    Reads the diff proof from state (written by diff_proof tools)
    and validates it against policy rules.
    """
    state = callback_context.state
    diff_content = state.get("diff_content", "")
    changed_files = state.get("changed_files", [])

    if not diff_content and not changed_files:
        state["post_gate_result"] = {"valid": True, "skipped": True,
                                      "reason": "No diff to validate"}
        return

    result = validate_diff(diff_content, changed_files)
    state["post_gate_result"] = result

    if not result["valid"]:
        state["post_gate_rejected"] = True
        state["post_gate_reason"] = "; ".join(result["errors"])
