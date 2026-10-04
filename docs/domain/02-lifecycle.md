---
title: CVE lifecycle
summary: Ten phases from discovery to lessons learned. For each phase, an agent may assist, may own a bounded step, or must stay out.
---

A vulnerability moves through an ecosystem in phases. These ten phases are a working map, not the names of states in the CVE Program. Ownership varies by organization and ecosystem. Select a phase to read its actors, work, output, and the pressure AI puts on that step.

The formal CVE record is a separate, shorter track: **No ID, Reserved, Published, Updated or Rejected**. A reserved identifier is not yet a public vulnerability record. Publication can happen before a fix exists.

## The ten phases

:::phase
number: 01
title: Discover
owner: Research
purpose: Create a credible private finding.
actors: Independent researchers, vendor AppSec teams, open-source maintainers, bug-bounty participants, human analysts, or LLM security agents.
work: Find a candidate weakness, build evidence, identify the affected component, and avoid unsafe testing on systems without authorization.
output: A private report with reproduction steps, an impact hypothesis, the affected build, and a contact path to the vendor or coordinator.
ai: Discovery capacity grows, but so do duplicate reports, low-confidence findings, unsafe autonomous testing, and the validation burden placed on maintainers.
:::

:::phase
number: 02
title: Intake
owner: Disclosure intake
purpose: Route, acknowledge, secure, and track the report.
actors: Vendor PSIRT, security response team, open-source maintainer, bug-bounty platform, CERT/CC, or another disclosure coordinator.
work: Authenticate the channel, acknowledge receipt, protect embargoed details, find the product owner, and establish a case and communication cadence.
output: An owned case with a secure communication path, reporter expectations, initial urgency, and an escalation route.
ai: Agents can normalize and route reports at scale, but prompt injection, malicious attachments, identity spoofing, and sensitive-data leakage become intake risks.
:::

:::phase
number: 03
title: Validate and scope
owner: Product security
purpose: Decide whether the issue is real, distinct, and in scope.
actors: Product security, maintainers, the reporter, test engineers, architecture owners, and sometimes the CNA.
work: Reproduce the behavior, trace root cause, deduplicate, identify affected and unaffected versions, map configurations, and estimate impact.
output: A validated vulnerability with clear scope, or a duplicate, non-security bug, out-of-scope report, or disputed conclusion.
ai: AI can build harnesses and trace data flow quickly. The control point is trustworthy reproduction in an isolated environment with auditable evidence.
:::

:::phase
number: 04
title: Reserve and coordinate
owner: CNA and coordination
purpose: Create shared identity and align disclosure across parties.
actors: The responsible CNA, vendor PSIRT, researcher, upstream project, downstream vendors, cloud providers, OEMs, and disclosure coordinators.
work: Reserve a CVE ID when appropriate; establish embargo membership, disclosure date, credits, affected-product language, ownership, and cross-vendor dependencies.
output: A reserved identifier and coordinated disclosure plan. The CVE is not yet a public vulnerability record.
ai: Dependency mapping and drafting get faster, while access control, provenance, agent identity, and preventing embargo leakage become more important.
:::

:::phase
number: 05
title: Assess in parallel
owner: Scoring and threat analysis
purpose: Separate severity, exploitability, threat, and business priority.
actors: Vendor and CNA analysts, NVD or other enrichment providers, red teams, exploit researchers, threat-intelligence teams, defenders, and attackers.
work: Describe technical severity with CVSS and CWE; validate exploit conditions; develop safe detections; and add likelihood or observed-exploitation evidence as it emerges.
output: Potentially multiple CVSS vectors, an exploitability assessment or proof of concept, detection ideas, and evolving signals such as EPSS or KEV status.
ai: AI accelerates exploit validation and detection engineering. CVSS remains severity, not proof of exploitation, probability, or organization-specific priority.
:::

:::phase
number: 06
title: Fix and release
owner: Engineering and release
purpose: Remove the root cause without creating a new failure.
actors: Upstream maintainers, vendor engineering, security engineers, QA, release engineering, and code-signing or build-infrastructure owners.
work: Design the fix, add regression tests, check variants, backport where supported, test compatibility, build and sign releases, and prepare mitigations.
output: A reviewed patch, supported fixed versions, tests, release artifacts, rollback plan, and advisory content.
ai: Agents can propose patches and backports, but semantic correctness, variant coverage, supply-chain provenance, and release authorization remain decisive.
:::

:::phase
number: 07
title: Publish and enrich
owner: Publication and enrichment
purpose: Make authoritative, machine-readable information public.
actors: The CNA, vendor or project, CVE Program, NVD and other data publishers, security researchers, and threat-intelligence providers.
work: Publish the CVE Record and advisory, link fixes and references, state affected versions and mitigations, add scoring and product metadata, and correct errors over time.
output: A public CVE Record, vendor advisory, fixed-version guidance, enrichment records, and feeds consumed by tools across the ecosystem.
ai: The same machine-readable disclosure can generate defensive queries and attacker playbooks. The publication-to-reproduction interval can collapse sharply.
:::

