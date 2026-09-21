"""Output redaction plugin — masks secrets in tool results before model context.

Inspired by VVAH's 3-layer redaction middleware (shape regex + credential
key masking + known-value replacement). Attached at the Runner level to
guard ALL agents and sub-agents.
"""

from __future__ import annotations

import re
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin

# Shape-based patterns (detect by format, not by key name)
SHAPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # GitHub tokens
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}"), "[GITHUB_TOKEN]"),
    # GitLab tokens
    (re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"), "[GITLAB_TOKEN]"),
    # Anthropic API keys (must precede generic sk- pattern)
    (re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"), "[ANTHROPIC_KEY]"),
    # OpenAI API keys
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[API_KEY]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=\-]{20,}"), "[BEARER_TOKEN]"),
    # PEM private keys
    (
        re.compile(
            r"-----BEGIN\s+\w+\s+PRIVATE\s+KEY-----[\s\S]*?-----END\s+\w+\s+PRIVATE\s+KEY-----"
        ),
        "[PRIVATE_KEY]",
    ),
    # JWTs (header.payload.signature)
    (re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[JWT_TOKEN]"),
    # Basic auth
    (re.compile(r"Basic\s+[A-Za-z0-9+/=]{20,}"), "[BASIC_AUTH]"),
    # Generic hex secrets (40+ chars, likely SHA/tokens)
    (
        re.compile(r"(?:token|secret|password|apikey|api_key)\s*[=:]\s*['\"]?[A-Fa-f0-9]{40,}"),
        "[REDACTED_SECRET]",
    ),
]

# Credential key names — if a dict key contains these, mask the value
CREDENTIAL_KEYS = frozenset(
    {
        "token",
        "secret",
        "password",
        "apikey",
        "api_key",
        "auth_token",
        "authorization",
        "cookie",
        "session_id",
        "sessionid",
        "credential",
        "private_key",
        "access_token",
        "refresh_token",
        "client_secret",
        # L7.3 — Additional credential keys for CVE remediation tools
        "nvd_api_key",
        "bugzilla_api_key",
        "maven_repo_password",
        "nexus_password",
        "quay_token",
        "pulp_password",
        "github_token",
        "gitlab_token",
        "gemini_api_key",
        "maas_api_key",
    }
)


def redact_text(text: str) -> str:
    """Apply shape-based redaction to a string."""
    for pattern, replacement in SHAPE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Redact secrets in a dict — both shape-based and key-name-based."""
    result = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(cred in key_lower for cred in CREDENTIAL_KEYS):
            result[key] = "[REDACTED]"
        elif isinstance(value, str):
            result[key] = redact_text(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(v)
                if isinstance(v, dict)
                else redact_text(v)
                if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result


class RedactionPlugin(BasePlugin):
    """Runner-level plugin that redacts secrets from tool results.

    Applied BEFORE model context, so the LLM never sees raw credentials.
    Does NOT redact tool inputs (the agent needs to send auth to tools).
    """

    def __init__(self):
        super().__init__(name="redaction_plugin")

    async def after_tool_callback(
        self,
        *,
        callback_context=None,
        invocation_context=None,
        tool=None,
        args=None,
        tool_context=None,
        tool_response=None,
        **kwargs,
    ):
        if tool_response is None:
            return None
        if isinstance(tool_response, dict):
            return redact_dict(tool_response)
        if isinstance(tool_response, str):
            return redact_text(tool_response)
        return None
