# lw-agents

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Google ADK](https://img.shields.io/badge/Google_ADK-2.0-orange.svg)](https://adk.dev/)
[![Tests](https://img.shields.io/badge/Tests-64_passing-brightgreen.svg)](#testing)

AI-accelerated CVE remediation and test generation for software supply chain
security, built on [Google ADK](https://adk.dev/) and deployable on
[Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai).

---

## What is Lightwell?

When Anthropic unveiled Project Glasswing and its Claude Mythos model, it proved
that frontier AI could autonomously discover decades-old zero-day flaws and
weaponize them faster than any human team. Time To Exploit (TTE) collapsed to
zero. Manual patch testing became a relic.

**Lightwell** is IBM and Red Hat's response: AI-accelerated engineering that
backports, validates, and deploys non-breaking open-source patches at machine
speed. This repository contains the **agent application** that powers that
remediation engine.

## How it works

Five specialist agents behind a coordinator, deployed as a service that CI/CD
pipelines call via HTTP API:

| Agent | ADK Pattern | What it does |
|---|---|---|
| **CVE Selection** | `LlmAgent` + `SkillToolset` | Loads the `cve-triage` skill, explores must-fix CVEs one-by-one via tools, selects the best one |
| **CVE Analysis** | `LlmAgent` + `SkillToolset` | Loads `cve-analysis` skill, iterates all CVEs, creates SCM issues for fixable ones |
| **Remediation** | `SequentialAgent` + `LoopAgent` | Reads pom.xml, applies fix via OpenCode, verifies Maven build (with retry loop), opens PR |
| **Test Generation** | `SequentialAgent` + `LoopAgent` | Generates JUnit tests via OpenCode, iterates until they pass, opens PR |
| **Fix Validation** | `SequentialAgent` + `BaseAgent` | Two adversarial personas (architect + pentester) evaluate fixes with deterministic weighted scoring |

## Technology stack

| Layer | What provides it |
|---|---|
| **Agent harness** | [Google ADK 2.0](https://adk.dev/) -- core loop, tool dispatch, state, context, plugins, MCP, skills |
| **Agent platform** | [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai) -- EvalHub, MLflow, Tekton pipelines, OpenShift deployment |
| **Model serving** | [Gemini API](https://ai.google.dev/), [Red Hat MaaS](https://github.com/rrbanda/rh-maas-litellm) (OpenAI-compatible Gemini proxy), or [vLLM](https://github.com/vllm-project/vllm) self-hosted |
| **Agent application** | This repo -- CVE tools, remediation skills, policy gates, scoring, multi-persona validation |

## Quick start

```bash
# Clone
git clone https://github.com/redhat-lightwell/lw-agents.git
cd lw-agents

# Install
uv sync

# Set up credentials
cp .env.example .env
# Edit .env -- set GEMINI_API_KEY (or MAAS_BASE_URL + MAAS_API_KEY)

# Run the agent server
make dev
# -> http://localhost:8000

# Or use the ADK web playground
make playground
```

## Model serving options

lw-agents supports three model serving paths. Set the appropriate env vars in `.env`:

| Path | Env vars | Install |
|---|---|---|
| **Gemini API** (simplest, local dev) | `GEMINI_API_KEY` | `uv sync` |
| **Red Hat MaaS** (RHOAI clusters) | `MAAS_BASE_URL` + `MAAS_API_KEY` | `uv sync --extra maas` |
| **vLLM** (self-hosted) | Model endpoint URL via LiteLLM config | `uv sync` |

The MaaS integration uses [rh-maas-litellm](https://github.com/rrbanda/rh-maas-litellm)
to handle tools/response_format conflicts and PDF routing automatically.

## Testing

No Tekton pipelines or cluster required. Just an LLM.

```bash
# Unit tests (no LLM needed, 64 tests)
make test

# Lint
make lint

# Smoke test (needs LLM)
make run PROMPT="Select the best CVE to remediate. Workspace: /tmp/test"

# Full eval suite (38 cases across 6 agents, needs LLM + make dev running)
make eval
```

## Project structure

```
lw-agents/
  app/
    agent.py              # Root coordinator + App (ADK entry point)
    config.py             # Shared config: MODEL, WORKSPACE_PATH, MaaS detection
    tracing.py            # MLflow tracing bootstrap (OTel + LiteLLM autolog)
    callbacks.py          # Structured result extraction for Tekton
    agents/               # 5 specialist agents
    tools/                # CVE exploration + SCM issue/PR tools
    plugins/              # Safety (LLM-as-judge) + Redaction (secret masking)
    policy/               # Pre-gate (validate input) + Post-gate (validate diff)
    scoring/              # Fail-closed CVE selection validation
    eval/                 # EvalHub + MLflow + CVE metrics integration
    models/               # Pydantic data contracts
  skills/                 # 7 ADK skills (SKILL.md + references/)
  tests/                  # Unit tests, eval datasets, behavioral tests
  deployment/
    tekton/               # Thin HTTP-caller tasks for Tekton pipelines
  docs/
    adr/                  # 11 Architecture Decision Records
    architecture.md       # System diagrams + deployment model
```

## Skills

Skills are loaded dynamically via ADK's `SkillToolset`. The agent calls
`load_skill("cve-triage")` during its reasoning loop to get the methodology,
then follows the skill's process step-by-step using tools.

| Skill | Used by | Purpose |
|---|---|---|
| `cve-triage` | CVE Selection | Methodology for selecting the best CVE |
| `cve-analysis` | CVE Analysis | Methodology for analyzing all CVEs + issue creation |
| `maven-remediation` | Remediation | How to apply Maven dependency bumps |
| `junit-test-generation` | Test Generation | How to generate JUnit 5 tests |
| `scm-conventions` | Multiple agents | Branch naming, PR format, issue templates |
| `validation-architect` | Fix Validation | Security architect review persona |
| `validation-pentester` | Fix Validation | Penetration tester review persona |

## Why a service, not a pipeline step?

We chose the **agent-as-a-service** pattern (see [ADR-004](docs/adr/004-tekton-calls-agent-via-api.md)):

- **Eval-driven development** -- `make eval` runs against the live service locally; no pipeline needed
- **Skill hot-reload** -- update a SKILL.md, agent picks it up without rebuilding a container
- **Multi-pipeline reuse** -- one service handles all five task types
- **Observability** -- continuous traces from a long-lived service vs scattered logs from ephemeral pods

## MLflow tracing

Full-stack observability powered by OpenTelemetry + MLflow on RHOAI.
Every LLM call, tool execution, and agent delegation is captured as a span.

```bash
# Run with tracing enabled
make dev-traced
```

Tracing is **opt-in** (no env var = no tracing) and **gracefully degrades**
(unreachable server = warning log, agents start normally).

See [ADR-011](docs/adr/011-mlflow-tracing.md).

## Deployment

```bash
# Build container
podman build -t quay.io/<org>/lw-agents:v1.0.0 .

# Deploy on OpenShift
oc apply -f deployment/tekton/call-agent-task.yaml
```

See [docs/architecture.md](docs/architecture.md) for the full deployment model.

## Architecture Decision Records

| ADR | Title |
|-----|-------|
| [001](docs/adr/001-agent-framework-selection.md) | Agent Framework Selection (Google ADK on OpenShift) |
| [002](docs/adr/002-agents-and-skills-first.md) | Agents-and-Skills-First Architecture |
| [003](docs/adr/003-opencode-as-coding-agent.md) | OpenCode as Coding Agent |
| [004](docs/adr/004-tekton-calls-agent-via-api.md) | Tekton Calls Agent via API |
| [005](docs/adr/005-orchestration-pattern-selection.md) | Orchestration Pattern Selection |
| [006](docs/adr/006-safety-at-runner-level.md) | Safety at Runner Level |
| [007](docs/adr/007-policy-gates.md) | Policy Gates Before and After the Agent |
| [008](docs/adr/008-multi-persona-validation.md) | Multi-Persona Fix Validation |
| [009](docs/adr/009-output-redaction.md) | Output Redaction at Runner Level |
| [010](docs/adr/010-evalhub-integration.md) | EvalHub Integration for Safety and Quality Gates |
| [011](docs/adr/011-mlflow-tracing.md) | MLflow Tracing via OpenTelemetry |

## Related projects

- [Google ADK](https://adk.dev/) -- the agent harness powering lw-agents
- [agentic-starter-kits](https://github.com/red-hat-data-services/agentic-starter-kits) -- Red Hat's production-ready agent templates for OpenShift
- [rh-maas-litellm](https://github.com/rrbanda/rh-maas-litellm) -- ADK LiteLLM adapter for Red Hat MaaS

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding conventions, and how to submit changes.

## License

[Apache License 2.0](LICENSE)
