# ADR-004: Tekton Calls Agent via API

## Status
Accepted

## Context
The original ssc-demo embedded 430+ lines of Python and 150+ lines of bash
directly inside Tekton task YAML as inline `script:` blocks. This made the AI
logic untestable, unlintable, and duplicated across tasks.

The question: should AI logic run inside Tekton task pods, or should Tekton call
an external agent service?

## Decision
**Agents run as a standalone ADK service.** Tekton tasks are thin HTTP callers
(~30 lines of curl/bash) that POST to the agent service and read the response.
The agent service runs ADK's built-in `adk api_server`.

## Rationale
- Decouples AI logic from CI/CD orchestration — agent service is independently
  deployable, testable, and observable
- Tekton tasks become trivial — no Python/bash AI logic in YAML
- The agent service can be tested locally via `make dev` or `make playground`
  without Tekton
- Eval can run against the agent service directly via `agents-cli eval`
- The agent service can serve multiple Tekton pipelines and other consumers
- Version upgrades to the agent don't require pipeline YAML changes

## Consequences
- The agent service must be deployed as a separate OpenShift Deployment/Service
- Tekton tasks need network access to the agent service (in-cluster Service URL)
- Agent responses are natural language — structured field extraction from
  responses requires parsing (or a future structured API)
- Session management and state are handled by the agent service, not Tekton
