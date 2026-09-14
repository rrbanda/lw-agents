"""Fail-closed validation for CVE selection results.

Inspired by VVAH's scoring engine where every error path returns
INCONCLUSIVE. A selection is only honored if ALL fields pass validation.
"""

from __future__ import annotations

import re
from typing import Any

CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$", re.I)
VERSION_HAS_DIGIT = re.compile(r"\d")
MAVEN_COORD = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]+:[a-zA-Z][a-zA-Z0-9._-]+$")


def validate_selection(result: dict[str, Any]) -> dict[str, Any]:
    """Validate a CVE selection result. Fail-closed: any error -> SELECTED=0.

    Args:
        result: Dict with keys: selected, cve_id, package, current_version,
                fixed_version, justification.

    Returns:
        Validated result with selected="0" if any check fails, plus
        validation_errors list.
    """
    errors: list[str] = []
    selected = str(result.get("selected", "0")).strip()
    cve_id = str(result.get("cve_id", "")).strip()
    package = str(result.get("package", "")).strip()
    current = str(result.get("current_version", "")).strip()
    fixed = str(result.get("fixed_version", "")).strip()
    justification = str(result.get("justification", "")).strip()

    if selected not in ("1", "true", "True"):
        return {
            **result,
            "SELECTED": "0",
            "validation_errors": [],
            "validation_status": "not_selected",
        }

    # CVE ID must match pattern
    if not CVE_PATTERN.match(cve_id):
        errors.append(f"Invalid CVE ID: {cve_id!r}")

    # Package must be groupId:artifactId
    if not MAVEN_COORD.match(package):
        errors.append(f"Invalid package: {package!r}")

    # Versions must contain digits
    if not VERSION_HAS_DIGIT.search(fixed):
        errors.append(f"Fixed version has no digits: {fixed!r}")
    if not VERSION_HAS_DIGIT.search(current):
        errors.append(f"Current version has no digits: {current!r}")

    # Versions must not be identical
    if current and fixed and current == fixed:
        errors.append(f"Current and fixed versions identical: {current}")

    # Justification must not be empty
    if not justification:
        errors.append("Empty justification")

    # Placeholder detection (from original ssc-demo)
    for field_name, value in [
        ("package", package),
        ("fixed_version", fixed),
        ("current_version", current),
    ]:
        lower = value.lower()
        if lower in ("string", "null", "none", "n/a", ""):
            errors.append(f"{field_name} is a placeholder: {value!r}")

    if errors:
        return {
            "SELECTED": "0",
            "CVE_ID": "",
            "PACKAGE": "",
            "CURRENT_VERSION": "",
            "FIXED_VERSION": "",
            "JUSTIFICATION": f"Validation failed: {'; '.join(errors)}",
            "validation_errors": errors,
            "validation_status": "rejected",
        }

    return {
        "SELECTED": "1",
        "CVE_ID": cve_id,
        "PACKAGE": package,
        "CURRENT_VERSION": current,
        "FIXED_VERSION": fixed,
        "JUSTIFICATION": justification,
        "validation_errors": [],
        "validation_status": "accepted",
    }


async def fail_closed_selection_callback(callback_context) -> None:
    """ADK after_agent_callback for the CVE selection agent.

    Parses the agent's output (JSON, YAML-like key:value, or NL) into
    a structured result. Every error path sets SELECTED=0.
    """
    state = callback_context.state
    raw = state.get("selection_result", "")

    parsed: dict[str, Any] = {}
    if isinstance(raw, str):
        from app.callbacks import _extract_json_object

        # Try 1: JSON object
        parsed = _extract_json_object(raw) or {}

        # Try 2: YAML-like "key: value" lines (common agent output format)
        if not parsed:
            for line in raw.splitlines():
                line = line.strip()
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip().lower().replace(" ", "_")
                    value = value.strip()
                    if key in (
                        "selected",
                        "cve_id",
                        "package",
                        "current_version",
                        "fixed_version",
                        "justification",
                    ):
                        parsed[key] = value

        # Try 3: regex fallback for CVE ID and selected flag
        if not parsed.get("cve_id"):
            cve_match = re.search(r"CVE-\d{4}-\d+", raw, re.I)
            if cve_match:
                parsed["cve_id"] = cve_match.group(0)
        if "selected" not in parsed:
            parsed["selected"] = "1" if "selected: true" in raw.lower() else "0"

    validated = validate_selection(parsed)
    state["structured_result"] = validated
