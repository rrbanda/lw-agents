---
title: Agent tasks
summary: What each agent task does inside phase 09, which sub-steps are covered, and where the Lightwell integration stands.
---

All agent tasks today operate within phase 09 of the CVE lifecycle: prioritize, remediate, test, and validate. The pipeline head (scan, SBOM, policy gate) and the pipeline tail (deploy, verify production) are not agent tasks.

## Phase 09 sub-steps

| Sub-step | What does it | Agent task? | Status |
| --- | --- | --- | --- |
| Scan and generate SBOM | Build the application and container, generate a bill of materials | No. Pipeline task (`buildah`, `upload-sbom-to-rhtpa`) | Covered |
| Vulnerability analysis | Compare the SBOM against known advisories | No. Pipeline task (`rhtpa-vulnerability-analysis`) | Covered |
| Remediation recommendations | Look up vendor fix-version recommendations | No. Pipeline task (`rhtpa-remediation-report`) | Covered |
| Policy gate | Filter the must-fix set by severity or policy | No. Pipeline task (`conforma-policy-check`) | Covered |
| Select one CVE | Choose the highest-priority advisory from the must-fix set | Yes. `ai-select-cve` (inline) or `lw-select-cve` (remote service) | Covered |
| Analyze all CVEs | Produce a decision for every fixable advisory, render issue files | Yes. `ai-analyze-cves` (inline) or `lw-analyze-cves` (remote service) | Covered |
| Open issues | Create one issue per fixable CVE in GitLab or GitHub | No. Pipeline task (`open-cve-issues`) | Covered |
| Change the manifest | Edit `pom.xml` or `build.gradle` to the fixed version | Yes. `ai-remediate-dependency` (inline) or `lw-remediate-dependency` (remote service) | Covered |
| Build and test | Run the application build and existing tests | Partially. The inline agent runs `mvn verify` inside the task. The pipeline also has a standalone `maven` re-run task | Covered |
| Open the pull request | Commit, push a branch, and create a PR/MR | Partially. The inline pipeline uses a separate `open-pr` task. The remote service does it internally | Covered |
| Validate the fix | Check that the diff is the correct pin, the resolution is from the right repository, and the PR does not over-claim | Yes. `validation.py` in lw-agents with architect and pentester skills | Not wired into ssc-demo pipelines |
| Generate tests | Write JUnit tests that prove the application still works with the fix | Yes. `ai-generate-tests` (inline) or `lw-generate-tests` / `lw-investigate-cve` + `lw-opencode-write-tests` (remote service) | Covered |
| Image scan and admission | Check the container image against security policies | No. Pipeline tasks (`acs-image-scan`, `acs-image-check`, `acs-deploy-check`) | Covered |
| Human merge | Developer reviews and merges the pull request | No. Human step, by design | Covered |
| Deploy to production | Update the deployment manifest | No. Pipeline task (`update-deployment`) | Covered |
| Verify production is clean | Confirm the running estate no longer has the affected version | No task exists | Not in scope. Agents stop at the PR |

## What the agent tools call today

Every tool in the agent service hits a public upstream API. None of them call Lightwell.

| Tool | What it hits | What it provides | What it cannot provide |
| --- | --- | --- | --- |
| `check_version_exists` | Maven Central (`repo1.maven.org`) | Whether an upstream version is on Central | Whether a `.rhlw` version exists. Lightwell packages are not on Central |
| `lookup_osv` | `api.osv.dev` | Upstream affected ranges and fix versions | The Lightwell fixed coordinate. Lightwell's OSV is a different feed |
| `lookup_nvd` | NVD | CVSS, CWE, references | A coordinate to pin |
| `lookup_vex` | Red Hat CSAF/VEX (`security.access.redhat.com`) | Red Hat product advisories for RHEL, OpenShift | Lightwell advisory data. Different product |
| `lookup_epss` | FIRST.org | Exploitation probability | A coordinate |
| `search_github_advisory` | GitHub Advisory Database | Upstream fix commits and patched versions | The Lightwell coordinate |
| `discover_upstream_repo` | GitHub, Maven POM metadata | The upstream repository for a component | Whether Lightwell has a backport |

## Lightwell tools now available

The following tools have been added to close the gap. Both the selection and analysis agents now have access to them.

| Tool | What it hits | What it provides |
| --- | --- | --- |
| `lookup_lightwell_osv` | Lightwell OSV feed at `packages.redhat.com` | The fixed coordinate, affected ranges, and advisory metadata for a Lightwell advisory. This is the version authority for a Lightwell pin |
| `check_lightwell_version_exists` | Lightwell Java repository at `packages.redhat.com` | Whether a `.rhlw` version exists in the Lightwell repository. Use instead of `check_version_exists` for Lightwell versions |
| `check_version_exists_smart` | Routes automatically | Checks the Lightwell repository when the version has a `.rhlw` or `+rhlw` suffix, Maven Central otherwise |
| `list_lightwell_advisories` | Lightwell OSV `PULP_MANIFEST` | A list of all available advisory IDs and their checksums. A changed checksum means new data |

### Authentication

The production Lightwell repositories require a registry service account. Set `LIGHTWELL_USERNAME` and `LIGHTWELL_TOKEN` as environment variables. When both are set, the tools include HTTP Basic auth. When unset, only the public demo feed is accessible.

The public demo feed (no auth required) can be used by setting:

```
LIGHTWELL_OSV_BASE_URL=https://packages.redhat.com/api/pulp-content/public-lightwell-demo/osv/java/remediated
```

### How the tools change agent behavior

