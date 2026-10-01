"""OpenCode server integration — call OpenCode via its HTTP API.

Replaces the subprocess-based approach (execute_bash("opencode run ..."))
with direct HTTP calls to a persistent OpenCode server running as a
sidecar (opencode serve --port 4096).

Architecture:
    ADK test_writer → call_opencode_server(spec)
        → POST /api/session (create session with workspace)
        → POST /api/session/{id}/prompt (send test specification)
        → Returns: assistant response with created file paths

Benefits over subprocess:
    - No SSE timeout (HTTP tool call returns normally)
    - No cold boot (persistent server)
    - No double-LLM telephone game (single prompt → response)
    - Shared workspace via volume mount
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

OPENCODE_SERVER_URL = os.environ.get("OPENCODE_SERVER_URL", "http://opencode-server:4096")
OPENCODE_SERVER_PASSWORD = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
OPENCODE_SERVER_USERNAME = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")


def _opencode_headers() -> dict[str, str]:
    """Build request headers for the OpenCode server."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if OPENCODE_SERVER_PASSWORD:
        import base64

        creds = base64.b64encode(
            f"{OPENCODE_SERVER_USERNAME}:{OPENCODE_SERVER_PASSWORD}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {creds}"
    return headers


def _create_session(workspace: str) -> str | None:
    """Create an OpenCode session pointed at the workspace.

    Returns the session ID, or None on failure.
    """
    import httpx

    url = f"{OPENCODE_SERVER_URL}/api/session"
    headers = _opencode_headers()
    body = {"location": {"directory": workspace}}

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=30)
        if resp.status_code in (200, 201):
            data = resp.json()
            session_id = data.get("id", "")
            logger.info("opencode_session_created id=%s workspace=%s", session_id, workspace)
            return session_id
        logger.warning(
            "opencode_session_create_failed status=%d body=%s",
            resp.status_code,
            resp.text[:200],
        )
        return None
    except Exception as exc:
        logger.warning("opencode_session_create_error error=%s", exc)
        return None


def _send_prompt(session_id: str, prompt: str, timeout: float = 180) -> dict[str, Any]:
    """Send a prompt to an OpenCode session and wait for the response.

    Returns the assistant response as a dict with 'text' and 'files' keys.
    """
    import httpx

    url = f"{OPENCODE_SERVER_URL}/api/session/{session_id}/prompt"
    headers = _opencode_headers()
    body = {
        "parts": [{"type": "text", "text": prompt}],
    }

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
        if resp.status_code in (200, 201):
            data = resp.json()
            # Extract text from response parts
            text_parts = []
            parts = data.get("parts", [])
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
            response_text = "\n".join(text_parts)
            logger.info(
                "opencode_prompt_ok session=%s response_len=%d",
                session_id,
                len(response_text),
            )
            return {
                "status": "ok",
                "text": response_text,
                "raw": data,
            }
        logger.warning(
            "opencode_prompt_failed status=%d body=%s",
            resp.status_code,
            resp.text[:500],
        )
        return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout after {timeout}s"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def call_opencode_server(
    specification: str,
    workspace: str = "/tmp/workspace",
) -> dict[str, Any]:
    """Send a test specification to the OpenCode server and get back results.

    This is an ADK FunctionTool that the test_writer agent calls instead
    of execute_bash("opencode run ..."). The OpenCode server runs as a
    sidecar pod with access to the same workspace volume.

    Args:
        specification: The test specification text (CVE, CWE, class, method,
            attack, assertion, file path, strategy).
        workspace: Path to the workspace directory (shared volume).

    Returns:
        Dict with status, response text, and any files created.
    """
    # Check if the server is reachable
    server_url = OPENCODE_SERVER_URL
    if not server_url:
        return {"status": "error", "error": "OPENCODE_SERVER_URL not configured"}

    # Create a session
    session_id = _create_session(workspace)
    if not session_id:
        return {
            "status": "error",
            "error": f"Failed to create OpenCode session at {server_url}",
        }

    # Build the prompt from the specification
    prompt = (
        f"Create a JUnit 5 reproducer test based on this specification:\n\n"
        f"{specification}\n\n"
        f"Write the test file at the path specified in the spec. "
        f"Make sure it compiles with: mvn -B -q -DskipTests compile"
    )

    # Send to OpenCode server
    result = _send_prompt(session_id, prompt, timeout=180)

    if result.get("status") == "ok":
        return {
            "status": "ok",
            "session_id": session_id,
            "response": result.get("text", ""),
            "message": "OpenCode generated the test file. Check the workspace.",
        }

    return result


def is_opencode_server_available() -> bool:
    """Check if the OpenCode sidecar server is reachable.

    Returns True if the server responds to a health check.
    """
    import httpx

    try:
        resp = httpx.get(f"{OPENCODE_SERVER_URL}/api/session", timeout=5)
        return resp.status_code in (200, 401)  # 401 = auth required but server is up
    except Exception:
        return False
