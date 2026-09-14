"""Pre-gate: validate the remediation request before the agent runs.

Inspired by VVAH's policy/decide.py — denied findings get guidance-only
verdicts with zero model spend. The agent never runs on invalid input.
"""

from __future__ import annotations

import re
from typing import Any

CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$", re.I)
MAVEN_COORD_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]+:[a-zA-Z][a-zA-Z0-9._-]+$")
VERSION_PATTERN = re.compile(r"\d")


def validate_cve_selection_request(
    workspace_path: str,
) -> dict[str, Any]:
    """Validate that the workspace has the required RHTPA report files."""
    from pathlib import Path

    ws = Path(workspace_path)
    errors = []

    must_fix = ws / "rhtpa" / "must-fix-cves.json"
    if not must_fix.exists():
        errors.append(f"must-fix-cves.json not found at {must_fix}")

    vuln = ws / "rhtpa" / "vulnerabilities.json"
    if not vuln.exists():
        errors.append(f"vulnerabilities.json not found at {vuln}")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_remediation_request(
    cve_id: str,
    package: str,
    current_version: str,
    fixed_version: str,
) -> dict[str, Any]:
    """Validate remediation params before the agent runs.

    Returns {valid: bool, errors: list[str]}. If not valid, the agent
    should not run — return a guidance-only response instead.
    """
    errors = []

    if not cve_id or not CVE_PATTERN.match(cve_id):
        errors.append(f"Invalid CVE ID: {cve_id!r}")

    if not package or not MAVEN_COORD_PATTERN.match(package):
        errors.append(f"Invalid Maven coordinates: {package!r} (expected groupId:artifactId)")

    if not fixed_version or not VERSION_PATTERN.search(fixed_version):
        errors.append(f"Invalid fixed version: {fixed_version!r} (must contain digits)")

    if not current_version or not VERSION_PATTERN.search(current_version):
        errors.append(f"Invalid current version: {current_version!r}")

    if current_version and fixed_version and current_version == fixed_version:
        errors.append(f"Current and fixed versions are identical: {current_version}")

    return {"valid": len(errors) == 0, "errors": errors}


async def pre_gate_callback(callback_context):
    """ADK before_agent_callback — validate request before agent runs.

    Returns a Content object to halt the agent when validation fails,
    achieving zero model spend on invalid input. Returns None to proceed.
    """
    from google.genai import types as genai_types

    state = callback_context.state

    cve_id = state.get("cve_id", "")
    package = state.get("package", "")
    current = state.get("current_version", "")
    fixed = state.get("fixed_version", "")

    if cve_id and package:
        result = validate_remediation_request(cve_id, package, current, fixed)
    elif cve_id or package or current or fixed:
        # Some but not all fields present — fail rather than skip
        result = validate_remediation_request(cve_id, package, current, fixed)
    else:
        result = {"valid": True, "errors": []}

    state["pre_gate_result"] = result
    if not result["valid"]:
        state["pre_gate_denied"] = True
        reason = "; ".join(result["errors"])
        state["pre_gate_reason"] = reason
        return genai_types.Content(
            role="model",
            parts=[genai_types.Part.from_text(
                text=f"Pre-gate validation failed: {reason}"
            )],
        )
    return None
