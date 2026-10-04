---
title: Where agents help
summary: A greenfield map of every CVE lifecycle phase, the agent capabilities that exist for each, and how to compose them.
---

Agents are not only a phase 09 feature. Across the ten lifecycle phases, agent capabilities range from discovering novel vulnerabilities to assessing exploitability to pinning a fixed coordinate. Some are built. Some are optional. Some are human-only. This page maps the full picture.

## Phase-by-phase

| Phase | What an agent can do | What exists today | Optional? | Lightwell-specific |
| --- | --- | --- | --- | --- |
| **01 Discover** | Frontier AI models autonomously find novel zero-day vulnerabilities in upstream open-source libraries | Clearing House members use frontier models (Mythos, Glasswing). Not an agent in these repositories | Yes. Only Clearing House members do this | Members submit novel vulnerabilities to Red Hat through Lightwell for remediation |
| **02 Intake** | Normalize and route vulnerability reports at scale, classify duplicates, assign urgency | Not implemented | Yes. Most organizations rely on existing PSIRT or bug-bounty workflows | N/A |
| **03 Validate** | Reproduce the vulnerability in an isolated environment, trace code reachability, understand whether the vulnerable code path is exercised | **Vulnerability analysis agent** (exploit-iq): reachability agent traces call chains using Call Chain Analyzer, Function Locator, Function Caller Finder, and Library Version Finder tools. Code understanding agent analyzes configuration, environment, and version-specific behavior | Yes. Some organizations skip validation and go directly to assessment based on advisory severity | N/A |
| **04 Coordinate** | Map dependency trees across vendors, draft embargo communications, track disclosure timelines | Not implemented | Human-only for most organizations | Clearing House manages embargo periods and pre-disclosure coordination |
| **05 Assess** | Deep exploitability analysis: is this CVE actually exploitable in this specific application? Fetch intel, process the SBOM, verify the vulnerable package is in the dependency tree, generate an investigation checklist, run multi-agent investigation, summarize findings, justify exploitability, generate CVSS, produce VEX documents, and fetch upstream patches | **Vulnerability analysis agent** (exploit-iq): full pipeline with intel from NVD, GHSA, EPSS, Red Hat Security Advisories, and Ubuntu. Fan-out investigation across reachability and code understanding sub-agents. Produces exploitability verdicts, VEX, and CVSS | Yes. Can be replaced by simpler severity-based triage when deep analysis is not worth the compute cost | When Lightwell has a backport, assessment confirms the vulnerability is real and exploitable before the organization spends effort consuming the fix |
| **06 Fix and release** | Propose patches, generate regression tests, backport to older versions, build and sign releases | Lightwell builds the security-only backport. This is not an agent task for the customer | N/A for customer agents | Lightwell's core function: build, test, sign, and publish the backport on the version the application already runs |
| **07 Publish** | Generate machine-readable advisories, VEX documents, and enrichment data | **Vulnerability analysis agent** (exploit-iq) generates VEX documents (`cve_generate_vex`). Lightwell publishes OSV with fixed events | Yes. CNA responsibility | Lightwell publishes advisory data to the OSV feed at `packages.redhat.com` |
| **08 Repackage** | Open dependency-update pull requests across dependency graphs, update lockfiles, test downstream applications | Not implemented as a separate phase agent. The Renovate bot in the workshop handles this for the lab | Yes | Lightwell publishes to `packages.redhat.com`. The customer's artifact manager (Artifactory, Nexus) proxies it. The proxy makes the package resolvable |
| **09 Prioritize and remediate** | Select the highest-priority advisory, analyze all fixable CVEs and open issues, change the application manifest to the fixed version, generate tests, validate the fix, open a pull request | **ssc-demo**: four Tekton pipelines (inline agent + remote agent service variants). **lw-agents**: Google ADK service with specialist agents and skills. **Lightwell tools**: OSV feed lookup, version verification, smart routing | Core. This is the main execution pipeline | `lookup_lightwell_osv` finds the fixed coordinate. `check_lightwell_version_exists` verifies the `.rhlw` version. `check_version_exists_smart` auto-routes based on the version suffix |
| **10 Observe and learn** | Correlate telemetry and code history at portfolio scale, detect exploitation, identify patch bypasses | Not implemented | Human-led. SOC and incident response own this phase | N/A |

## Three layers

The agent capabilities organize into three layers. Each layer is independent. An organization can adopt any combination.

### Assessment layer (phases 03 and 05)

The vulnerability analysis agent answers the question: **Is this CVE actually exploitable in my application?**

