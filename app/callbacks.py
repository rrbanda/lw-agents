"""Shared callbacks for structured result extraction.

The ADK agents return natural language. Downstream consumers (Tekton tasks)
need structured fields. These after_agent_callbacks parse the agent's output
and write structured results to session state, which the API response exposes.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Default structured_result fields — set early so even if the pipeline
# errors partway through, Tekton always gets a valid response.
_STRUCTURED_RESULT_DEFAULTS = {
    "SELECTED": "0",
    "CVE_ID": "",
    "PACKAGE": "",
    "CURRENT_VERSION": "",
    "FIXED_VERSION": "",
    "JUSTIFICATION": "",
    "PR_URL": "",
    "COUNT": "0",
    "TESTS_ADDED": "0",
    "ISSUES_CREATED": "0",
    "CHANGED": "0",
}


async def init_structured_result(callback_context) -> None:
    """Set structured_result defaults BEFORE the agent runs.

    This is the coordinator's before_agent_callback. It ensures
    structured_result is always in session state, even if a sub-agent
    crashes or the pipeline errors partway through.
    """
    state = callback_context.state
    if not state.get("structured_result"):
        state["structured_result"] = dict(_STRUCTURED_RESULT_DEFAULTS)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first valid JSON object from text, supporting nested braces.

    Handles markdown code fences (```json ... ```), nested objects, and
    text before/after the JSON. Returns the parsed dict, or None.
    """
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start : i + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    # Try next { after this failed block
                    next_start = text.find("{", i + 1)
                    if next_start == -1:
                        return None
                    start = next_start
                    depth = 0
                    continue
    return None


async def extract_structured_results(callback_context) -> None:
    """Parse the agent's output into a structured result dict in session state.

    Looks for the selection_result, analysis_result, remediation_result, or
    test_generation_result output_key, then extracts the 6-field decision
    contract (SELECTED, CVE_ID, PACKAGE, CURRENT_VERSION, FIXED_VERSION,
    JUSTIFICATION) plus PR_URL and COUNT.

    The Tekton call-ssc-agent task reads state["structured_result"] from the
    API response to populate Tekton results.
    """
    state = callback_context.state

    # If a sub-agent's fail-closed callback already set structured_result
    # with SELECTED=1 (i.e., a real result, not just defaults), keep it
    existing = state.get("structured_result", {})
    if existing and existing.get("SELECTED") == "1":
        return
    if existing and existing.get("CHANGED") == "1":
        return

    # Start from defaults (may already be set by init_structured_result)
    structured: dict[str, Any] = (
        dict(existing)
        if existing
        else {
            "SELECTED": "0",
            "CVE_ID": "",
            "PACKAGE": "",
            "CURRENT_VERSION": "",
            "FIXED_VERSION": "",
            "JUSTIFICATION": "",
            "PR_URL": "",
            "COUNT": "0",
            "TESTS_ADDED": "0",
            "ISSUES_CREATED": "0",
            "CHANGED": "0",
        }
    )

    # Collect all agent output from known output_keys
    output_text = ""
    for key in (
        "selection_result",
        "analysis_result",
        "remediation_result",
        "remediation_output",
        "test_generation_result",
        "test_output",
        "pr_result",
    ):
        val = state.get(key)
        if val:
            output_text += str(val) + "\n"

    if not output_text.strip():
        state["structured_result"] = structured
        return

    # Try to find JSON in the output (supports nested objects)
    parsed = _extract_json_object(output_text)
    if parsed:
        for key in structured:
            lower_key = key.lower()
            for pkey, pval in parsed.items():
                if pkey.lower() == lower_key:
                    structured[key] = str(pval)
                    break

    # Extract fields from natural language if JSON parsing didn't find them
    text_lower = output_text.lower()

    if structured["SELECTED"] == "0":
        if "selected: true" in text_lower or "selected=true" in text_lower:
            structured["SELECTED"] = "1"
        elif "selected: false" in text_lower or "selected=false" in text_lower:
            structured["SELECTED"] = "0"

    for field, patterns in {
        "CVE_ID": [r"CVE-\d{4}-\d+"],
        "PACKAGE": [r"[a-z][a-z0-9._-]+:[a-z][a-z0-9._-]+"],
        "PR_URL": [r"https?://\S+(?:merge_requests|pull)/\d+"],
    }.items():
        if not structured[field]:
            for pattern in patterns:
                match = re.search(pattern, output_text, re.I)
                if match:
                    structured[field] = match.group(0)
                    break

    # Version extraction (look for version-like strings near field names)
    for field in ("CURRENT_VERSION", "FIXED_VERSION"):
        if not structured[field]:
            label = field.replace("_", " ").lower()
            match = re.search(
                rf"{label}[:\s]+[\"']?(\d+\.\d+[\w.-]*)",
                output_text,
                re.I,
            )
            if match:
                structured[field] = match.group(1)

    # Count extraction
    for field in ("COUNT", "TESTS_ADDED", "ISSUES_CREATED"):
        if structured[field] == "0":
            label = field.replace("_", " ").lower()
            match = re.search(rf"{label}[:\s]+(\d+)", output_text, re.I)
            if match:
                structured[field] = match.group(1)

    # CHANGED detection for remediation flow
    if structured.get("CHANGED", "0") == "0":
        rem_output = str(state.get("remediation_output", "")).lower()
        post_gate = state.get("post_gate_result", {})

        # Check if build succeeded
        build_succeeded = (
            state.get("build_passed")
            or "build success" in rem_output
            or "successfully" in rem_output
            or "fix applied" in rem_output
            or "remediation complete" in rem_output
            or "version updated" in rem_output
            or "dependency updated" in rem_output
            or "file changed" in rem_output
        )

        # Check if there's actually a diff (post_gate wasn't skipped)
        has_diff = post_gate and not post_gate.get("skipped", False)

        # Check if PR was created, attempted, or branch was pushed
        pr_text = str(state.get("pr_result", "")).lower()
        rem_text_full = str(state.get("remediation_output", "")).lower()
        pr_created = (
            "created" in pr_text
            or "merge_request" in pr_text
            or "pull" in pr_text
            or "open a pull request" in pr_text
            or "git push" in rem_text_full
            or "pushed" in rem_text_full
        )

        if build_succeeded and (has_diff or pr_created):
            structured["CHANGED"] = "1"
        elif build_succeeded:
            structured["CHANGED"] = "1"

    # TESTS_ADDED detection for test-generation flow
    if structured.get("TESTS_ADDED", "0") == "0":
        test_output = str(state.get("test_output", "")).lower()
        if any(
            kw in test_output
            for kw in (
                "tests generated",
                "test created",
                "test generated",
                "tests pass",
                "grade: pass",
                "git push",
                "pushed",
                "file changed",
                "build success",
            )
        ):
            structured["TESTS_ADDED"] = "1"

    state["structured_result"] = structured
