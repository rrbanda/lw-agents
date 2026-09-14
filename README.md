# lw-agents

Agents-and-skills-first CVE remediation and test generation system built on
[Google ADK](https://adk.dev/) (Agent Development Kit).

## Architecture

Four specialist agents behind a coordinator, deployed as a service that Tekton
CI/CD pipelines call via HTTP API:

| Agent | ADK Pattern | What it does |
|---|---|---|
| **CVE Selection** | `LlmAgent` + `SkillToolset` | Loads the `cve-triage` skill, explores must-fix CVEs one-by-one via tools, selects the best one |
| **CVE Analysis** | `LlmAgent` + `SkillToolset` | Loads `cve-analysis` skill, iterates all CVEs, creates SCM issues for fixable ones |
| **Remediation** | `Workflow` graph | Reads pom.xml, applies fix via OpenCode, verifies Maven build, opens PR (with retry loop) |
| **Test Generation** | `SequentialAgent` + `LoopAgent` | Generates JUnit tests via OpenCode, iterates until they pass, opens PR |

## Why a Service, Not a Pipeline Step?

AI agents in CI/CD can run two ways:

| | Agent-in-the-Pod | Agent-as-a-Service |
|---|---|---|
| **How it works** | Agent runs inside the CI runner (like GitHub Copilot Coding Agent) | Agent runs as a long-lived service; CI tasks call it via HTTP |
| **Used by** | GitHub Copilot, SWE-agent, OpenHands | This project |
| **Infra complexity** | Lower — no extra service | Higher — deploy + manage the service |
| **Testing** | Must run inside pipeline | `make dev` + `make eval` locally |

We chose the **service pattern** because:
- **Eval-driven development** — `agents-cli eval` runs against the live service; no pipeline needed to test agent behavior
- **Skill hot-reload** — update a SKILL.md, agent picks it up without rebuilding a container image
- **Multi-pipeline reuse** — one service handles all four Tekton pipelines (selection, analysis, remediation, test-gen)
- **Observability** — continuous traces from a long-lived service vs scattered logs from ephemeral pods

See [ADR-004](docs/adr/004-tekton-calls-agent-via-api.md) for the full decision record including trade-offs.

## Quick Start

```bash
# Install
uv sync

# Set up credentials
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# Run the agent server
make dev
# -> http://localhost:8000

# Or use the ADK web playground
make playground

# Smoke test
make run PROMPT="Select the best CVE to remediate. Workspace: /tmp/test"

# Run evaluations
make eval
```

## Project Structure

```
lw-agents/
  app/
    agent.py              # Root coordinator + App (ADK entry point)
    agents/
      cve_selection.py    # LlmAgent + SkillToolset + CVE tools
      cve_analysis.py     # LlmAgent + SkillToolset + CVE + SCM tools
      remediation.py      # Workflow graph (read -> edit -> build -> PR)
      test_generation.py  # SequentialAgent + LoopAgent
    tools/
      cve_tools.py        # CVE exploration FunctionTools
      scm_tools.py        # GitLab/GitHub issue and PR tools
    plugins/
      safety.py           # LLM-as-judge BasePlugin
  skills/
    cve-triage/           # SKILL.md + references/
    cve-analysis/         # SKILL.md + references/
    maven-remediation/    # SKILL.md + references/
    junit-test-generation/
    scm-conventions/
  tests/
    eval/                 # Eval datasets + config
    test_runnability.py   # Smoke test
  deployment/
    tekton/               # Thin API-caller task for Tekton pipelines
  Dockerfile              # Container image for OpenShift deployment
```

## Skills

Skills are loaded dynamically via ADK's `SkillToolset`. The agent calls
`load_skill("cve-triage")` during its reasoning loop to get the methodology,
then follows the skill's process step-by-step using tools.

Each skill directory contains:
- `SKILL.md` — YAML frontmatter + methodology instructions
- `references/` — detailed docs the agent can load via `load_skill_resource`

## Tekton Integration

Tekton pipeline tasks call this agent service via HTTP API. The
`deployment/tekton/call-agent-task.yaml` is a thin (~30 line) curl-based
task that replaces the current 430+ line inline Python scripts.

## Deployment

```bash
# Build container
podman build -t quay.io/<org>/lw-agents:v1.0.0 .

# Deploy on OpenShift
oc apply -f deployment/tekton/call-agent-task.yaml
```

## Evaluation

```bash
# Run the full eval suite
make eval

# Or step by step
make eval-generate  # Run agents over eval datasets
make eval-grade     # Grade the traces
```
