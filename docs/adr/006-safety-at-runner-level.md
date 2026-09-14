# ADR-006: Safety at Runner Level

## Status
Accepted

## Context
The agent service handles security-sensitive operations (reading vulnerability
data, editing code, opening PRs). We need content safety guardrails that cover
all agents and sub-agents without per-agent safety code.

ADK offers two approaches:
- **Per-agent callbacks** — `before_model_callback` / `after_model_callback` on
  each agent. Must be added to every agent definition.
- **Runner-level plugins** — `BasePlugin` attached to the `App`/`Runner`. Wraps
  every agent and sub-agent underneath automatically.

## Decision
Use a **Runner-level `BasePlugin`** (LLM-as-judge pattern from the adk-samples
`safety-plugins` recipe). The plugin classifies user messages and model outputs
for harmful content using a separate LLM judge, and blocks unsafe content before
it reaches the model or is persisted to session state.

## Rationale
- Agent-agnostic — attach once at the Runner, guards all agents and sub-agents
- Session-poisoning defense — unsafe user prompts are overwritten before
  persistence, and the invocation is halted in `before_run_callback`
- The LLM judge runs in its own `InMemoryRunner` (decoupled from the protected
  agent), so a jailbreak on the main agent doesn't compromise the judge
- The pattern is proven in the adk-samples safety-plugins recipe with both
  LLM-as-judge and Model Armor variants

## Consequences
- Every model call incurs an additional LLM call for safety classification
  (latency + cost)
- The safety judge model should be fast and cheap (e.g. gemini-2.5-flash)
- The judge instruction must be tuned for the domain (security remediation
  is legitimate; jailbreak attempts are not)
- `before_tool_callback` and `after_tool_callback` hooks are not yet
  implemented — only user messages and model output are classified. Extend
  as needed for tool-call/tool-output filtering.
