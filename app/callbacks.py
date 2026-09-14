"""Shared callbacks for structured result extraction.

The ADK agents return natural language. Downstream consumers (Tekton tasks)
need structured fields. These after_agent_callbacks parse the agent's output
and write structured results to session state, which the API response exposes.
"""

from __future__ import annotations

import json
import re
from typing import Any


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

    # If a sub-agent's fail-closed callback already set structured_result, keep it
    if state.get("structured_result"):
        return

    structured: dict[str, Any] = {
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
    }

    # Collect all agent output from known output_keys
    output_text = ""
    for key in ("selection_result", "analysis_result", "remediation_result",
                "remediation_output", "test_generation_result", "test_output",
                "pr_result"):
        val = state.get(key)
        if val:
            output_text += str(val) + "\n"

    if not output_text.strip():
        state["structured_result"] = structured
        return

    # Try to find JSON in the output
    json_match = re.search(r"\{[^{}]*\}", output_text, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                for key in structured:
                    lower_key = key.lower()
                    for pkey, pval in parsed.items():
                        if pkey.lower() == lower_key:
                            structured[key] = str(pval)
                            break
        except json.JSONDecodeError:
            pass

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
                output_text, re.I,
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

    state["structured_result"] = structured
