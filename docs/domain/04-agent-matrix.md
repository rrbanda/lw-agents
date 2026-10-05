---
title: Where agents help
summary: A matrix of every CVE task mapped to agent capability. Independent of Lightwell, independent of execution engine.
---

This matrix takes every task from [What people do](03-cve-tasks.html) and answers: can an agent do this? What exists? Is it optional?

No Lightwell here. Lightwell changes where the fixed version comes from — that is a separate layer on [Where Lightwell fits](05-lightwell.html). No pipeline details here. The pipeline is how agents run — that is on [The pipeline](06-the-pipeline.html).

## The matrix

:::tab Discover
| Task | Can an agent do it? | What exists | Optional? |
| --- | --- | --- | --- |
| Generate an SBOM | No. Deterministic build step | Pipeline task (`buildah-rhtap`) | No. Prerequisite for everything |
| Submit to vulnerability analyzer | No. API call | Pipeline task (`upload-sbom-to-rhtpa`) | No |
| Get vulnerability report | No. API call | Pipeline task (`rhtpa-vulnerability-analysis`) | No |
| Apply policy (must-fix filter) | No. Policy engine | Pipeline task (`conforma-policy-check`) | No |
| Check container image | No. Scanner | Pipeline tasks (`acs-image-scan`, `acs-image-check`) | Yes. Can substitute other scanners |

**Agent role:** None. All deterministic pipeline tasks.
:::

:::tab Triage
| Task | Can an agent do it? | What exists | Optional? |
| --- | --- | --- | --- |
| Research each advisory | Yes. Read advisories, check versions, check EPSS and KEV | Selection agent and analysis agent | Yes. A person can read the report |
| Estimate blast radius | Partially. Agent can check dependency trees | Part of analysis agent output | Yes |
| Filter false positives | Yes, with deep analysis | Vulnerability analysis agent (exploit-iq): reachability analysis, code understanding | Yes. Can rely on severity-only policy instead |
| Assess exploitability | Yes. Full investigation pipeline | Vulnerability analysis agent (exploit-iq): fetch intel, process SBOM, verify vulnerable package, generate checklist, run sub-agents, summarize, justify, generate CVSS, generate VEX | Yes. This is the assessment layer |
| Prioritize | Yes. Combine signals into a ranked list | Selection agent scores by EPSS, CVSS, release-line compatibility, blast radius | Yes. A person can prioritize manually |
| Log (create issues) | No. Deterministic from agent output | Pipeline task (`open-cve-issues`) | No, if using agents |

**Agent role:** Research, estimate, filter, assess, prioritize. The heaviest manual work.
:::

:::tab Remediate
| Task | Can an agent do it? | What exists | Optional? |
| --- | --- | --- | --- |
| Identify the fixed version | Yes. Look up advisories and repositories | Selection and analysis agents check upstream advisories and verify versions | Yes |
| Edit the manifest | Yes. Change one dependency version | Remediation agent. Supports Maven and Gradle. BOM-aware | Yes. A developer can edit manually |
| Run the build | No. Deterministic | Pipeline task (`maven`) or inside the agent task | No |
| Run existing tests | No. Deterministic | Pipeline task (`maven verify`) | No |
| Handle build failures | Yes. Retry with classified error feedback | Remote agent service retries up to 3 times. Fail-closed on failure | Yes. Inline agent is single-attempt |

**Agent role:** Find the version, edit the manifest, retry on failure. Build and test are deterministic.
:::

:::tab Validate
| Task | Can an agent do it? | What exists | Optional? |
| --- | --- | --- | --- |
| Verify the coordinate | Yes. Check the diff matches the fixed event | Validation agent exists but is not wired in the pipeline | Yes |
| Review the diff | Partially. Agent can flag forbidden patterns | Validation agent's `analyze_diff` tool | Yes. Human review is still expected |
| Run additional tests | Yes. Generate and run JUnit tests | Test generation agent | Yes. Existing tests may suffice |
| Classify the change | Partially. Agent can state evidence for standard change | Audit data in the PR body | Yes |
| Get approval | No. Human decision | By design. PRs are never auto-merged | No |

**Agent role:** Verify, flag, generate tests, provide evidence. Approval stays human.
:::

:::tab Deliver
| Task | Can an agent do it? | What exists | Optional? |
| --- | --- | --- | --- |
| Merge the pull request | No. Human action | By design | No |
| Deploy | No. Existing CI/CD | Organization's deployment pipeline | No |
| Monitor | No. Existing observability | Organization's monitoring | No |
| Rollback if needed | No. Operations decision | Organization's rollback process | No |
| Verify production is clean | No. Re-scan | Not in scope of current agents | No |

**Agent role:** None. Delivery is human and operational.
:::

## Assessment agents (phases 03 and 05)

The vulnerability analysis agent (exploit-iq) covers tasks that happen before remediation: is this CVE real in my application?

:::tab Reachability
Trace call chains from application entry points to vulnerable functions.

| Tool | What it does |
| --- | --- |
| Call Chain Analyzer | Traces call chains across the codebase |
| Function Locator | Finds function definitions in Java, Python, Go, JavaScript, C/C++ |
| Function Caller Finder | Finds all callers of a specific function |
| Library Version Finder | Determines the installed version of a library |
| Transitive Code Search | Searches across transitive dependencies |
:::

:::tab Code understanding
Analyze configuration, environment, and version-specific behavior.

| Tool | What it does |
| --- | --- |
| Source Grep | Pattern-based search across the source tree |
| Lexical Search | Full-text search with code-aware tokenization |
| Configuration Scanner | Scans config files for security-relevant settings |
| Import Usage Analyzer | Analyzes how imported packages are used |
| Container Image Analysis | Extracts and analyzes data from container image layers |
:::

:::tab Verdict and output
Summarize findings and produce machine-readable output.

| Capability | What it does |
| --- | --- |
| Intel gathering | Fetch CVE data from NVD, GHSA, EPSS, Red Hat advisories |
| SBOM processing | Verify vulnerable package is in the dependency tree at the affected version |
| Exploitability verdict | Summarize findings: exploitable, not exploitable, or insufficient evidence |
| VEX generation | Produce machine-readable VEX documents per component |
| CVSS generation | Produce context-adjusted CVSS score |
:::

This layer is optional. Organizations that do not need deep exploitability analysis can use severity-based triage and go directly to remediation.

## Remediation agents (phase 09)

| Capability | What it does | Implementation |
| --- | --- | --- |
| CVE selection | Choose one advisory from the must-fix set | `cve_selection.py` with `cve-triage` skill |
| CVE analysis | Classify every advisory, produce one issue per fixable CVE | `cve_analysis.py` with `cve-analysis` skill |
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