| Before | After |
| --- | --- |
| `check_version_exists` rejects `.rhlw` versions because they are not on Central | `check_version_exists_smart` routes `.rhlw` versions to the Lightwell repository |
| The agent has no way to look up a Lightwell advisory | `lookup_lightwell_osv` returns the fixed coordinate from the Lightwell OSV feed |
| The selection skill says "never select without a verified fixed version" and the only check is Central | The agent can verify the version exists in the Lightwell repository |
| The agent cannot tell whether a package has a Lightwell backport | `list_lightwell_advisories` lists what is available in the feed |

## What still needs to change

The tools are available. The skills have not been rewritten to use them. The current skill text still says:

- `cve-triage`: "Call `check_version_exists` to verify" (which only checks Central)
- `cve-analysis`: "Call `check_version_exists` for each candidate to verify" (same)
- `maven-remediation`: Investigates the upstream commit before editing (unnecessary for a Lightwell pin)

The skill rewrite is a separate task tracked on the [Skill contract](05-skill-contract.html) reference page. The tools are the prerequisite. The tools are now in place.

## Validation gap

`validation.py` exists in the agent service with two skills (`validation-architect` and `validation-pentester`), but no pipeline task in `ssc-demo` calls it. The validation step is not wired into either the inline or remote pipeline flow.

The current validation skills also contain instructions that belong to a different phase (exploit reproduction, attack reconstruction). The domain model restricts validation for a Lightwell pin to three checks: the manifest coordinate matches the fixed event, the resolution repository is the trusted proxy, and the pull request does not claim more than it did.

## Test generation architectures

Two architectures exist for test generation:

| Architecture | How it works |
| --- | --- |
| Single step (inline `ai-generate-tests` or remote `lw-generate-tests`) | One agent call generates tests, runs them, and reports the count |
| Two-step (remote only: `lw-investigate-cve` then `lw-opencode-write-tests`) | The ADK agent investigates the CVE and produces a test specification. OpenCode writes the test code from that specification. Each tool does what it is best at |

The two-step architecture is a pattern for decomposing agent work: separate the reasoning (what tests should exist) from the writing (produce the code). The specification is a workspace file, not a Tekton result, so it avoids the 4KB result-size limit.

## Assessment agent capabilities (exploit-iq — phases 03 and 05)

The phase 09 agents above do not assess whether a CVE is exploitable. They assume the must-fix list is correct and work from it. The vulnerability analysis agent (exploit-iq) covers the earlier phases: validating that the vulnerability is real in this application and assessing its exploitability.

### Assessment pipeline stages

| Stage | What it does | Phase |
| --- | --- | --- |
| Fetch intel | Gather CVE data from NVD, GHSA, EPSS, Red Hat Security Advisories, Ubuntu advisories | 05 |
| Calculate intel score | Score the quality of available intelligence to decide the analysis depth | 05 |
| Process SBOM | Parse the application SBOM and identify affected components | 05 |
| Verify vulnerable package | Check if the vulnerable package is in the dependency tree at the affected version, using lockfiles and dependency analysis | 03 |
| Source acquisition | Clone the application source and install dependencies for code analysis | 03 |
| Code segmentation | Segment the codebase for efficient tool-based investigation | 03 |
| Checklist generation | Generate a structured list of investigation questions per CVE | 05 |
| Agent executor | Fan out to specialized sub-agents (reachability and code understanding) to answer each question | 03, 05 |
| Summarize | Consolidate findings from all sub-agents into a coherent summary | 05 |
| Justify | Produce an exploitability verdict: exploitable, not exploitable, or insufficient evidence | 05 |
| Generate CVSS | Produce a context-adjusted CVSS score | 05 |
| Generate VEX | Produce a machine-readable VEX document per component | 07 |
| Fetch patches | Retrieve upstream fix patches and commit data | 05 |

### Assessment sub-agents

| Sub-agent | What it investigates | Tools |
| --- | --- | --- |
| Reachability agent | Call chains, code paths, whether vulnerable code is called or reachable, whether untrusted data can reach a function | Call Chain Analyzer (CCA), Function Locator (FL), Function Caller Finder (FCF), Library Version Finder (FLVF), Transitive Code Search |
| Code understanding agent | Configuration, version, presence, application-level settings, input validation, general behavioral questions | Source Grep, Lexical Search, Configuration Scanner, Import Usage Analyzer, Container Image Analysis |

### Assessment tools

| Tool | What it does |
| --- | --- |
| Call Chain Analyzer | Traces call chains from application entry points to vulnerable functions |
| Function Locator | Finds function definitions in the codebase across Java, Python, Go, JavaScript, C/C++ |
| Function Caller Finder | Finds all callers of a specific function |
| Library Version Finder | Determines the installed version of a library in the dependency tree |
| Transitive Code Search | Searches for code patterns across transitive dependencies |
| Source Grep | Pattern-based search across the application source tree |
| Lexical Search | Full-text search with code-aware tokenization |
| Configuration Scanner | Scans application configuration files for security-relevant settings |
| Import Usage Analyzer | Analyzes how imported packages are used in the application code |
| Container Image Analysis | Extracts and analyzes data from container image layers |
| SERP (web search) | Searches the web for patches, advisories, and exploit information |
| Local VDB Retriever | Retrieves vulnerability data from a local vector database |

### How assessment connects to remediation

The assessment agent's output is an exploitability verdict per CVE. Today, the remediation pipeline's input is a must-fix list filtered by severity policy. The connection point is the policy gate.

If the assessment layer is deployed, its verdicts can refine the policy: a CVE that is not exploitable in this application can be deprioritized even if it is severity critical. A CVE that is actively exploited and confirmed reachable should be prioritized above one that is merely critical by CVSS score.

This integration is not wired today. The assessment and remediation layers run independently. See [Where agents help](05b-where-agents-help.html) for the full lifecycle mapping and optionality tiers.

