# ADR-009: Output Redaction at Runner Level

## Status
Accepted

## Context
VVAH applies 3-layer redaction middleware (shape regex + credential key
masking + known-value replacement) to tool results before they re-enter
model context. This prevents secrets from leaking into LLM prompts.

lw-agents had no redaction. SCM tokens, API keys, and workspace secrets
could leak into model context via tool results (e.g., git config output,
file contents with hardcoded credentials).

## Decision
Add a RedactionPlugin (ADK BasePlugin) at the Runner level that masks
secrets in tool results via after_tool_callback:
- Shape-based: GitHub/GitLab tokens, API keys, JWTs, PEM keys, Bearer tokens
- Key-name-based: dict keys containing "token", "secret", "password", etc.

## Rationale
- Runner-level plugin covers all agents and sub-agents automatically
- after_tool_callback intercepts results before the model sees them
- Shape-based detection catches secrets the agent didn't expect to find
- Key-name detection catches structured credential fields
- Does NOT redact tool inputs (agent needs to send auth to external tools)
