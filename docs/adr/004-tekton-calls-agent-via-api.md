# ADR-004: Tekton Calls Agent via API (Service Pattern)

## Status
Accepted

## Context
The original ssc-demo embedded 430+ lines of Python and 150+ lines of bash
directly inside Tekton task YAML as inline `script:` blocks. This made the AI
logic untestable, unlintable, and duplicated across tasks.

Two patterns exist for running AI agents in CI/CD:

### Pattern A: Agent-in-the-Pod (how GitHub does it)
The agent runs inside the CI runner as a step. GitHub Copilot Coding Agent
uses this pattern — it spins up an ephemeral Actions runner, the agent runs
inside it with direct filesystem access, edits code, runs tests, opens a PR,
and the runner is destroyed. SWE-agent and OpenHands also use this pattern.

**Pros:** Simpler infrastructure, direct filesystem access, no network
dependency, no service to deploy.
**Cons:** Cold start each run, no state between runs, can't share across
pipelines, harder to test independently, no persistent sessions.

### Pattern B: Agent-as-a-Service (what we chose)
The agent runs as a long-lived service. CI tasks are thin HTTP callers that
POST to the agent service and read the response.

**Pros:** Agent is independently testable and evaluatable, warm service = fast
calls, can serve multiple pipelines, version upgrades don't touch pipeline YAML,
ADK eval framework works natively, skill updates only require a service restart.
**Cons:** Extra infrastructure (Deployment + Service), workspace files must be
accessible (mounted or shipped), more complex deployment.

## Decision
**Pattern B: Agent-as-a-Service.** The ADK agent runs as a standalone OpenShift
Deployment/Service using `adk api_server`. Tekton tasks are thin HTTP callers
(~30 lines of curl/bash) that POST requests and read responses.

## Why not the GitHub pattern?
GitHub Copilot's agent-in-the-runner pattern works well for general-purpose
coding tasks (write code, run tests, open PR). Our use case has additional
requirements that benefit from a service:

1. **Eval-driven development.** ADK's `agents-cli eval` framework runs against
   a live agent server. The agent-in-pod pattern would require spinning up a
   full pipeline to test agent behavior. With a service, `make eval` runs
   locally in seconds.

2. **Skill updates without pipeline changes.** Skills are loaded from the
   filesystem at service startup via `load_skill_from_dir()`. Updating a skill
   requires a service restart (or redeployment) but no changes to pipeline YAML.
   In-pod agents would need a new container image for every skill edit.

3. **Multi-pipeline reuse.** The same agent service handles CVE selection,
   analysis, remediation, and test generation. Four different Tekton pipelines
   call the same endpoint. In-pod would duplicate the agent setup in each.

4. **Observability continuity.** A long-lived service emits continuous traces
   and metrics. In-pod agents produce scattered logs across ephemeral pods
   that are hard to aggregate.

5. **Session and memory potential.** While current tasks are one-shot, the
   service pattern enables future cross-session memory (e.g., "this CVE was
   already attempted and failed last week") without architectural changes.

## Trade-off acknowledged
The service pattern is more complex to deploy and requires workspace files to
be accessible to the agent. For teams with simpler needs (single pipeline,
no eval, no memory), the agent-in-pod pattern (like GitHub) would be
simpler. This is a deliberate choice of capability over simplicity.

## Consequences
- The agent service must be deployed as a separate OpenShift Deployment/Service
- Tekton tasks need network access to the agent service (in-cluster Service URL)
- Agent responses are natural language — structured field extraction from
  responses requires parsing (or a future structured API)
- Session management and state are handled by the agent service, not Tekton
- Workspace files must be accessible to the agent service (shared PVC or
  file upload API)
