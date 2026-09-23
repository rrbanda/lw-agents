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

Two execution paths exist, each using the best-fit orchestration pattern:

### Path 1: Coordinator sub-agents (playground / interactive)

Used by the LLM coordinator in `app/agent.py` for playground and interactive
use. Agents are registered as `sub_agents` of the coordinator `LlmAgent`.

| Agent | ADK Pattern | Source Recipe |
|-------|-------------|--------------|
| CVE Selection | `LlmAgent` + `SkillToolset` + FunctionTools | skills-tutorial |
| CVE Analysis | `LlmAgent` + `SkillToolset` + FunctionTools + SCM tools | skills-tutorial |
| Remediation | `SequentialAgent` + `LoopAgent` + `BaseAgent` escalation | deep-search |
| Test Generation | `SequentialAgent` + `LoopAgent` + `BaseAgent` escalation | deep-search |
| Fix Validation | `SequentialAgent` + `BaseAgent` (deterministic scoring) | — |
| Root | Coordinator `LlmAgent` with `sub_agents` delegation | deep-search |

ADK's `Workflow` cannot be used as an `LlmAgent` sub-agent (it must be the
root of an `App`), so the coordinator path uses `SequentialAgent` + `LoopAgent`
for remediation and test generation.

### Path 2: Workflow graph (pipeline / CI/CD)

Used by `app/workflow.py` for deterministic pipeline execution. The `Workflow`
is the root agent of a separate `App` (`lw-agents-pipeline`). Tekton defaults
to this path.

| Agent | ADK Pattern |
|-------|-------------|
| CVE Selection | `LlmAgent` (single_turn node) |
| Remediation | `LlmAgent` (single_turn node) with conditional routing via `Event(route=...)` |
| Test Generation | `LlmAgent` (single_turn node) |
| Fix Validation | Two `LlmAgent` nodes + pure-Python scoring function |
| Pipeline | `Workflow` graph with `route_on_selection`, `route_on_build`, `route_on_retry` |

## Rationale
- **CVE Selection/Analysis**: Pure LLM reasoning with tool calling. The agent
  loads a skill, calls tools to explore CVEs, reasons about each one. No
  deterministic flow needed — the LLM decides the order.
- **Remediation (Workflow path)**: Deterministic graph with conditional edges.
  Build success/failure determines the path (retry vs PR). The `Workflow` API
  (ADK 2.0) provides this natively with `Event(route=...)`.
- **Remediation (coordinator path)**: `SequentialAgent` + `LoopAgent` achieves
  the same retry logic. `BuildResultChecker` (a `BaseAgent`, no LLM) classifies
  failures and escalates on success to exit the loop.
- **Test Generation**: Iterative refinement where the loop count is unknown.
  `LoopAgent` with a custom `BaseAgent` escalation checker (like deep-search's
  `EscalationChecker`) stops the loop when tests pass.
- **Root Coordinator**: LLM-driven delegation to specialists based on the
  request content. Sub-agents need `description` for the LLM to route correctly.

## Consequences
- Two execution paths must be kept in sync when agent logic changes
- The Workflow path (`lw-agents-pipeline`) is the production default for Tekton
- The coordinator path (`app`) is used for playground, interactive debugging,
  and ADK's built-in eval framework
- Test generation uses two separate test_writer instances (initial + loop fixer)
  to avoid ADK parent-conflict errors on shared sub-agents
- The root coordinator relies on LLM reasoning for delegation — incorrect routing
  is possible; eval should cover this