:::phase
number: 08
title: Repackage and integrate
owner: Software supply chain
purpose: Move the fix through every software supply-chain layer.
actors: Linux distributions, package registries, language ecosystems, OEMs, managed-service and cloud providers, dependency maintainers, and application teams.
work: Ingest or backport the upstream fix, rebuild and sign packages or images, publish channels, update lockfiles, test dependent applications, and release new versions.
output: Patched downstream packages, containers, firmware, SaaS deployments, dependency pull requests, and application releases.
ai: Update agents can open and test changes across dependency graphs. Long-tail compatibility, abandoned packages, generated code, and ownership gaps still slow propagation.
:::

:::phase
number: 09
title: Prioritize and remediate
owner: Vulnerability management
purpose: Decide what is exposed and reduce real organizational risk.
actors: Vulnerability management, asset and service owners, platform teams, SRE and operations, change management, risk owners, and leadership for exceptions.
work: Match vulnerable versions to assets, confirm reachability and exposure, combine severity with threat and business context, then patch, mitigate, isolate, accept, or retire.
output: Approved remediation actions, deployed changes, documented exceptions, compensating controls, and verification that exposure is removed.
ai: AI can join advisories to inventories and orchestrate low-risk fixes. Poor asset data, unclear ownership, maintenance windows, and rollback risk remain bottlenecks.
:::

:::phase
number: 10
title: Observe and learn
owner: SOC, IR, and governance
purpose: Detect exploitation and improve both the record and the system.
actors: SOC and incident-response teams, threat-intelligence providers, CISA and other authorities, CNA and vendor teams, researchers, and engineering leadership.
work: Hunt for indicators, respond to compromise, identify patch bypasses and variants, update threat signals and CVE data, run postmortems, and improve development controls.
output: Incidents contained, detections updated, records corrected or rejected when needed, variants tracked, and preventive tests or design changes added.
ai: Agents can correlate telemetry and code history at portfolio scale. Poisoned feedback, privacy, model drift, and over-automation can make the learning loop worse.
:::

## Where agents fit

| Phase | Agent role | Why |
| --- | --- | --- |
| 01 Discover | Assist only | More findings and more noise. Isolated validation with auditable evidence is the control |
| 02 Intake | Assist only | Route and normalize at scale. Prompt injection, spoofing, and data leakage are intake risks |
| 03 Validate | Stay out unless authorized | Reproduction belongs in an isolated lab, with authorization. Not a routine agent task |
| 04 Coordinate | Stay out | Embargo membership, disclosure dates, and credits are human decisions |
| 05 Assess | Assist only | CVSS, EPSS, and detection engineering can be accelerated. Priority is still an organizational decision |
| 06 Fix and release | Stay out of customer agents | The library patch, its tests, and its signed build belong to the upstream maintainer or to a supplier like Lightwell |
| 07 Publish | Stay out | CVE record publication is a CNA responsibility |
| 08 Repackage | Assist only | An agent can open dependency-update pull requests. Compatibility and ownership gaps remain human problems |
| 09 Prioritize and remediate | Own a bounded step | Match the advisory to the application, pin the fixed coordinate, open a pull request, and stop for a person |
| 10 Observe and learn | Stay out of routine agents | Incident response, postmortems, and record corrections are human-led. Agents that feed back into this loop need governance |

Phase 09 is the only phase where a remediation agent can own a bounded step in routine operation. The execution model pages describe [three ways](04-pipeline-only.html) to [do that](05-pipeline-with-agents.html).

## Four workstreams after validation

Publication may occur before a fix exists. Scoring, exploit analysis, patching, and disclosure planning often run at the same time.

| | Workstream | Typical owners |
| --- | --- | --- |
| A | Record and severity. CVE identity, affected products, references, CWE, and CVSS vectors | CNA, vendor, NVD, other data publishers |
| B | Exploitability and threat. Reachability, prerequisites, safe reproduction, proofs of concept, detections, EPSS, and observed exploitation | Red teams, researchers, threat intelligence, CISA |
| C | Fix and release. Root-cause repair, regression tests, backports, signed builds, mitigations, and rollback | Maintainers, engineering, QA, release teams |
| D | Disclosure coordination. Embargo scope, partner readiness, advisory language, credits, and publication timing | PSIRT, CNA, researchers, downstream vendors |

## Severity is not priority

| Signal | What it is |
| --- | --- |
| CVSS | Technical severity. Intrinsic characteristics and impact. More than one assessor may publish a vector |
| Exploit analysis, EPSS, KEV | Likelihood and evidence. Theoretical impact, estimated probability, and confirmed exploitation are different facts |
| Exposure and business context | The organizational decision. Assets, reachability, criticality, compensating controls, operational risk, and threat evidence |

:::equation
Remediation priority | = | severity | + | threat evidence | + | environmental context
:::

Priority decides which advisory to act on first among advisories that have a fix. It does not choose the fix. The fix comes from the advisory's fixed event.

## What AI changes

AI compresses intervals and expands queues. The hard problems move toward validation, authorization, provenance, rollout safety, and governance.

| | Pressure | Control |
| --- | --- | --- |
| Discovery | More findings and more noise | Isolated validation with auditable evidence |
| Disclosure | Advisories become inputs for defense and for attack | Synchronize fixes and defensive guidance |
| Patching | Agents draft fixes, tests, backports, and notes | Trusted builds, human approval, staged rollout, and rollback |
| Operations | Agents join advisories to inventories | Reliable asset data, bounded authority, and verification |
