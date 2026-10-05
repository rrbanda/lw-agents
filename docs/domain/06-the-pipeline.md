---
title: The pipeline
summary: One logical flow from scan to pull request, split at human handoff points. Five stages from the deck.
---

The pipeline is a Tekton DAG that runs the [CVE task flow](03-cve-tasks.html) as a declared sequence. It splits into separate pipeline runs at points where a person must review before the next stage starts. This split is the implementation. The logical flow is one.

## The five stages

:::tab Stage 1: Discover
These tasks run without any agent. They produce the must-fix list.

| Step | Task | What it does |
| --- | --- | --- |
| 1 | `git-clone` | Pull the application source |
| 2 | `verify-commit` (optional) | Check commit signature against signing infrastructure |
| 3 | `maven` (package) | Build the application |
| 4 | `buildah-rhtap` | Build the container image and generate the SBOM |
| 5 | `upload-sbom-to-rhtpa` | Send the SBOM to the vulnerability analyzer |
| 6 | `rhtpa-vulnerability-analysis` | Get the vulnerability report |
| 7 | `rhtpa-remediation-report` | Get vendor fix recommendations (supplemental) |
| 8 | `conforma-policy-check` | Filter to the must-fix set by severity or policy |
:::

:::tab Stage 2: Triage and log
An agent task triages the must-fix list and produces issues.

| Step | Task | Agent? | What it does |
| --- | --- | --- | --- |
| 9a | `ai-select-cve` / `lw-select-cve` | **Yes** | Choose exactly one CVE. Emit a six-field decision |
| 9b | `ai-analyze-cves` / `lw-analyze-cves` | **Yes** | Produce a decision for every fixable CVE. Render issue files |
| 10 | `open-cve-issues` | No | Create one GitLab or GitHub issue per fixable CVE |

Steps 9a and 9b are alternatives. The selection pipeline picks one CVE. The analysis pipeline triages the full set.

**Human handoff.** The pipeline stops here. A person reviews the decision or the issue, then starts the remediation pipeline with those values as parameters. For the analysis pipeline, the developer comments `/remediate` on an issue to trigger remediation.
:::

:::tab Stage 3: Remediate
The remediation pipeline takes the six-field decision as input. It does not scan or triage.

| Step | Task | Agent? | What it does | Gated on |
| --- | --- | --- | --- | --- |
| 1 | `git-clone` | No | Clone the source | Always |
| 2 | `verify-commit` (optional) | No | Check commit signature | `verify-commit=true` |
| 3 | `ai-remediate-dependency` / `lw-remediate-dependency` | **Yes** | Edit the manifest, verify compile. Emit `CHANGED=1/0` | `SELECTED=1` |
| 4 | `maven` (re-run tests) | No | Run `mvn verify` | `CHANGED=1` |
| 5 | `open-pr-cve` | No | Commit, push branch, create PR/MR | `CHANGED=1` |

**Fail-closed.** If the agent cannot apply the fix or the build fails, the result is `CHANGED=0`. Steps 4 and 5 are skipped. No PR is opened for broken code.

**Human handoff.** The pipeline stops at the PR. A developer reviews and merges into the existing path to production.
:::

:::tab Stage 4: Test (optional)
A developer comments `/generate-tests` on an issue to trigger this pipeline. It runs independently of remediation.

| Step | Task | Agent? | What it does | Gated on |
| --- | --- | --- | --- | --- |
| 1 | `git-clone` | No | Clone the source | Always |
| 2 | `maven` (package) | No | Build the application | Always |
| 3 | `ai-generate-tests` / `lw-generate-tests` | **Yes** | Generate JUnit tests, run them. Emit `TESTS_ADDED` count | Always |
| 4 | `maven` (re-run) | No | Run all tests including generated ones | `TESTS_ADDED > 0` |
| 5 | `open-pr-tests` | No | Open a tests-only PR | `TESTS_ADDED > 0` |
:::

:::tab Stage 5: Deliver
The pipeline stops at the pull request. Everything after merge is the organization's existing CI/CD path.

| Step | Who | What happens |
| --- | --- | --- |
| Merge | Developer | Reviews and merges the PR |
| Deploy | CI/CD pipeline | Picks up the merge, deploys to staging then production |
| Verify | Vulnerability management | Re-scan confirms production no longer has the affected version |
:::

## The six-field contract

The triage stage produces these fields. The remediation stage consumes them.

| Field | Meaning |
| --- | --- |
| `SELECTED` | `1` if a CVE was selected, `0` otherwise |
| `CVE_ID` | The CVE identifier |
| `PACKAGE` | Maven coordinates (`groupId:artifactId`) |
| `CURRENT_VERSION` | The vulnerable version |
| `FIXED_VERSION` | The version to change to |
| `JUSTIFICATION` | Why this CVE was chosen |

For the analysis pipeline, these fields are embedded in the issue body inside an HTML comment marker. The `/remediate` trigger reads them automatically.

## How the agent task runs

This is a deployment choice, not a different pipeline.

| | In-pod (`ai-*` tasks) | Remote service (`lw-*` tasks) |
| --- | --- | --- |
| Where the model runs | Inside the Tekton pod | A separate ADK service, possibly on a different cluster |
| Session | Stateless. One prompt, one answer | Persistent. SSE session with skills, retry, multi-step reasoning |
| What the pipeline sees | `SELECTED`, `CHANGED`, or `TESTS_ADDED` | Same structured result |
| When to use | Simpler setup | Multi-step reasoning, retry on build failure, serve multiple pipelines |

## Rules

- **One CVE at a time.** One dependency change per PR.
- **PRs are never auto-merged.** A developer reviews and merges.
- **Fail-closed.** `CHANGED=0` or `TESTS_ADDED=0` skips the PR.
- **No discovery.** The agent reads the scanner's output.
- **No library patching.** The agent changes the version, not the library source.
- **Secrets stay mounted.** Tokens and keys are never in the diff.
- **Backend is pluggable.** Anthropic, OpenAI-compatible, Bedrock, Vertex, IBM Granite. Claude Code or aider.

## Without agents

Remove the agent tasks and the pipeline still runs stages 1 and 5. A person does stages 2, 3, and 4 manually. The same scanning, SBOM, policy gate, image checks, and deployment path. Agents compress the middle — they do not replace the ends.
