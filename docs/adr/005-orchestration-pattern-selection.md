# ADR-005: Orchestration Pattern Selection

## Status
Accepted

## Context
ADK offers multiple orchestration patterns. Each of our four agent tasks has
different characteristics:

| Task | Characteristics |
|------|----------------|
| CVE Selection | Tool-driven reasoning, explore data incrementally, single decision |
| CVE Analysis | Same as selection but iterates all CVEs, creates issues |
| Remediation | Deterministic steps with conditional branching (build pass/fail) |
| Test Generation | Iterative refinement (generate -> test -> fix loop) |

## Decision

| Agent | ADK Pattern | Source Recipe |
|-------|-------------|--------------|
| CVE Selection | `LlmAgent` + `SkillToolset` + FunctionTools | skills-tutorial |
| CVE Analysis | `LlmAgent` + `SkillToolset` + FunctionTools + SCM tools | skills-tutorial |
| Remediation | `Workflow` graph with `Event(route=...)` conditional routing | ambient-expense-agent |
| Test Generation | `SequentialAgent` + `LoopAgent` + `BaseAgent` escalation | deep-search |
| Root | Coordinator `LlmAgent` with `sub_agents` delegation | deep-search |

## Rationale
- **CVE Selection/Analysis**: Pure LLM reasoning with tool calling. The agent
  loads a skill, calls tools to explore CVEs, reasons about each one. No
  deterministic flow needed — the LLM decides the order.
- **Remediation**: Deterministic graph with conditional edges. Build
  success/failure determines the path (retry vs PR). HITL approval pause before
  PR creation via `RequestInput`. The `Workflow` API (ADK 2.0) provides this
  natively with `Event(route=...)`.
- **Test Generation**: Iterative refinement where the loop count is unknown.
  `LoopAgent` with a custom `BaseAgent` escalation checker (like deep-search's
  `EscalationChecker`) stops the loop when tests pass.
- **Root Coordinator**: LLM-driven delegation to specialists based on the
  request content. Sub-agents need `description` for the LLM to route correctly.

## Consequences
- Remediation uses `Workflow` (ADK 2.0) — requires `google-adk>=2.0.0`
- Test generation uses two separate test_writer instances (initial + loop fixer)
  to avoid ADK parent-conflict errors on shared sub-agents
- The root coordinator relies on LLM reasoning for delegation — incorrect routing
  is possible; eval should cover this
