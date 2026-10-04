---
title: Pipeline with agents
summary: The pipeline is one execution engine. It runs tasks in a declared order. Some tasks use agents. How the agent runs is a deployment choice.
---

The pipeline is a Tekton DAG that owns the order of work. It runs the same sequence whether agents are involved or not. When agents are added, they replace specific manual steps — triage, manifest editing, test generation — with agent tasks that produce structured results. The pipeline gates every downstream step on those results.

The `ai-*` tasks run a model inside the Tekton pod. The `lw-*` tasks call a remote ADK service over SSE. Both produce the same structured output. The pipeline does not care which one is behind the task. This is a deployment choice, not a different execution model.

## The CVE flow mapped to pipeline tasks

The deck's flow is: **Discover → Triage and Log → Remediate → Test and Validate → Deliver**. Each stage maps to pipeline tasks.

### Stage 1: Discover what is vulnerable

These tasks produce the inputs. No agent is involved.

| Task | What it does | Maps to |
| --- | --- | --- |
| `git-clone` | Pull the application source | Prerequisite |
| `verify-commit` | Check the commit signature (optional) | Provenance |
| `maven` (package) | Build the application | Prerequisite |
| `buildah-rhtap` | Build the container image and generate the SBOM | Discover |
| `upload-sbom-to-rhtpa` | Send the SBOM to the vulnerability analyzer | Discover |
| `rhtpa-vulnerability-analysis` | Get the vulnerability report: which CVEs affect this application | Discover |
| `rhtpa-remediation-report` | Get vendor fix-version recommendations (supplemental) | Discover |

Output: a vulnerability report with CVE IDs, severities, affected PURLs, and fix hints.

### Stage 2: Triage and log

The policy gate filters the report. Then an agent task triages the result.

| Task | Agent? | What it does | Maps to |
| --- | --- | --- | --- |
| `conforma-policy-check` | No | Apply policy to produce the must-fix set (e.g. critical and high only) | Triage |
| `ai-select-cve` / `lw-select-cve` | **Yes** | Choose exactly one CVE from the must-fix set. Emits a six-field decision | Triage |
| `ai-analyze-cves` / `lw-analyze-cves` | **Yes** | Produce a decision for every fixable CVE. Render one issue file per CVE | Log |
| `open-cve-issues` | No | Create one GitLab or GitHub issue per fixable CVE | Log |

The selection pipeline and the analysis pipeline share the same head (stage 1) but differ in the tail. Selection picks one CVE for immediate remediation. Analysis triages the full set and creates a backlog.

### The six-field contract

Selection and analysis produce these fields. Remediation consumes them.

| Field | Meaning |
| --- | --- |
| `SELECTED` | `1` if a CVE was selected, `0` otherwise |
| `CVE_ID` | The CVE identifier |
| `PACKAGE` | Maven coordinates (`groupId:artifactId`) |
| `CURRENT_VERSION` | The vulnerable version the application uses now |
| `FIXED_VERSION` | The concrete version to change to |
| `JUSTIFICATION` | Why this CVE was chosen |

### Human handoff

A person stands between triage and remediation. For the selection pipeline, the person reviews the decision and starts the remediation pipeline with those values as parameters. For the analysis pipeline, the person reviews an issue and comments `/remediate` to trigger remediation. This decoupling is deliberate.

### Stage 3: Remediate one CVE

The remediation pipeline takes the six-field decision as input. It does not scan or triage.

| Task | Agent? | What it does | Maps to |
| --- | --- | --- | --- |
| `git-clone` | No | Clone the source | Prerequisite |
| `ai-remediate-dependency` / `lw-remediate-dependency` | **Yes** | Edit the manifest to the fixed version, verify the build compiles. Emits `CHANGED=1` or `CHANGED=0` | Remediate |
| `maven` (re-run tests) | No | Run `mvn verify` on the remediated tree (gated on `CHANGED=1`) | Test |
| `open-pr-cve` | No | Commit, push a branch, create a PR/MR (gated on `CHANGED=1`) | Deliver handoff |

If the agent cannot apply the fix, or the build fails, the result is `CHANGED=0`. The pipeline skips the PR. No broken code is shipped.

### Stage 4: Test (optional pipeline)

The test generation pipeline runs independently. A developer comments `/generate-tests` on an issue.

| Task | Agent? | What it does | Maps to |
| --- | --- | --- | --- |
| `git-clone` | No | Clone the source | Prerequisite |
| `maven` (package) | No | Build the application | Prerequisite |
| `ai-generate-tests` / `lw-generate-tests` | **Yes** | Generate JUnit tests, run them. Emits `TESTS_ADDED` count | Test |
| `maven` (re-run) | No | Run all tests including generated ones (gated on `TESTS_ADDED > 0`) | Validate |
| `open-pr-tests` | No | Commit only tests to a branch, open a tests-only PR (gated on `TESTS_ADDED > 0`) | Deliver handoff |

### Stage 5: Deliver

The pipeline stops at the pull request. A developer reviews and merges. The merge goes into the organization's existing CI/CD path to production. The pipeline does not deploy, does not roll back, and does not claim production is clean.

## How the agent task runs — a deployment choice

| | In-pod (`ai-*` tasks) | Remote service (`lw-*` tasks) |
| --- | --- | --- |
| Where the model runs | Inside the Tekton pod. A Python or coding-agent container | A separate ADK service, possibly on a different cluster |
| Session | Stateless. One prompt, one structured answer | Persistent. SSE session with skills, retry, and multi-step reasoning |
| What the pipeline sees | The same structured result | The same structured result |
| When to use | Simpler setup. No service to deploy | Multi-step reasoning, skill loading, retry on build failure, and the ability to serve multiple pipelines |

The pipeline contract is the same either way: the task writes `SELECTED`, `CHANGED`, or `TESTS_ADDED` to Tekton results. Downstream tasks gate on those values.

## Rules

- **One CVE at a time.** Each remediation changes exactly one dependency. Small changes qualify as standard changes.
- **Pull requests are never auto-merged.** A developer reviews and merges.
- **Fail-closed.** Any error or build failure results in `CHANGED=0`. The pipeline does not open a PR for a failed fix.
- **No discovery.** The agent reads the scanner's output. It does not find new vulnerabilities.
- **No library patching.** The agent changes the application's dependency version. The library fix belongs to the upstream maintainer or to a supplier like Lightwell.
- **Secrets are not committed.** Tokens and keys are mounted, never in the diff.
- **The agent backend is pluggable.** Anthropic, OpenAI-compatible, Bedrock, Vertex, IBM Granite via vLLM. Claude Code or aider as the coding agent. Configuration, not code change.

## What the developer sees

1. The analysis pipeline ran in the background and created issues in the backlog, one per fixable CVE.
2. The developer opens an issue. It shows the CVE details, the recommended version, and the severity.
3. The developer comments `/remediate`.
4. The remediation pipeline runs. If the fix works, a pull request appears linked to the issue with the diff and audit data.
5. The developer reviews and merges into the existing path to production.

The developer did not research the advisory, did not hunt for the right version, and did not edit `pom.xml`. The developer approved the change.
