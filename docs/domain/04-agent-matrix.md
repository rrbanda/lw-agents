---
title: Where agents help
summary: A matrix of every CVE task mapped to agent capability. Independent of Lightwell, independent of execution engine.
---

This matrix takes every task from [What people do](03-cve-tasks.html) and answers: can an agent do this? What exists? Is it optional?

No Lightwell here. Lightwell changes where the fixed version comes from — that is a separate layer on [Where Lightwell fits](05-lightwell.html). No pipeline details here. The pipeline is how agents run — that is on [The pipeline](06-the-pipeline.html).

## The matrix

| Task | Stage | Can an agent do it? | What exists | Optional? |
| --- | --- | --- | --- | --- |
| Generate an SBOM | Discover | No. Deterministic build step | Pipeline task (`buildah-rhtap`) | No. Prerequisite for everything |
| Submit to vulnerability analyzer | Discover | No. API call | Pipeline task (`upload-sbom-to-rhtpa`) | No |
| Get vulnerability report | Discover | No. API call | Pipeline task (`rhtpa-vulnerability-analysis`) | No |
| Apply policy (must-fix filter) | Discover | No. Policy engine | Pipeline task (`conforma-policy-check`) | No |
| Check container image | Discover | No. Scanner | Pipeline tasks (`acs-image-scan`, `acs-image-check`) | Yes. Can substitute other scanners |
| Research each advisory | Triage | Yes. Read advisories, check versions, check EPSS and KEV | Selection agent (`ai-select-cve` / `lw-select-cve`) and analysis agent (`ai-analyze-cves` / `lw-analyze-cves`) | Yes. A person can read the report |
| Estimate blast radius | Triage | Partially. Agent can check dependency trees | Part of analysis agent output | Yes |
| Filter false positives | Triage | Yes, with deep analysis | Vulnerability analysis agent (exploit-iq): reachability analysis, code understanding | Yes. Can rely on severity-only policy instead |
| Assess exploitability | Triage | Yes. Full investigation pipeline | Vulnerability analysis agent (exploit-iq): fetch intel, process SBOM, verify vulnerable package, generate checklist, run sub-agents (reachability + code understanding), summarize, justify, generate CVSS, generate VEX | Yes. This is the assessment layer |
| Prioritize | Triage | Yes. Combine signals into a ranked list | Selection agent scores by EPSS, CVSS, release-line compatibility, blast radius | Yes. A person can prioritize manually |
| Log (create issues) | Triage | No. Deterministic from agent output | Pipeline task (`open-cve-issues`) | No, if using agents. The agent produces the issue content |
| Identify the fixed version | Remediate | Yes. Look up advisories and repositories | Selection and analysis agents. Lightwell tools when the fix is a backport (separate layer) | Yes |
| Edit the manifest | Remediate | Yes. Change one dependency version | Remediation agent (`ai-remediate-dependency` / `lw-remediate-dependency`). Supports Maven and Gradle. BOM-aware | Yes. A developer can edit manually |
| Run the build | Remediate | No. Deterministic | Pipeline task (`maven`) or inside the agent task | No |
| Run existing tests | Remediate | No. Deterministic | Pipeline task (`maven verify`) | No |
| Handle build failures | Remediate | Yes. Retry with classified error feedback | Remote agent service retries up to 3 times. Fail-closed: `CHANGED=0` on failure | Yes. Inline agent is single-attempt |
| Verify the coordinate | Validate | Yes. Check the diff matches the fixed event | Validation agent exists (`validation.py`) but is not wired in the pipeline | Yes |
| Review the diff | Validate | Partially. Agent can flag forbidden patterns | Validation agent's `analyze_diff` tool checks for forbidden patterns, doc-only changes | Yes. Human review is still expected |
| Run additional tests | Validate | Yes. Generate and run JUnit tests | Test generation agent (`ai-generate-tests` / `lw-generate-tests`) | Yes. Existing tests may suffice |
| Classify the change | Validate | Partially. Agent can state evidence for standard change | Audit data in the PR body includes the CVE, the fix, and the build result | Yes |
| Get approval | Validate | No. Human decision | By design. PRs are never auto-merged | No |
| Merge the pull request | Deliver | No. Human action | By design | No |
| Deploy | Deliver | No. Existing CI/CD | Organization's deployment pipeline | No |
| Monitor | Deliver | No. Existing observability | Organization's monitoring | No |
| Rollback if needed | Deliver | No. Operations decision | Organization's rollback process | No |
| Verify production is clean | Deliver | No. Re-scan | Not in scope of current agents | No |

## Summary by stage

| Stage | Tasks an agent can do | Tasks that stay human or deterministic |
| --- | --- | --- |
| Discover | None. All deterministic pipeline tasks | SBOM generation, scanning, policy |
| Triage | Research advisories, estimate blast radius, filter false positives, assess exploitability, prioritize, identify the fixed version | Read the report manually (when no agent) |
| Remediate | Edit the manifest, handle build failures with retry | Run the build, run tests (deterministic) |
| Validate | Verify the coordinate, flag forbidden patterns in the diff, generate tests | Get approval (human), review (human + agent) |
| Deliver | None | Merge, deploy, monitor, rollback, verify production |

## Assessment agents (phases 03 and 05)

The vulnerability analysis agent (exploit-iq) covers tasks that happen before remediation: is this CVE real in my application?

| Capability | What it does | Tools |
| --- | --- | --- |
| Reachability analysis | Trace call chains from application entry points to vulnerable functions | Call Chain Analyzer, Function Locator, Function Caller Finder, Library Version Finder |
| Code understanding | Analyze configuration, environment, and version-specific behavior | Source Grep, Lexical Search, Configuration Scanner, Import Usage Analyzer |
| Intel gathering | Fetch CVE data from NVD, GHSA, EPSS, Red Hat advisories | HTTP clients to public APIs |
| SBOM processing | Verify vulnerable package is in the dependency tree at the affected version | Lockfile and dependency-tree analysis |
| Exploitability verdict | Summarize findings: exploitable, not exploitable, or insufficient evidence | LLM-based justification from investigation results |
| VEX generation | Produce machine-readable VEX documents per component | CSAF generator |
| CVSS generation | Produce context-adjusted CVSS score | LLM-based CVSS scoring |

This layer is optional. Organizations that do not need deep exploitability analysis can use severity-based triage (the policy gate) and go directly to remediation.

## Remediation agents (phase 09)

| Capability | What it does | Implementation |
| --- | --- | --- |
| CVE selection | Choose one advisory from the must-fix set | `cve_selection.py` with `cve-triage` skill |
| CVE analysis | Classify every advisory in the set, produce one issue per fixable CVE | `cve_analysis.py` with `cve-analysis` skill |
| Dependency remediation | Edit the manifest to the fixed version, verify the build | `remediation.py` with `maven-remediation` or `gradle-remediation` skill |
| Test generation | Generate JUnit tests that prove the application still works | `test_generation.py` with `junit-test-generation` skill |
| Fix validation | Check the diff is correct, the coordinate matches, the PR does not over-claim | `validation.py` with `validation-architect` and `validation-pentester` skills. **Not wired in the pipeline** |

## What no agent should do

- Discover a new vulnerability (phase 01 — only Clearing House members with frontier models)
- Publish or correct the CVE record (phase 07 — CNA responsibility)
- Approve or merge the pull request (human decision)
- Deploy to production (operations responsibility)
- Declare production is clean (verification after deployment)
- Write an exploit or proof of concept (not a remediation task)
- Put a registry token in the pull request
