---
title: Pipeline with agents
summary: Two ways to put agent tasks inside the pipeline. The pipeline owns the DAG. The agent does one bounded step.
---

The pipeline head is the same as [Pipeline only](04-pipeline-only.html): clone, build, SBOM, scan, policy gate. After the gate, an agent task does one of four jobs: select one CVE, analyze all CVEs and open issues, remediate one dependency, or generate tests. The pipeline decides the order. The agent does one step at a time.

Two variants exist. Both share the same shape and the same rules.

## Variant 1: Inline agent

The agent runs inside the Tekton pod. A Python container or a coding-agent container (Claude Code, aider) executes one prompt, writes one structured result, and exits. There is no persistent session.

### Four pipelines, four jobs

| Pipeline | What the agent does | Output |
| --- | --- | --- |
| CVE selection | Reads the must-fix set, selects exactly one CVE with the highest priority, and emits a six-field decision | `SELECTED`, `CVE_ID`, `PACKAGE`, `CURRENT_VERSION`, `FIXED_VERSION`, `JUSTIFICATION` |
| CVE analysis | Reads the must-fix set, produces a decision for every fixable CVE, and opens one issue per CVE in GitLab or GitHub | One issue per fixable CVE, each carrying the six-field decision in a marker |
| CVE remediation | Takes a decision as input parameters, changes the dependency version in the manifest, runs the build and tests, and opens a pull request | A pull request linked to the issue, with audit data |
| Test generation | Generates unit tests for the application, runs them, and opens a tests-only pull request | A tests-only pull request |

### The six-field contract

The selection and analysis pipelines produce these fields. The remediation pipeline consumes them.

| Field | Meaning |
| --- | --- |
| `SELECTED` | `1` if a CVE was selected, `0` otherwise |
| `CVE_ID` | The CVE identifier |
| `PACKAGE` | Maven coordinates (`groupId:artifactId`) |
| `CURRENT_VERSION` | The vulnerable version the application uses now |
| `FIXED_VERSION` | The concrete version to change to |
| `JUSTIFICATION` | Why this CVE was chosen |

### Human handoff

Selection emits the decision as pipeline results. A person reviews the decision, then starts the remediation pipeline with those values as parameters. This is a deliberate decoupling: a human stands between triage and action.

For the analysis pipeline, the handoff is an issue. Each issue carries the six-field decision in an HTML comment marker. A developer reviews the issue and comments `/remediate` to trigger the remediation pipeline. The trigger reads the fields from the issue body.

### Fail-closed

If the agent cannot apply the fix, or the build fails, or the tests fail, the result is `CHANGED=0`. The pipeline skips the pull request. No broken code is shipped. The logback 1.2 to 1.5 example in the demo shows this: the major version jump required an incompatible SLF4J version, the build failed, and the agent correctly returned `CHANGED=0`.

## Variant 2: Remote agent service

The pipeline head is the same. The agent task calls a remote service instead of running a model in-pod.

### What changes

| | Inline agent | Remote agent service |
| --- | --- | --- |
| Where the agent runs | Inside the Tekton pod | A separate service on a separate cluster |
| Session | Stateless. One prompt, one answer | Persistent. The service holds an SSE session, loads skills, retries builds |
| Communication | The task script runs the model directly | The task sends an HTTP request and reads an SSE stream |
| What the pipeline sees | The same structured result (`CHANGED=1/0`, six-field decision) | The same structured result |
| What the service does internally | Nothing. It is a single call | A coordinator delegates to specialist agents. Each specialist loads methodology from a skill file. The remediation agent retries up to three times with classified error feedback |

The pipeline still owns the DAG. The pipeline still gates downstream tasks on the result. The human handoff is the same. Fail-closed is the same.

The remote service adds multi-step reasoning, skill loading, and retry without changing the pipeline's contract. The pipeline does not know or care how the service reached the answer, only that the answer arrived in the expected shape.

### Two-cluster architecture

The pipeline cluster handles CI/CD with access to the image registry, Git, and the vulnerability analyzer. The agent service cluster handles AI workloads. Communication between them is HTTPS. This separation lets the agent service scale independently and serve multiple pipelines.

## Shared rules

Both variants follow the same rules.

- **One CVE at a time.** Each remediation changes exactly one dependency. Small, discrete changes reduce risk and qualify as standard changes.
- **Pull requests are never auto-merged.** Every change lands on a branch for human review. The developer merges after reviewing the diff, the build result, and the audit data.
- **Fail-closed.** Any error, build failure, or uncertainty results in `CHANGED=0`. The pipeline does not open a pull request for a failed fix.
- **No discovery.** The agent does not find new vulnerabilities. It reads the scanner's output.
- **No library patching.** The agent changes the application's dependency version. It does not patch library source code. That work belongs to the upstream maintainer or to a supplier like Lightwell.
- **Secrets are not committed.** Registry tokens, API keys, and SCM credentials are mounted as secrets, never baked into images or written to the pull request.
- **The agent is pluggable.** The AI provider (Anthropic, OpenAI-compatible, Bedrock, Vertex, IBM Granite via vLLM) and the coding agent (Claude Code, aider) are configuration. The task contract stays the same.

## What the developer sees

1. The analysis pipeline ran in the background. It created issues in the backlog, one per fixable CVE.
2. The developer opens an issue, sees the CVE details, the recommended fix version, and the severity.
3. The developer comments `/remediate`.
4. The remediation pipeline runs. If the fix works, a pull request appears, linked to the issue, with the diff and audit data.
5. The developer reviews the pull request and merges it into the existing path to production.

The developer did not research the advisory, did not hunt for the right version, and did not edit `pom.xml`. The developer approved the change. That approval is the human-in-the-loop step that the architecture preserves.
