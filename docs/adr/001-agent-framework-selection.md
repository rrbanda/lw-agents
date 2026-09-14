# ADR-001: Agent Framework Selection

## Status
Accepted

## Context
The original ssc-demo implementation embedded AI logic as inline Python/bash
scripts inside Tekton task YAML (430+ lines per task). We need a proper agent
framework that provides: agent orchestration loops, tool calling, skill
management, evaluation, and a built-in HTTP server.

We evaluated:
- **Google ADK** — agent loops, SkillToolset, Workflow/SequentialAgent/LoopAgent,
  ExecuteBashTool, eval framework, built-in adk api_server
- **Lightweight stack** (litellm + Pydantic AI + FastAPI + promptfoo) — minimal
  deps, full control, no lock-in
- **LangGraph** — mature agent framework, state management, streaming

The target deployment platform is **OpenShift with Tekton** (not GCP).

## Decision
Use **Google ADK** as the agent framework, deployed on OpenShift. Use ADK's
agent loop, tool system, SkillToolset, eval framework, and built-in server.
Ignore GCP-specific deployment features (Agent Runtime, Vertex AI sessions,
Memory Bank, Cloud Trace).

## Rationale
- ADK provides the richest agent orchestration (Workflow graphs, LoopAgent,
  SequentialAgent) compared to the alternatives
- Native SkillToolset with progressive disclosure (L1 metadata -> L2
  instructions -> L3 resources) matches our skills-first architecture
- Built-in eval framework (agents-cli eval) with LLM-as-judge metrics
- ExecuteBashTool with BashToolPolicy provides security-constrained command
  execution for OpenCode and Maven
- adk api_server eliminates the need for custom FastAPI code
- The adk-samples repository provides production-tested patterns to follow

## Consequences
- GCP deployment features (Agent Runtime, Cloud Trace, Memory Bank) are unused
- Observability must use OpenTelemetry directly instead of Cloud Trace
- Session storage must use in-memory or a custom backend instead of Vertex AI
- The ADK dependency is heavier than a lightweight stack would be