It does not fix anything. It produces a verdict, a justification, and optionally a VEX document and a CVSS score. This verdict can feed into the execution layer to prioritize which CVEs to fix first, and to avoid spending remediation effort on vulnerabilities that are not exploitable in the specific application context.

The assessment pipeline:

1. Fetch CVE intelligence from NVD, GHSA, EPSS, Red Hat advisories, and other sources
2. Process the application's SBOM to identify affected components
3. Verify the vulnerable package is actually in the dependency tree at the affected version
4. Generate a checklist of investigation questions for each CVE
5. Fan out to specialized sub-agents: reachability (call-chain tracing) and code understanding (configuration, environment, behavioral analysis)
6. Summarize findings and produce an exploitability justification
7. Generate CVSS score and VEX document

Tools: Call Chain Analyzer, Function Locator, Function Caller Finder, Library Version Finder, Source Grep, Lexical Search, Configuration Scanner, Import Usage Analyzer, Container Image Analysis, SERP (web search for patches and advisories).

### Execution layer (phase 09)

The remediation pipeline takes a published advisory with a known fix and opens a pull request. This is the core pipeline described on the [Pipeline with agents](05-pipeline-with-agents.html) and [Agent tasks](05a-agent-tasks.html) pages.

Three execution models:

- **Pipeline only**: scan, report, human acts
- **Pipeline with inline agents**: agent tasks inside Tekton pods
- **Pipeline with remote agent service**: Tekton calls a Google ADK service over SSE

### Patch source layer

Where the fixed version comes from:

- **Upstream release**: the open-source project ships a new version containing the fix
- **Lightwell backport**: a security-only patch on the version the application already runs, when it cannot upgrade
- **Maven Central / PyPI**: the registry where upstream releases are published
- **Enterprise proxy**: the internal artifact manager that resolves Lightwell or upstream packages

## Optionality tiers

Every capability is optional except the scan-and-report foundation. The tiers build on each other.

| Tier | What it adds | What it compresses | Phases covered |
| --- | --- | --- | --- |
| **1. Pipeline only** | SBOM scan, vulnerability analysis, policy gate, image checks. A person reads and acts | Nothing. This is the baseline | 09 (intake only) |
| **2. Add triage agents** | Selection and analysis agents choose which CVEs to fix and open one issue per fixable advisory | Triage from about 5 days to minutes | 09 (prioritize) |
| **3. Add remediation agents** | Remediation and test generation agents change the manifest, run the build, and open a pull request | Developer sprint from 5–14 days to minutes | 09 (remediate + test) |
| **4. Add assessment agents** | Exploitability analysis answers "is this CVE real in my application?" before effort is spent fixing it | False-positive remediation. 77 must-fix CVEs become 56 fixable, and only the exploitable ones are prioritized | 03, 05 |
| **5. Add Lightwell integration** | Lightwell tools read the OSV feed and verify `.rhlw` versions. The agent pins the backport when the application cannot upgrade | The search for the right version when Central does not have it | 09 (with Lightwell as patch source) |
| **6. Fully agentic** | A coordinator decides the next action across phases and applications inside written rules. Not built | Handoff delays between pipeline runs | 03, 05, 09 (orchestrated) |

Tier 1 is always present. Tiers 2 and 3 are the most common addition. Tier 4 is valuable when the must-fix list has many false positives. Tier 5 applies when Lightwell is the patch source. Tier 6 is a design target.

## How the layers connect

The assessment layer's output is an exploitability verdict per CVE. The execution layer's input is a must-fix list filtered by policy. The connection point is the policy gate.

Today, the Conforma policy gate in `ssc-demo` filters by severity (critical and high). If the assessment layer produces a verdict, that verdict can refine the policy: a CVE that is not exploitable in this application can be deprioritized even if it is severity critical. A CVE that is actively exploited (KEV) and confirmed reachable by the assessment agent should be prioritized above one that is merely critical by CVSS.

This connection is not wired today. The two layers run independently. The guide documents it as an integration point for organizations that adopt both.

## What customers can leave out

| If the customer does not want | Leave out | What they keep |
| --- | --- | --- |
| Deep exploitability analysis | Assessment layer (exploit-iq) | Severity-based triage in the pipeline |
| AI-generated tests | Test generation agent | Manual tests or existing test suite |
| Lightwell backports | Lightwell tools | Upstream upgrades only |
| AI-driven triage | Selection and analysis agents | Human reads the scan report |
| Any AI at all | All agent tasks | Pipeline only: scan, report, human acts |

Nothing breaks when a layer is removed. The pipeline still runs. The scan still reports. The person still decides.
